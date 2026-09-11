"""XM本番構成＋Sca2でGOLDのrisk%・複利42案をFULL/OOS比較する。
過去の棄却を幾何平均・ピーク比DD・破綻除外で再評価するための掃引。
再開・EA差し替え検知・端末回収・スリープ抑止はfxcomp1を継承する。
"""
from __future__ import annotations

import csv
import os
import math
from generate_proposals import load_proposals, parameters
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
RUN_TIMEOUT = 5400

WINDOWS = {
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
}

# 本番との差をGSZに限定するため、mult1のBOOKをそのまま固定する。
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

# 第3は円建てDDで棄却されたため、第2の13項目だけを採用する。
BASE = {
    **BOOK,
    "Sca2Enable": True, "Sca2RangeStart": 13, "Sca2RangeEnd": 15,
    "Sca2TradeEnd": 20, "Sca2ForceClose": 23,
    "Sca2MinRange": 0.40, "Sca2MaxRange": 1.00, "Sca2Buffer": 0.0,
    "Sca2RR": 1.7, "Sca2SkipFriday": True, "Sca2RevBoost": True,
    "Sca2BoostMult": 2.0, "Sca2Lot": 0.01,
    # 比較対象外のラボが混入しないよう、無効値を固定する。
    "Sca3Enable": False, "Sca4Enable": False, "Sca5Enable": False,
    "Sca6Enable": False, "Pb2Enable": False, "ScaNewEnable": False,
    "RsiBBFlagMaxBars": 0, "RsiRSIFlagMaxBars": 0,
    "RsiResetOnMAFlip": False, "RsiConsumeWhileHeld": False, "RsiMemSleeveMask": 0,
    "FxRiskMask": 0, "FxRiskPct": 0.0, "FxRiskRefCap": 0.0,
    "GszMode": 0, "GszSleeveMask": 0, "GszRiskPct": 0.0, "GszRefCap": 0.0,
}

MAGICS = {
    20260640: "pb_gold", 20261002: "sca_gold", 20261003: "sca2",
    20260710: "eth", 20260720: "fund", 20260724: "bfx",
}

EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts\MIX_EA_SIMVERIFY.ex5")
_ea_sha = None
_baseline_trades = {}


def ea_sha() -> str:
    import hashlib
    return hashlib.sha256(EA_EX5.read_bytes()).hexdigest()


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8", newline="") as fh:
        fh.write(line + "\n")


def kill():
    folder = str(Path(EXE).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   timeout=120, capture_output=True)


