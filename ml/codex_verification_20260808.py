"""Targeted, serial backtests for docs/codex_verification_20260808.md.

This script intentionally invokes mt5bt one run at a time. Generated configs live
under results/codex_verification_20260808/cfg and never modify production YAMLs.
"""
import copy
import csv
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
ROOT = REPO / "results" / "codex_verification_20260808"
CFG = ROOT / "cfg"
CFG.mkdir(parents=True, exist_ok=True)


def load_yaml(relative):
    with (REPO / relative).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def read_summary(run_name):
    path = REPO / "results" / run_name / "summary.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as fh:
        values = {row[0]: row[1] for row in csv.reader(fh) if len(row) >= 2}
    try:
        return {
            "net": float(values["純利益"]),
            "pf": float(values["プロフィットファクター"]),
            "dd": float(values["最大相対DD%"]),
            "trades": int(values["総取引数"]),
        }
    except (KeyError, ValueError):
        return None


def run_case(name, base_yaml, overrides, window, model):
    run_name = f"CV260808_{name}_{window}"
    existing = read_summary(run_name)
    if existing is not None:
        return existing
    cfg = copy.deepcopy(load_yaml(base_yaml))
    cfg["from_date"], cfg["to_date"] = WINDOWS[window]
    cfg["model"] = model
    cfg["report_dir"] = "results"
    cfg["report_name"] = run_name
    cfg["parameters"].update(overrides)
    cfg["parameters"]["ResultFileName"] = f"{run_name}_result.csv"
    cfg_path = CFG / f"{run_name}.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    completed = subprocess.run([MT5BT, "run", str(cfg_path)], cwd=REPO, text=True)
    result = read_summary(run_name)
    if result is None:
        print(f"FAIL {run_name} exit={completed.returncode}", flush=True)
    return result


def step1():
    rows = []
    for hour in (0, 1):
        for window in WINDOWS:
            result = run_case(f"SCA_GOLD_RangeStart{hour}", "configs/sca_gold_m15.yaml",
                              {"RangeStartHour": hour}, window, "every_tick")
            row = {"case": f"RangeStartHour={hour}", "window": window}
            if result:
                row.update(result)
            rows.append(row)
            print(row, flush=True)
    out = ROOT / "step1_results.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["case", "window", "net", "pf", "dd", "trades"])
        writer.writeheader()
        writer.writerows(rows)


def step2():
    rows = []
    cases = [("baseline", {}), ("StopOrders_fixed", {"UseStopOrders": True})]
    for case_name, overrides in cases:
        for window in WINDOWS:
            result = run_case(f"SCA_USDJPY_{case_name}", "configs/sca_usdjpy_m15.yaml",
                              overrides, window, "every_tick")
            row = {"case": case_name, "window": window}
            if result:
                row.update(result)
            rows.append(row)
            print(row, flush=True)
    out = ROOT / "step2_results.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["case", "window", "net", "pf", "dd", "trades"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("step1", "step2"):
        raise SystemExit("usage: python ml/codex_verification_20260808.py step1|step2")
    {"step1": step1, "step2": step2}[sys.argv[1]]()
