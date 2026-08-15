# -*- coding: utf-8 -*-
"""XM5で利益増かつDD低下だった候補のIS/OOS内訳を確認する。"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
rows = [r for r in csv.DictReader(open(REPO / "ml/gold_dd/screen_results.csv", encoding="utf-8-sig"))
        if r.get("status") == "OK"]
props = {}
for r in csv.DictReader(open(REPO / "ml/gold_dd/proposals.csv", encoding="utf-8-sig")):
    pid = r.get("id") or r.get("proposal_id")
    if pid:
        props[pid] = r

for pid in ["GDD31_02", "GDD31_06", "GDD31_10", "GDD31_17", "GDD06_01", "GDD24_13", "GDD07_14"]:
    print("\n[%s] %s" % (pid, props.get(pid, {}).get("variation", "?")))
    for r in rows:
        if r["id"] == pid:
            print("  %-4s net=%+10.0f pf=%.4f dd=%8.4f%% lots=%s eth=%s"
                  % (r["window"], float(r["net_jpy"]), float(r["pf_jpy"]),
                     float(r["dd_jpy"]), r["effective_lots"], r["eth_present"]))
