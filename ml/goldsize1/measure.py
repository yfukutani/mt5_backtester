"""PB/SCA GOLD の risk% サイジングを掃引し、固定ロットとフロンティアで比較する。

【判定の考え方】risk% と固定ロットは「同じリスク量でリターンが増えるか」でしか比べられない。
純益だけ見ても、サイズを上げれば増えるのは当たり前である。よって
  ・risk% 側の (純益, DD) 曲線
  ・固定ロット側の (純益, DD) 曲線（ml/deploy50b/results.csv に実測済み）
を重ね、同じDDでどちらが純益が高いかを見る。

【通貨の罠は回避済み】GszLot は OrderCalcProfit を使う。SYMBOL_TRADE_TICK_VALUE は
GOLD ではUSD建てのまま返るため使わない（docs/profit_trail_20260805.md §2）。
検算: risk0.68%→全件0.01ロット（固定と一致）、risk5.0%→平均0.0666ロット・0.01〜0.14に分散。

【端末】BT1 は MT5 の LiveUpdate（build 6140→6180）がテスト実行を乗っ取るため使わない。
"""
from __future__ import annotations

import csv
import queue
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "goldsize1"
RUN_DIR = ROOT / "runs"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "run_deals"
OUT = ROOT / "results.csv"
LOG = ROOT / "measure.log"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")

DEPOSIT = 500000
RUN_TIMEOUT = 1800

# 【2026-09-05】MT5の LiveUpdate（build 6140→6180）が起動のたびにテスト実行を乗っ取り、
# 端末を1つずつ使用不能にしている。BT1/BT2/BT3 は汚染済み。汚染前の端末だけを使う。
# 症状: 端末ログに "LiveUpdate failed to create copy ... [32]" → "Terminal exit with code 0"
#       が出て、テストを実行せず約24秒で終了する。
TERMINALS = [
    ("PROD", r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"),
    ("BT4", r"C:\Program Files\OANDA MetaTrader 5_BT4\terminal64.exe"),
]

WINDOWS = {
    "IS":   ("2021.06.21", "2026.06.20", 60.0),
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
}

BASE = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": True,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64,
    "Oafx2LabMode": 0, "PprotMode": 0, "SxitMode": 0,
    "GszMode": 0, "GszSleeveMask": 0, "GszRiskPct": 0.0, "GszRefCap": 0.0,
}

