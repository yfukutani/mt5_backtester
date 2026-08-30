"""ETH sleeve FULL-window history investigation: strictly sequential MT5 probes.

Hypothesis under test: the ETH sleeve dies not because of window LENGTH but
because the window START precedes the broker's ETHUSD history start
(2016.11.08), which makes iMA(ETHUSD,D1,...) fail at OnInit with 4805 and
leaves hTrend/hExit as INVALID_HANDLE for the entire run.

Production EAs and production configs are untouched; this only drives the
verification EA MIX_EA_SIMVERIFY with ETH as the single enabled sleeve.
"""
from __future__ import annotations

import copy
import json
import subprocess
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "eth_history_investigation"
CFG, LOG, DEALS = (ROOT / x for x in ("configs", "logs", "deals"))
EXE = REPO / "mt5bt.bat"
COMMON = Path.home() / "AppData/Roaming/MetaQuotes/Terminal/Common/Files"

BASE = {
    "mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
    "expert": "MIX_EA_SIMVERIFY", "symbol": "GOLD", "period": "M15",
    "deposit": 900, "currency": "USD", "leverage": 25, "model": "every_tick",
    "parameters": {
        "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
        "En_PB_GOLD": False, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
        "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
        "En_VBO": False, "En_ETH": True, "En_BTC_FUND": False,
        "En_BFXREV": False, "En_SCA_GOLD": False, "En_SCA_USDJPY": False,
        "En_SCA_GBPJPY": False, "FundUseWebRequest": False,
        "BfxUseWebRequest": False, "SimVerifyMode": 0, "R6GoldMode": 0,
        "R6CryptoMode": 0,
    }, "report_dir": "results",
}

# name -> (from_date, to_date, why)
PROBES = {
    # A: exact reproduction of the phase-3 FULL window.
    "a_full_0621": ("2016.06.21", "2026.06.20"),
    # B: same 10y end, start moved past the ETHUSD history start 2016.11.08.
    "b_full_1109": ("2016.11.09", "2026.06.20"),
    # C: the OOS window, single sleeve. Phase 3 claimed OOS was healthy.
    "c_oos_0621": ("2016.06.21", "2021.06.20"),
}


def mt5_busy() -> bool:
    q = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "@(Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=60)
    try:
        return int(q.stdout.strip()) > 0
    except ValueError:
        return True


def wait_idle(timeout=600) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not mt5_busy():
            return True
        time.sleep(3)
    return False


def run_one(name: str) -> dict:
    frm, to = PROBES[name]
    run = f"ethhist_{name}"
    cfg = copy.deepcopy(BASE)
    cfg.update({"from_date": frm, "to_date": to, "report_name": run})
    cfg["parameters"].update({
        "ResultFileName": run + "_result.csv",
        "EquityLogFile": run + "_deals.csv",
        "EnableOpsLog": True, "OpsLogPrefix": run + "_ops",
    })
    cp = CFG / f"{run}.yaml"
    cp.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    deal = COMMON / f"{run}_deals.csv"
    if deal.exists():
        deal.unlink()
    if not wait_idle():
        return {"probe": name, "status": "MT5_NOT_IDLE"}
    started = time.time()
    q = subprocess.run([str(EXE), "run", str(cp), "--no-charts", "--no-html"],
                       cwd=REPO, capture_output=True, text=True, timeout=3600)
    (LOG / f"{run}.log").write_text(
        f"returncode={q.returncode}\nwindow={frm}..{to}\n{q.stdout}\n{q.stderr}",
        encoding="utf-8")
    # OnDeinit writes the deal file as the tester child winds down.
    deadline = time.time() + 300
    while time.time() < deadline and not deal.exists():
        time.sleep(3)
    wait_idle()

    row = {"probe": name, "window": f"{frm}..{to}",
           "secs": round(time.time() - started, 1)}
    if not deal.exists():
        row.update({"status": "NO_DEAL_FILE", "eth_rows": 0})
        return row
    target = DEALS / deal.name
    target.write_bytes(deal.read_bytes())
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    eth = [ln for ln in lines[1:] if "20260710" in ln]
    row.update({"status": "OK", "deal_rows": len(lines) - 1, "eth_rows": len(eth),
                "first_eth": eth[0] if eth else "", "last_eth": eth[-1] if eth else ""})
    return row


def main():
    for d in (CFG, LOG, DEALS):
        d.mkdir(parents=True, exist_ok=True)
    out = ROOT / "probe_results.json"
    rows = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    done = {r["probe"] for r in rows if r.get("status") == "OK"}
    for name in PROBES:
        if name in done:
            continue
        r = run_one(name)
        rows.append(r)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(r, flush=True)


if __name__ == "__main__":
    main()
