"""Round 6 phase 3 step A: XM five-sleeve MT5 tests, strictly sequential."""
from __future__ import annotations

import copy
import csv
import math
import subprocess
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "round6_phase3"
CFG, LOG, DEALS = (ROOT / x for x in ("configs", "logs", "deals"))
OUT = ROOT / "step_a_results.csv"
EXE = REPO / "mt5bt.bat"
COMMON = Path.home() / "AppData/Roaming/MetaQuotes/Terminal/Common/Files"

BASE = {
    "mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
    "expert": "MIX_EA_SIMVERIFY", "symbol": "GOLD", "period": "M15",
    "deposit": 900, "currency": "USD", "leverage": 25, "model": "every_tick",
    "parameters": {
        "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
        "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
        "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
        "En_VBO": False, "En_ETH": True, "En_BTC_FUND": True,
        "En_BFXREV": True, "En_SCA_GOLD": True, "En_SCA_USDJPY": False,
        "En_SCA_GBPJPY": False, "FundUseWebRequest": False,
        "BfxUseWebRequest": False, "SimVerifyMode": 0, "R6GoldMode": 0,
    }, "report_dir": "results",
}

WINDOWS = {
    "IS": ("2021.06.21", "2026.06.20"),
    "OOS": ("2016.06.21", "2021.06.20"),
    "FULL": ("2016.06.21", "2026.06.20"),
}
# BOTH is an actual rerun. Since both gates have the same lookback/cooldown and
# D10 is a strict subset of D5, their union is exactly the D5 parameterization.
CASES = {"OFF": (0, 5.0), "D5": (1, 5.0), "D10": (1, 10.0), "BOTH": (1, 5.0)}


def converted_metrics(path: Path, deposit_jpy: float = 100000.0):
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    profits = [float(r["profit_jpy"]) for r in rows]
    win, loss = sum(x for x in profits if x > 0), -sum(x for x in profits if x < 0)
    bal = peak = deposit_jpy
    max_dd = 0.0
    for p in profits:
        bal += p; peak = max(peak, bal); max_dd = max(max_dd, peak - bal)
    net = sum(profits)
    return {"net_jpy": net, "pf_jpy": win/loss if loss else math.inf,
            "max_dd_jpy": max_dd, "dd_jpy": max_dd/deposit_jpy*100,
            "rf": net/max_dd if max_dd else math.inf,
            "trades": sum(1 for r in rows if int(r["entry"]) != 0)}


def save(rows):
    fields = ["window","case","multiplier","status","net_jpy","pf_jpy",
              "max_dd_jpy","dd_jpy","rf","trades"]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def run_one(window: str, case: str, multiplier: int = 1):
    mode, drop = CASES[case]
    run = f"r6p3_xm5_{window.lower()}_{case.lower()}_x{multiplier}"
    cfg = copy.deepcopy(BASE)
    cfg.update({"from_date": WINDOWS[window][0], "to_date": WINDOWS[window][1],
                "report_name": run})
    cfg["parameters"].update({"R6CryptoMode": mode, "R6CryptoLookbackDays": 1,
        "R6CryptoCooldownDays": 3, "R6CryptoShockPct": drop,
        "GlobalLotMult": float(multiplier), "ResultFileName": run+"_result.csv",
        "EquityLogFile": run+"_deals.csv", "EnableOpsLog": True,
        "OpsLogPrefix": run+"_ops"})
    cp = CFG / f"{run}.yaml"
    cp.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    deal = COMMON / f"{run}_deals.csv"
    if not deal.exists():
        q = subprocess.run([str(EXE), "run", str(cp), "--no-charts", "--no-html"],
                           cwd=REPO, capture_output=True, text=True, timeout=3600)
        (LOG/f"{run}.log").write_text(
            f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}", encoding="utf-8")
        # With a live XM terminal already resident, terminal64 returns control
        # while the tester is still active. The EA writes this file only from
        # OnTester after the run, so it is the serialization/completion signal.
        deadline = time.time() + 3600
        while time.time() < deadline and not deal.exists(): time.sleep(5)
    if not deal.exists():
        return {"window":window,"case":case,"multiplier":multiplier,"status":"FAILED"}
    target = DEALS / deal.name
    target.write_bytes(deal.read_bytes())
    return {"window":window,"case":case,"multiplier":multiplier,"status":"OK",
            **converted_metrics(target)}


def main():
    for d in (CFG, LOG, DEALS): d.mkdir(parents=True, exist_ok=True)
    rows = []
    # OFF is always first: this is the required no-op equivalence checkpoint.
    for case in CASES:
        for window in WINDOWS:
            row = run_one(window, case); rows.append(row); save(rows); print(row, flush=True)
    # If a candidate's measured full-window DD is below 30%, measure integer
    # multipliers until the first failure; never infer the boundary linearly.
    passing = [r for r in rows if r["window"]=="FULL" and r["case"]!="OFF"
               and r["status"]=="OK" and r["dd_jpy"] < 30]
    for base in passing:
        for mult in range(2, 11):
            row = run_one("FULL", base["case"], mult); rows.append(row); save(rows); print(row, flush=True)
            if row["status"] != "OK" or row["dd_jpy"] > 30: break


if __name__ == "__main__": main()
