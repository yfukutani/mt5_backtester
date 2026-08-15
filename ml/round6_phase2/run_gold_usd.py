"""Round 6 phase 2: GOLD USD-account feasibility and candidate runs (sequential)."""
from __future__ import annotations

import copy
import csv
import math
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "round6_phase2"
CFG = ROOT / "configs"
LOG = ROOT / "logs"
OUT = ROOT / "gold_usd_results.csv"
EXE = REPO / "mt5bt.bat"
COMMON = Path.home() / "AppData/Roaming/MetaQuotes/Terminal/Common/Files"

BASE = {
    "mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
    "expert": "MIX_EA_SIMVERIFY", "symbol": "GOLD", "period": "H4",
    "deposit": 900, "currency": "USD", "leverage": 25, "model": "open_prices",
    "parameters": {
        "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
        "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
        "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
        "En_VBO": False, "En_ETH": False, "En_BTC_FUND": False,
        "En_BFXREV": False, "En_SCA_GOLD": False, "En_SCA_USDJPY": False,
        "En_SCA_GBPJPY": False, "FundUseWebRequest": False,
        "BfxUseWebRequest": False, "SimVerifyMode": 0,
    }, "report_dir": "results",
}

CASES = [
    ("OFF", 0, 1, 1.5, 1.0),
    ("EXIT_A0.25", 2, 1, 1.5, .25), ("EXIT_A0.3", 2, 1, 1.5, .3),
    ("EXIT_A0.35", 2, 1, 1.5, .35), ("EXIT_A0.4", 2, 1, 1.5, .4),
    ("EXIT_A0.8", 2, 1, 1.5, .8), ("EXIT_A2.0", 2, 1, 1.5, 2.0),
    ("CAUSE_L1_T0.75", 1, 1, .75, 1.0),
    ("CAUSE_L3_T1.25", 1, 3, 1.25, 1.0),
    ("CAUSE_L3_T1.5", 1, 3, 1.5, 1.0),
]

def converted_metrics(path: Path, deposit_jpy: float = 100000.0):
    deals = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    profits = [float(r["profit_jpy"]) for r in deals]
    gross_win = sum(x for x in profits if x > 0)
    gross_loss = -sum(x for x in profits if x < 0)
    bal = peak = deposit_jpy
    max_rel = 0.0
    for p in profits:
        bal += p
        peak = max(peak, bal)
        if peak > 0: max_rel = max(max_rel, (peak-bal)/peak*100)
    rates = [float(r["usdjpy"]) for r in deals if float(r["usdjpy"]) > 0]
    return {"net_jpy": sum(profits), "pf_jpy": gross_win/gross_loss if gross_loss else math.inf,
            "dd_jpy": max_rel, "deals": len(deals), "fx_min": min(rates),
            "fx_max": max(rates), "fx_mean": sum(rates)/len(rates)}

def run_one(period: str, item):
    ident, mode, lb, shock, adverse = item
    run = f"r6p2_gold_{period.lower()}_usd_{ident.lower().replace('.', 'p')}"
    cfg = copy.deepcopy(BASE)
    cfg.update({"from_date": "2021.06.21" if period == "IS" else "2016.06.21",
                "to_date": "2026.06.20" if period == "IS" else "2021.06.20",
                "report_name": run})
    cfg["parameters"].update({"R6GoldMode": mode, "R6GoldLookbackBars": lb,
        "R6GoldShockATR": shock, "R6GoldAdverseATR": adverse,
        "ResultFileName": run+"_result.csv", "EquityLogFile": run+"_deals.csv"})
    cp = CFG / (run+".yaml")
    cp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    q = subprocess.run([str(EXE), "run", str(cp), "--no-charts", "--no-html"],
                       cwd=REPO, capture_output=True, text=True, timeout=1800)
    (LOG/(run+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}", encoding="utf-8")
    deal = COMMON/(run+"_deals.csv")
    return {"period": period, "id": ident, "status": "OK" if deal.exists() else "FAILED",
            **(converted_metrics(deal) if deal.exists() else {})}

def main():
    CFG.mkdir(parents=True, exist_ok=True); LOG.mkdir(parents=True, exist_ok=True)
    rows = []
    # IS baseline must establish accounting equivalence before any OOS/candidate runs.
    rows.append(run_one("IS", CASES[0])); print(rows[-1], flush=True)
    if rows[-1]["status"] != "OK": return
    for period in ("IS", "OOS"):
        for item in (CASES[1:] if period == "IS" else CASES):
            rows.append(run_one(period, item)); print(rows[-1], flush=True)
            with OUT.open("w", encoding="utf-8", newline="") as f:
                w=csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r})); w.writeheader(); w.writerows(rows)

if __name__ == "__main__": main()
