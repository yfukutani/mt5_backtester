"""有力案を基準と同一セッションで測り直して確定させる。

【なぜ必要か】MT5テスターは現在のスワップ率を全履歴に一律適用するため、測定日が違うと
同じ取引でも損益が動く（docs/sca_gold_exit_20260904.md §4 で最大6%の実測）。
掃引は数時間かけて回すので、その中でも基準がずれうる。採否を決める数値は
基準と候補を連続して測り、その中だけで比較する。

あわせてフルブック（GOLD 3枠だけでなく全枠）でも測り、他の枠に影響が出ないかを見る。
"""
from __future__ import annotations

import csv
import json
import subprocess
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "sca2"
RUN_DIR = ROOT / "confirm_runs"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "run_deals"
OUT = ROOT / "confirm_results.csv"
LOG = ROOT / "confirm.log"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
EXE = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

DEPOSIT = 500000
RUN_TIMEOUT = 2400
CANDIDATES = ["S2046", "S2047", "S2057"]

WINDOWS = {"IS": ("2021.06.21", "2026.06.20", 60.0),
           "OOS": ("2016.11.09", "2021.06.20", 55.0)}

GOLD_ONLY = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_BTC_FUND": False, "En_BFXREV": False,
    "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
}
# フルブック（XM本番構成: GOLD 2枠＋暗号3枠）
FULL_BOOK = dict(GOLD_ONLY)
FULL_BOOK.update({"En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True})

COMMON_PARAMS = {
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GoldPBHoldBars": 64, "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
    "GszMode": 0, "GszSleeveMask": 0,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
}
MAG = {20260640: "pb", 20261002: "sca1", 20261003: "sca2"}


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def kill():
    folder = str(Path(EXE).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   timeout=120, capture_output=True)


def run(label, book, params, window):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"cf_{window.lower()}_{label}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(book)
    p.update(COMMON_PARAMS)
    p.update(params)
    p["ResultFileName"] = f"{run_id}_result.csv"
    p["EquityLogFile"] = f"{run_id}_deals.csv"
    frm, to, months = WINDOWS[window]
    lines = [f"mt5_path: {EXE}", "expert: MIX_EA_SIMVERIFY", "symbol: USDJPY",
             "period: M15", f"from_date: {frm}", f"to_date: {to}",
             f"deposit: {DEPOSIT}", "currency: JPY", "leverage: 25",
             "model: every_tick", "parameters:"]
    for k, v in p.items():
        lines.append(f"  {k}: {'true' if v is True else 'false' if v is False else v}")
    lines += [f"report_dir: {RUN_DIR}", f"report_name: {run_id}", ""]
    cfg = CONFIG_DIR / f"{run_id}.yaml"
    cfg.write_text("\n".join(lines), encoding="utf-8")

    log(f"RUN_START {label} {window}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        return {"label": label, "window": window, "status": "FAILED"}

    sp = RUN_DIR / run_id / "summary.csv"
    v = None
    if sp.exists():
        d = {r[0]: r[1] for r in csv.reader(open(sp, encoding="utf-8")) if len(r) >= 2}
        try:
            v = {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                 "dd_pct": float(d["最大相対DD%"]), "trades": int(float(d["総取引数"]))}
        except (KeyError, ValueError):
            v = None

    src = COMMON / f"{run_id}_deals.csv"
    dst = DEAL_DIR / f"{run_id}_deals.csv"
    if src.exists():
        try:
            src.replace(dst)
        except OSError:
            dst = src
    st = defaultdict(lambda: {"net": 0.0, "n": 0})
    if dst.exists():
        for r in csv.DictReader(open(dst, encoding="utf-8")):
            k = MAG.get(int(r["magic"]))
            if k is None:
                continue
            if r["entry"] == "0":
                st[k]["n"] += 1
            else:
                st[k]["net"] += float(r["profit"])
    kill()

    row = {"label": label, "window": window, "run_id": run_id,
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / months, 4)
    for k in ("pb", "sca1", "sca2"):
        row[f"{k}_net"] = round(st[k]["net"]) if k in st else ""
        row[f"{k}_n"] = st[k]["n"] if k in st else ""
    log(f"RUN_END {label} {window} net={row.get('net')} dd={row.get('dd_pct')} "
        f"sca2={row.get('sca2_net')} {row['elapsed']}s")
    return row


def main():
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    props = {r["proposal_id"]: r for r in
             csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8"))}

    jobs = []
    for w in ("IS", "OOS"):
        jobs.append(("BASELINE", GOLD_ONLY, {"Sca2Enable": False}, w))
        for pid in CANDIDATES:
            jobs.append((pid, GOLD_ONLY, json.loads(props[pid]["parameter_json"]), w))
        # フルブック（暗号3枠込み）でも基準と最有力案を測る
        jobs.append(("FULL_BASE", FULL_BOOK, {"Sca2Enable": False}, w))
        jobs.append((f"FULL_{CANDIDATES[0]}", FULL_BOOK,
                     json.loads(props[CANDIDATES[0]]["parameter_json"]), w))

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        log(f"CONFIRM_START jobs={len(jobs)}")
        for label, book, params, window in jobs:
            results.append(run(label, book, params, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = ["label", "window", "status", "net", "pf", "dd_pct", "monthly_pct",
              "trades", "pb_net", "pb_n", "sca1_net", "sca1_n", "sca2_net", "sca2_n",
              "elapsed", "run_id"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})
    log(f"CONFIRM_END rows={len(results)} -> {OUT}")


if __name__ == "__main__":
    main()
