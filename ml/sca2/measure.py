"""SCA GOLD 第2セッションの掃引ドライバ（XM端末・直列・再開可能）。

【端末】OANDA 5端末は MT5 の LiveUpdate（6140→6180）に捕まり使用不能。
XM端末は先に 6180 へ更新済みでクリーンなのでそちらを使う。

【チャート銘柄】USDJPY にする。GOLD にすると JPY建て口座の通貨換算に XAUJPY が要り、
XMの XAUJPY 履歴が 2025.09.17 以降しかないため OOS 期間が no history data で落ちる
（GOLD 自体は 2008.02.19 から揃っている）。

【判定】第2セッション枠（magic 20261003）だけを見ても意味がない。GOLD 3枠の合計
（PB GOLD + SCA GOLD第1 + SCA GOLD第2）で純益とDDがどう動くかで見る。
取引が増えればDDも増えるのが自然なので、固定ロットの倍率を上げた場合と同じ
効率（純益倍率 ÷ DD倍率）で比較する。1.0 を超えなければ、倍率を上げるほうが得。
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
ROOT = REPO / "ml" / "sca2"
RUN_DIR = ROOT / "runs"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "run_deals"
PROPOSALS = ROOT / "proposals.csv"
OUT = ROOT / "results.csv"
LOG = ROOT / "measure.log"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")

DEPOSIT = 500000
RUN_TIMEOUT = 1800

TERMINALS = [
    ("XM1", r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"),
]

WINDOWS = {
    "IS":  ("2021.06.21", "2026.06.20", 60.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
}

BASE = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_BTC_FUND": False, "En_BFXREV": False,
    "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GoldPBHoldBars": 64,
    "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
    "GszMode": 0, "GszSleeveMask": 0,
    "Sca2Enable": False,
}

MAGICS = {20260640: "pb", 20261002: "sca1", 20261003: "sca2"}

_lock = threading.Lock()

FIELDS = ["proposal_id", "family", "window", "status", "net", "pf", "dd_pct",
          "monthly_pct", "trades",
          "pb_net", "pb_n", "sca1_net", "sca1_n", "sca2_net", "sca2_n",
          "description", "parameter_json", "elapsed", "run_id"]


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    with _lock:
        print(line, flush=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def write_config(run_id, exe, params, window) -> Path:
    frm, to, _ = WINDOWS[window]
    p = dict(BASE)
    p.update(params)
    p["ResultFileName"] = f"{run_id}_result.csv"
    p["EquityLogFile"] = f"{run_id}_deals.csv"
    lines = [f"mt5_path: {exe}", "expert: MIX_EA_SIMVERIFY", "symbol: USDJPY",
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
    out = {}
    if not path.exists():
        return out
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        key = MAGICS.get(m)
        if key is None:
            continue
        a = out.setdefault(key, {"net": 0.0, "n": 0})
        if r["entry"] == "0":
            a["n"] += 1
        else:
            a["net"] += float(r["profit_jpy"])
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


def append_result(row):
    exists = OUT.exists()
    with _lock:
        with open(OUT, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if not exists:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in FIELDS})


def load_done():
    done = set()
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            if r.get("status") == "OK":
                done.add((r["proposal_id"], r["window"]))
    return done


def run_one(name, exe, prop, window):
    import json
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"s2_{window.lower()}_{prop['proposal_id']}_{stamp}_{uuid.uuid4().hex[:4]}"
    params = json.loads(prop["parameter_json"])
    cfg = write_config(run_id, exe, params, window)
    log(f"RUN_START {prop['proposal_id']} {window} [{prop['family']}]")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        log(f"RUN_TIMEOUT {prop['proposal_id']} {window}")
        kill_terminal(exe)
        return {"proposal_id": prop["proposal_id"], "family": prop["family"],
                "window": window, "status": "FAILED"}
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
    row = {"proposal_id": prop["proposal_id"], "family": prop["family"],
           "window": window, "run_id": run_id,
           "description": prop["description"], "parameter_json": prop["parameter_json"],
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / WINDOWS[window][2], 4)
    for key in ("pb", "sca1", "sca2"):
        if key in st:
            row[f"{key}_net"] = round(st[key]["net"])
            row[f"{key}_n"] = st[key]["n"]
    log(f"RUN_END {prop['proposal_id']} {window} net={row.get('net')} "
        f"dd={row.get('dd_pct')} sca2_n={row.get('sca2_n')} "
        f"sca2_net={row.get('sca2_net')} {row['elapsed']}s")
    return row


def main():
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    props = list(csv.DictReader(open(PROPOSALS, encoding="utf-8")))
    done = load_done()
    jobs = [(p, w) for w in WINDOWS for p in props if (p["proposal_id"], w) not in done]
    log(f"MEASURE_START proposals={len(props)} remaining={len(jobs)} done={len(done)}")

    work: "queue.Queue" = queue.Queue()
    for j in jobs:
        work.put(j)
    results = []

    def worker(name, exe):
        while True:
            try:
                prop, window = work.get_nowait()
            except queue.Empty:
                return
            try:
                r = run_one(name, exe, prop, window)
                append_result(r)
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
