# -*- coding: utf-8 -*-
"""EMA25/60採用後、構造TPが実際に効いているか（ON/OFFで差が出るか）を確認する。"""
import copy
import csv
import subprocess
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "adopt3" / "cfg"
WORK.mkdir(parents=True, exist_ok=True)
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}


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


def run_case(name, overrides, win):
    run = "%s_%s" % (name, win)
    r = summary(run)
    if r is not None:
        return r
    with (REPO / "configs/pullback_gbpjpy_h4.yaml").open(encoding="utf-8") as fh:
        cfg = copy.deepcopy(yaml.safe_load(fh))
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


for name, ov in [("PBG_ema2560_structOFF", {"UseStructureTP": False}),
                 ("PBG_ema2560_structON", {"UseStructureTP": True}),
                 ("PBG_ema2560_structON_lb50", {"UseStructureTP": True, "StructureLookback": 50}),
                 ("PBG_ema2560_structON_rr0.5", {"UseStructureTP": True, "StructureMinRR": 0.5})]:
    for win in ("IS", "OOS"):
        r = run_case(name, ov, win)
        print("%-30s %-4s %s" % (name, win,
              ("net=%+9.0f pf=%.3f dd=%.2f%% n=%d" % (r["net"], r["pf"], r["dd"], r["n"])) if r else "FAIL"),
              flush=True)