def run(prop, window):
    mult = parameters(prop["parameter_json"])["GlobalLotMult"]
    if ea_sha() != _ea_sha:
        raise RuntimeError("EAバイナリが測定中に入れ替わった")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"gc_{window.lower()}_{prop['proposal_id']}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(BASE)
    p.update(parameters(prop["parameter_json"]))
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
    cfg.write_bytes("\n".join(lines).encode("utf-8"))

    log(f"RUN_START x{mult} {window}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        return {**prop, "mult": mult, "window": window, "run_id": run_id, "status": "FAILED"}

    sp = RUN_DIR / run_id / "summary.csv"
    v = None
    d = {}
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

    # 枠別も残す。倍率余力が特定の枠のDDに縛られていないかを後で見るため。
    st = {}
    deal_profit = 0.0
    if dst.exists():
        for r in csv.DictReader(open(dst, encoding="utf-8")):
            deal_profit += float(r["profit"])
            k = MAGICS.get(int(r["magic"]))
            if k is None:
                continue
            a = st.setdefault(k, {"net": 0.0, "n": 0})
            if r["entry"] == "0":
                a["n"] += 1
            else:
                a["net"] += float(r["profit"])   # JPY口座の損益をそのまま比較するため
    kill()

    row = {**prop, "mult": mult, "window": window, "run_id": run_id,
           "deals": str(dst) if dst.exists() else "",
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    row["final_balance"], row["balance_source"] = final_balance(
        d, deal_profit if dst.exists() else None)
    # 他の統計が欠けても、破綻判定の証跡を失わないため取引数を保存する。
    try:
        row["trades"] = int(float(d["総取引数"]))
    except (KeyError, ValueError):
        pass
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / months, 4)
    for k in MAGICS.values():
        row[f"{k}_net"] = round(st[k]["net"]) if k in st else ""
        row[f"{k}_n"] = st[k]["n"] if k in st else ""
    log(f"RUN_END x{mult} {window} net={row.get('net')} dd%={row.get('dd_pct')} "
        f"trades={row.get('trades')} {row['elapsed']}s")
    return row


FIELDS = (["proposal_id", "family", "description", "parameter_json",
           "mult", "window", "status", "net", "pf", "dd_pct", "monthly_pct",
           "trades", "final_balance", "balance_source", "blown", "deals", "elapsed", "run_id"]
          + [f"{k}_{s}" for k in MAGICS.values() for s in ("net", "n")])


def final_balance(summary, deal_profit):
    for key in ("最終残高", "残高", "Final Balance", "Balance", "final_balance", "balance"):
        try:
            value = float(str(summary[key]).replace(",", "").replace(" ", ""))
        except (KeyError, ValueError):
            continue
        if math.isfinite(value):
            return value, f"summary:{key}"
    # summaryに残高がなければ入金+全dealのprofitで代用する。
    # EAのprofitはスワップ・手数料込みで、入金行は含まないため二重加算しない。
    if deal_profit is not None:
        return round(DEPOSIT + deal_profit, 2), "deposit_plus_deal_profit"
    return "", "unavailable"


def mark_blown(row):
    window = row["window"]
    trades = row.get("trades")
    if row["proposal_id"] == "G001" and row["status"] == "OK" and trades is not None and trades > 0:
        _baseline_trades[window] = trades
    baseline_trades = _baseline_trades.get(window)
    if trades is not None and baseline_trades is not None:
        # 取引数減少は証拠金破綻の暫定代理指標であり、破綻そのものの確定診断ではない。
        row["blown"] = trades < baseline_trades * 0.5
    else:
        # 欠測を非破綻(False)と誤認しないよう、判定不能は空欄にする。
        row["blown"] = ""


def append_result(row):
    exists = OUT.exists() and OUT.stat().st_size > 0
    with open(OUT, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
        # 強制終了後にも完了済みrunを再利用できるよう、毎回ディスクまで保存する。
        fh.flush()
        os.fsync(fh.fileno())


def load_done(props):
    done = set()
    _baseline_trades.clear()
    expected = {p["proposal_id"]: parameters(p["parameter_json"]) for p in props}
    if OUT.exists() and OUT.stat().st_size:
        with open(OUT, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != FIELDS:
                raise ValueError("results.csvのヘッダーが一致しません")
            for r in reader:
                if r.get("proposal_id") in expected:
                    if parameters(r["parameter_json"]) != expected[r["proposal_id"]]:
                        raise ValueError("既存結果と案のパラメータが異なります")
                    path = Path(r.get("deals") or "__missing__")
                    if not path.is_absolute():
                        path = DEAL_DIR / path
                    if r.get("status") == "OK" and path.is_file():
                        if r["proposal_id"] == "G001":
                            trades = int(float(r["trades"]))
                            if trades <= 0:
                                continue
                            _baseline_trades[r["window"]] = trades
                        done.add((r["proposal_id"], r["window"]))
    return done


def main():
    global _ea_sha
    props = sorted(load_proposals(), key=lambda p: p["proposal_id"])
    done = load_done(props)
    jobs = [(p, w) for w in WINDOWS for p in props if (p["proposal_id"], w) not in done]
    if not jobs:
        print("全案・両窓が完了済みです")
        return
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ea_sha = ea_sha()
    log(f"EA_SHA {_ea_sha[:16]}")
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        log(f"GOLDCOMP_START jobs={len(jobs)} done={len(done)}")
        for prop, window in jobs:
            # G001未取得で後続を測ると、破綻を比較判定できないため中断する。
            if prop["proposal_id"] != "G001" and window not in _baseline_trades:
                raise RuntimeError(f"{window}のG001基準取引数がありません")
            row = run(prop, window)
            mark_blown(row)
            append_result(row)
            if prop["proposal_id"] == "G001" and window not in _baseline_trades:
                raise RuntimeError(f"{window}のG001取得失敗。再開時に再試行してください")
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    log(f"GOLDCOMP_END -> {OUT}")


if __name__ == "__main__":
    main()
