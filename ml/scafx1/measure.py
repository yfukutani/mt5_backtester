"""SCA USDJPY/GBPJPYの第2セッション横展開を、各枠別にIS/OOSで測る。
OANDA端末が使用不能のためXM端末・XM銘柄でOANDA相当構成を用いる。
新枠の両窓純益とサンプル数を第一とし、deal由来の円建てDDは参考表示に留める。
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
ROOT = Path(__file__).resolve().parent
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
    # FULL は全案では回さない。暗号枠を有効にすると BTCUSD/ETHUSD の日足読み込みで
    # 1run 321秒かかり（GOLD単体の99秒の3倍以上）、41案×3窓では約14時間になる。
    # まず IS/OOS で絞り、FULL は上位案だけ confirm_full.py で測る。
    # "FULL": ("2016.11.09", "2026.06.20", 115.0),
}

# 【掃引は親枠＋新枠だけの最小構成で回す】
# OANDA本番相当の11枠を有効にすると多銘柄の読み込みで1run 455秒かかり、
# 71案×2窓では18時間になる。枠が純粋に加算的であることは各ラウンドで確認済みで
# （新枠を足しても既存枠の損益は1円も動かない）、掃引での第一の判定材料は
# 新枠自身の両窓純益なので、ブックを小さくしても判定は変わらない。
# フルブックでのDD文脈は上位案だけ confirm で測り直す。
# フルブック1件の実測は results_fullbook_x001.csv に退避してある。
BASE = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_BTC_FUND": False, "En_BFXREV": False,
    "En_SCA_GOLD": False, "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GoldPBHoldBars": 64,
    "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
    "GszMode": 0, "GszSleeveMask": 0,
    "Sca2Enable": True,
    "Sca2RangeStart": 13, "Sca2RangeEnd": 15,
    "Sca2TradeEnd": 20, "Sca2ForceClose": 23,
    "Sca2MinRange": 0.40, "Sca2MaxRange": 1.00, "Sca2Buffer": 0.0,
    "Sca2RR": 1.7, "Sca2SkipFriday": True,
    "Sca2RevBoost": True, "Sca2BoostMult": 2.0, "Sca2Lot": 0.01,
    "Sca3Enable": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
    "Sca4Enable": False,
    "Sca5Enable": False, "Sca6Enable": False,
    "Pb2Enable": False,
}

MAGICS = {20261000: "sca_uj", 20261001: "sca_gj", 20261006: "uj2", 20261007: "gj2", 20261002: "sca1", 20261003: "sca2", 20260640: "pb"}

# 掃引中にEAを再コンパイルすると、以降のrunだけ別バイナリで測ったことになる。
# MT5は未知のSETパラメータを黙って無視するので失敗が表に出ず、前ラウンドでは
# これで「OFFの結果を有効値だと思い込む」偽の測定を出した。開始時のSHAを固定し、
# 1runごとに突き合わせて、変わっていたら結果を残さず止める。
EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts\MIX_EA_SIMVERIFY.ex5")
_ea_sha = None


def ea_sha() -> str:
    import hashlib
    return hashlib.sha256(EA_EX5.read_bytes()).hexdigest()


class EAChanged(RuntimeError):
    pass


def check_ea() -> None:
    if ea_sha() != _ea_sha:
        raise EAChanged(f"EAバイナリが掃引中に入れ替わった: {EA_EX5}")


_lock = threading.Lock()

FIELDS = ["proposal_id", "family", "window", "status", "net", "pf", "dd_pct",
          "monthly_pct", "trades",
          "sca_uj_net", "sca_uj_n", "sca_gj_net", "sca_gj_n", "uj2_net", "uj2_n", "gj2_net", "gj2_n", "sca1_net", "sca1_n", "sca2_net", "sca2_n", "pb_net", "pb_n",
          "description", "parameter_json", "elapsed", "run_id", "deals"]


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
            a["net"] += float(r["profit"])
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
    run_id = f"fx_{window.lower()}_{prop['proposal_id']}_{stamp}_{uuid.uuid4().hex[:4]}"
    params = json.loads(prop["parameter_json"])
    check_ea()
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
           "deals": dst.name if dst.exists() else "",
           "description": prop["description"], "parameter_json": prop["parameter_json"],
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / WINDOWS[window][2], 4)
    for key in ("sca_uj", "sca_gj", "uj2", "gj2", "sca1", "sca2", "pb"):
        if key in st:
            row[f"{key}_net"] = round(st[key]["net"])
            row[f"{key}_n"] = st[key]["n"]
    log(f"RUN_END {prop['proposal_id']} {window} net={row.get('net')} "
        f"dd={row.get('dd_pct')} uj2_net={row.get('uj2_net')} "
        f"uj2_n={row.get('uj2_n')} gj2_net={row.get('gj2_net')} "
        f"gj2_n={row.get('gj2_n')} {row['elapsed']}s")
    return row


def main():
    global _ea_sha
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ea_sha = ea_sha()
    log(f"EA_SHA {_ea_sha[:16]} {EA_EX5.stat().st_size}bytes")
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
            abort = False
            try:
                prop, window = work.get_nowait()
            except queue.Empty:
                return
            try:
                r = run_one(name, exe, prop, window)
                append_result(r)
                with _lock:
                    results.append(r)
            except EAChanged as e:
                # 汚染された測定を積み増さないよう、残りを捨てて即座に降りる
                log(f"ABORT {e}")
                abort = True
            finally:
                work.task_done()
            if abort:
                while True:
                    try:
                        work.get_nowait()
                    except queue.Empty:
                        return
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