# (ラベル, マスク, risk%, refCap, Boost適用)
CASES: list[tuple[str, int, float, float, bool]] = [("BASELINE", 0, 0.0, 0.0, True)]
for r in (0.68, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
    CASES.append((f"PB_r{r}", 1, r, 500000.0, True))
for r in (0.68, 1.0, 2.0, 3.0, 5.0):
    CASES.append((f"SCA_r{r}", 2, r, 500000.0, True))
for r in (1.0, 2.0, 3.0, 5.0):
    CASES.append((f"BOTH_r{r}", 3, r, 500000.0, True))
# 複利（equity追従）: position_sizing.md では PullbackTrend の利益3.6倍の主因
for r in (1.0, 2.0, 3.0):
    CASES.append((f"PBcomp_r{r}", 1, r, 0.0, True))
# SCA の Boost を乗せない版（Boostがリスクを二重に増やしていないかの確認）
for r in (2.0, 3.0):
    CASES.append((f"SCAnb_r{r}", 2, r, 500000.0, False))

_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    with _lock:
        print(line, flush=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def write_config(run_id, exe, mask, risk, refcap, boost, window) -> Path:
    frm, to, _ = WINDOWS[window]
    p = dict(BASE)
    if mask:
        p.update({"GszMode": 1, "GszSleeveMask": mask, "GszRiskPct": risk,
                  "GszRefCap": refcap, "GszApplyBoost": boost})
    p["ResultFileName"] = f"{run_id}_result.csv"
    p["EquityLogFile"] = f"{run_id}_deals.csv"
    lines = [f"mt5_path: {exe}", "expert: MIX_EA_OANDA_SIMVERIFY", "symbol: XAUUSD",
             "period: M15", f"from_date: {frm}", f"to_date: {to}",
             f"deposit: {DEPOSIT}", "currency: JPY", "leverage: 25",
             "model: every_tick", "parameters:"]
    for k, v in p.items():
        lines.append(f"  {k}: {'true' if v is True else 'false' if v is False else v}")
    lines += [f"report_dir: {RUN_DIR}", f"report_name: {run_id}", ""]
    path = CONFIG_DIR / f"{run_id}.yaml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def parse(run_id):
    p = RUN_DIR / run_id / "summary.csv"
    if not p.exists():
        return None
    v = {r[0]: r[1] for r in csv.reader(open(p, encoding="utf-8")) if len(r) >= 2}
    try:
        return {"net": float(v["純利益"]), "pf": float(v["プロフィットファクター"]),
                "dd_pct": float(v["最大相対DD%"]), "trades": int(float(v["総取引数"]))}
    except (KeyError, ValueError):
        return None


def sleeve_stats(path):
    """枠別の純益と平均ロット。"""
    out = {}
    if not path.exists():
        return out
    agg = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        a = agg.setdefault(m, {"net": 0.0, "lots": [], "n": 0})
        if r["entry"] == "0":
            a["lots"].append(float(r["volume"]))
            a["n"] += 1
        else:
            a["net"] += float(r["profit_jpy"])
    for m, a in agg.items():
        out[m] = {"net": a["net"], "n": a["n"],
                  "avg_lot": (sum(a["lots"]) / len(a["lots"])) if a["lots"] else 0.0}
    return out


def kill_terminal(exe):
    folder = str(Path(exe).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       timeout=120, capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def run_one(name, exe, label, mask, risk, refcap, boost, window):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"gsz_{window.lower()}_{label}_{stamp}_{uuid.uuid4().hex[:4]}"
    cfg = write_config(run_id, exe, mask, risk, refcap, boost, window)
    log(f"RUN_START {label} {window} on {name}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        log(f"RUN_TIMEOUT {label} {window}")
        kill_terminal(exe)
        return {"label": label, "window": window, "status": "FAILED"}
    v = parse(run_id)
    src = COMMON / f"{run_id}_deals.csv"
    dst = DEAL_DIR / f"{run_id}_deals.csv"
    if src.exists():
        try:
            src.replace(dst)
        except OSError:
            dst = src
    st = sleeve_stats(dst)
    kill_terminal(exe)
    row = {"label": label, "window": window, "mask": mask, "risk_pct": risk,
           "ref_cap": refcap, "boost": boost, "run_id": run_id,
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / WINDOWS[window][2], 4)
    for m, key in ((20260640, "pb"), (20261002, "sca")):
        if m in st:
            row[f"{key}_net"] = round(st[m]["net"])
            row[f"{key}_lot"] = round(st[m]["avg_lot"], 4)
            row[f"{key}_n"] = st[m]["n"]
    log(f"RUN_END {label} {window} net={row.get('net')} dd={row.get('dd_pct')} "
        f"pb_lot={row.get('pb_lot')} sca_lot={row.get('sca_lot')} {row['elapsed']}s")
    return row


def load_done() -> set:
    """成功済みの (label, window)。端末が次々に使えなくなるため再開可能にする。"""
    done = set()
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            if r.get("status") == "OK":
                done.add((r["label"], r["window"]))
    return done


def append_result(row, fields):
    exists = OUT.exists()
    with _lock:
        with open(OUT, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            if not exists:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in fields})


FIELDS = ["label", "window", "mask", "risk_pct", "ref_cap", "boost", "status",
          "net", "pf", "dd_pct", "monthly_pct", "trades",
          "pb_net", "pb_lot", "pb_n", "sca_net", "sca_lot", "sca_n",
          "elapsed", "run_id"]


def main():
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    # 前回の全滅分（status!=OK）は残さず、成功分だけを引き継ぐ
    done = load_done()
    if OUT.exists():
        keep = [r for r in csv.DictReader(open(OUT, encoding="utf-8"))
                if r.get("status") == "OK"]
        with open(OUT, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for r in keep:
                w.writerow({k: r.get(k, "") for k in FIELDS})
    jobs = [(c, w) for w in WINDOWS for c in CASES if (c[0], w) not in done]
    log(f"RESUME done={len(done)} remaining={len(jobs)}")
    work: "queue.Queue" = queue.Queue()
    for j in jobs:
        work.put(j)
    results = []
    log(f"MEASURE_START jobs={len(jobs)}")

    def worker(name, exe):
        while True:
            try:
                (label, mask, risk, refcap, boost), window = work.get_nowait()
            except queue.Empty:
                return
            try:
                r = run_one(name, exe, label, mask, risk, refcap, boost, window)
                append_result(r, FIELDS)
                with _lock:
                    results.append(r)
            finally:
                work.task_done()

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        ts = []
        for name, exe in TERMINALS:
            t = threading.Thread(target=worker, args=(name, exe), daemon=True)
            t.start()
            ts.append(t)
            time.sleep(25)
        for t in ts:
            t.join()
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    ok = sum(1 for r in results if r.get("status") == "OK")
    log(f"MEASURE_END rows={len(results)} ok={ok} -> {OUT}")


if __name__ == "__main__":
    main()
