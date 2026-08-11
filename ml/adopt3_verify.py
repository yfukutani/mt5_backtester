# -*- coding: utf-8 -*-
"""①②③採用後の単体EA検証 + MIX_EA回帰。

①PB GBPJPY EMA25/60  ②PB GBPJPY 構造TP(LB30/MinRR1.5)  ③SCA GBPJPY Boost4.0
本番yaml（採用後の値）そのままでIS/OOSを測り、採用前の記録値と突き合わせる。
"""
import copy
import csv
import subprocess
import sys
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "adopt3" / "cfg"
WORK.mkdir(parents=True, exist_ok=True)
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}

CASES = [
    ("PB_GBPJPY_adopted", "configs/pullback_gbpjpy_h4.yaml", None),
    ("SCA_GBPJPY_adopted", "configs/sca_gbpjpy_m15.yaml", None),
]


def summary(run):
    f = REPO / "results" / run / "summary.csv"
    if not f.exists():
        return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


def run_case(name, base, overrides, win):
    run = "%s_%s" % (name, win)
    r = summary(run)
    if r is not None:
        return r
    with (REPO / base).open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg = copy.deepcopy(cfg)
    if overrides:
        cfg["parameters"].update(overrides)
    cfg["from_date"], cfg["to_date"] = WINDOWS[win]
    cfg["report_dir"] = "results"
    cfg["report_name"] = run
    cfg["parameters"]["ResultFileName"] = run + "_r.csv"
    p = WORK / (run + ".yaml")
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    subprocess.run([MT5BT, "run", str(p)], cwd=str(REPO), capture_output=True, text=True, timeout=1800)
    return summary(run)


def main():
    for name, base, ov in CASES:
        for win in ("IS", "OOS"):
            r = run_case(name, base, ov, win)
            if r:
                print("%-24s %-4s net=%+9.0f pf=%.3f dd=%.2f%% n=%d"
                      % (name, win, r["net"], r["pf"], r["dd"], r["n"]), flush=True)
            else:
                print("%-24s %-4s FAIL" % (name, win), flush=True)


if __name__ == "__main__":
    main()
