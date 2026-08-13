"""Round 6 phase 3: actual MT5 sleeve decomposition, strictly sequential."""
from __future__ import annotations

import copy
import csv
import subprocess
import time
from pathlib import Path

import yaml

from run_step_a import BASE, COMMON, DEALS, LOG, CFG, EXE, REPO, WINDOWS, converted_metrics

OUT = Path(__file__).with_name("decomposition_results.csv")

ENABLE_KEYS = (
    "En_PB_GOLD", "En_SCA_GOLD", "En_ETH", "En_BTC_FUND", "En_BFXREV"
)
VARIANTS = {
    "GOLD2": ("En_PB_GOLD", "En_SCA_GOLD"),
    "CRYPTO3_OFF": ("En_ETH", "En_BTC_FUND", "En_BFXREV"),
    "CRYPTO3_D10": ("En_ETH", "En_BTC_FUND", "En_BFXREV"),
    "CRYPTO3_D10_X2": ("En_ETH", "En_BTC_FUND", "En_BFXREV"),
    "PB_GOLD": ("En_PB_GOLD",),
    "SCA_GOLD": ("En_SCA_GOLD",),
    "ETH": ("En_ETH",),
    "BTC_FUND": ("En_BTC_FUND",),
    "BFXREV": ("En_BFXREV",),
}


def mt5_processes_running():
    q = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "@(Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return int(q.stdout.strip()) > 0
    except ValueError:
        return True


def wait_mt5_idle(timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not mt5_processes_running():
            return True
        time.sleep(2)
    return False


def load_rows():
    if not OUT.exists():
        return []
    return list(csv.DictReader(OUT.open(encoding="utf-8", newline="")))


def save(rows):
    fields = ["window", "variant", "status", "net_jpy", "pf_jpy", "max_dd_jpy",
              "dd_jpy", "rf", "trades", "months", "monthly_simple_pct"]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def run_one(window, variant):
    run = f"r6p3_decomp_{window.lower()}_{variant.lower()}"
    cfg = copy.deepcopy(BASE)
    cfg.update({"from_date": WINDOWS[window][0], "to_date": WINDOWS[window][1],
                "report_name": run})
    enabled = set(VARIANTS[variant])
    for key in ENABLE_KEYS:
        cfg["parameters"][key] = key in enabled
    cfg["parameters"].update({
        "R6CryptoMode": 1 if variant.startswith("CRYPTO3_D10") else 0,
        "R6CryptoLookbackDays": 1, "R6CryptoCooldownDays": 3,
        "R6CryptoShockPct": 10.0, "ResultFileName": run + "_result.csv",
        "EquityLogFile": run + "_deals.csv", "EnableOpsLog": True,
        "OpsLogPrefix": run + "_ops",
    })
    if variant.endswith("_X2"):
        cfg["parameters"]["GlobalLotMult"] = 2.0
    cp = CFG / f"{run}.yaml"
    cp.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    deal = COMMON / f"{run}_deals.csv"
    if not deal.exists():
        if not wait_mt5_idle():
            return {"window": window, "variant": variant, "status": "MT5_NOT_IDLE"}
        q = subprocess.run([str(EXE), "run", str(cp), "--no-charts", "--no-html"],
                           cwd=REPO, capture_output=True, text=True, timeout=3600)
        (LOG / f"{run}.log").write_text(
            f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}", encoding="utf-8")
        deadline = time.time() + 3600
        while time.time() < deadline and not deal.exists():
            time.sleep(5)
    base = {"window": window, "variant": variant,
            "status": "OK" if deal.exists() else "FAILED"}
    if not deal.exists():
        return base
    target = DEALS / deal.name
    target.write_bytes(deal.read_bytes())
    # OnTester writes the deal file just before the tester child exits. Do not
    # start the next run while that child is still winding down.
    if not wait_mt5_idle():
        return {"window": window, "variant": variant, "status": "MT5_NOT_IDLE"}
    metrics = converted_metrics(target)
    months = 120 if window == "FULL" else 60
    return {**base, **metrics, "months": months,
            "monthly_simple_pct": metrics["net_jpy"] / 100000.0 / months * 100.0}


def main():
    for d in (CFG, LOG, DEALS): d.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    done = {(r["window"], r["variant"]) for r in rows if r["status"] == "OK"}
    # Group attribution gets both protocol gates and FULL; individual attribution
    # uses FULL because the requested contribution is to the observed FULL DD.
    jobs = [(w, v) for v in ("GOLD2", "CRYPTO3_OFF", "CRYPTO3_D10") for w in WINDOWS]
    jobs += [("FULL", v) for v in ("PB_GOLD", "SCA_GOLD", "ETH", "BTC_FUND", "BFXREV")]
    jobs += [(w, "CRYPTO3_D10_X2") for w in ("IS", "OOS")]
    for window, variant in jobs:
        if (window, variant) in done:
            continue
        row = run_one(window, variant); rows.append(row); save(rows); print(row, flush=True)


if __name__ == "__main__":
    main()
