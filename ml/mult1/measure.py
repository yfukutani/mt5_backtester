"""第2＋第3セッションを入れたことで、同じDD予算でどこまで倍率を上げられるかを測る。

【なぜ測るか】第3セッションの確定測定で、フルブックのISドローダウンが
**絶対値で下がった**（5.457% → 5.218%、docs/sca_gold_third_session_20260906.md §5）。
現行の「x4推奨」は第2・第3が無い前提の数字なので、DDが下がったぶん倍率に
回せるはずである。新しい施策で利益を足すより、こちらのほうが規模が大きい。

【なぜ x1 だけ測れば足りるか】全枠が固定ロット（useRisk=false）なので、
各取引の円建て損益は倍率に正比例する。したがって x1 の deal ログを n 倍すれば
任意の倍率の資産曲線と円建てDDが得られる。ただし証拠金が効き始めると
線形性が崩れるので、x4 と x8 を実測して線形性そのものを検証する。

【なぜ%ではなく円で見るか】MT5の最大相対DD%は「その時点の残高」に対する比率。
固定ロットで残高が増えていくブックでは、後半の落ち込みほど%が小さく出る。
新規に入金50万で始める人の危険度は「入金額に対する円建ての落ち込み」で見るべき。
（docs/deploy50_recheck_20260905.md で確立した見方）
"""
from __future__ import annotations

import csv
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / "runs"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "run_deals"
OUT = ROOT / "results.csv"
LOG = ROOT / "measure.log"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
EXE = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

DEPOSIT = 500000
RUN_TIMEOUT = 3600

WINDOWS = {
    "IS":   ("2021.06.21", "2026.06.20", 60.0),
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}

# XM本番構成（GOLD 2枠＋暗号3枠）
BOOK = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True,
    "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GoldPBHoldBars": 64, "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
    "GszMode": 0, "GszSleeveMask": 0,
    "Pb2Enable": False, "Sca4Enable": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
}

# 採用済みの第2セッション（S2046）と第3セッション（S3018）
SESSIONS_ON = {
    "Sca2Enable": True, "Sca2RangeStart": 13, "Sca2RangeEnd": 15,
    "Sca2TradeEnd": 20, "Sca2ForceClose": 23,
    "Sca2MinRange": 0.40, "Sca2MaxRange": 1.00, "Sca2Buffer": 0.0,
    "Sca2RR": 1.7, "Sca2SkipFriday": True, "Sca2RevBoost": True,
    "Sca2BoostMult": 2.0, "Sca2Lot": 0.01,
    "Sca3Enable": True, "Sca3RangeStart": 9, "Sca3RangeEnd": 11,
    "Sca3TradeEnd": 17, "Sca3ForceClose": 23,
    "Sca3MinRange": 0.40, "Sca3MaxRange": 1.00, "Sca3Buffer": 0.0,
    "Sca3RR": 1.7, "Sca3SkipFriday": True, "Sca3RevBoost": True,
    "Sca3BoostMult": 2.0, "Sca3Lot": 0.01,
}
SESSIONS_OFF = {"Sca2Enable": False, "Sca3Enable": False}

EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts\MIX_EA_SIMVERIFY.ex5")
_ea_sha = None


def ea_sha() -> str:
    import hashlib
    return hashlib.sha256(EA_EX5.read_bytes()).hexdigest()


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


def run(label, sessions, mult, window):
    if ea_sha() != _ea_sha:
        raise RuntimeError("EAバイナリが測定中に入れ替わった")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"m1_{window.lower()}_{label}_x{mult}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(BOOK)
    p.update(sessions)
    p["GlobalLotMult"] = mult
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

    log(f"RUN_START {label} x{mult} {window}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        return {"label": label, "mult": mult, "window": window, "status": "FAILED"}

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
    kill()

    row = {"label": label, "mult": mult, "window": window, "run_id": run_id,
           "deals": dst.name if dst.exists() else "",
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / months, 4)
    log(f"RUN_END {label} x{mult} {window} net={row.get('net')} "
        f"dd%={row.get('dd_pct')} {row['elapsed']}s")
    return row


def main():
    global _ea_sha
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ea_sha = ea_sha()
    log(f"EA_SHA {_ea_sha[:16]}")

    jobs = []
    # 本体: x1 を両構成・3窓。ここから倍率曲線を解析的に出す。
    for w in ("IS", "OOS", "FULL"):
        jobs.append(("OFF", SESSIONS_OFF, 1, w))
        jobs.append(("ON", SESSIONS_ON, 1, w))
    # 線形性の検証: 証拠金が効き始めると x1 のスケーリングが崩れる。
    for m in (4, 8):
        jobs.append(("ON", SESSIONS_ON, m, "IS"))
        jobs.append(("OFF", SESSIONS_OFF, m, "IS"))

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        log(f"MULT_START jobs={len(jobs)}")
        for label, sessions, mult, window in jobs:
            results.append(run(label, sessions, mult, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = ["label", "mult", "window", "status", "net", "pf", "dd_pct",
              "monthly_pct", "trades", "deals", "elapsed", "run_id"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})
    ok = sum(1 for r in results if r.get("status") == "OK")
    log(f"MULT_END rows={len(results)} ok={ok} -> {OUT}")


if __name__ == "__main__":
    main()
