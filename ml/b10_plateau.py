# -*- coding: utf-8 -*-
"""B10（構造TP）の台地性評価。PB_GOLDは入れ子窓なので差分で独立前半区間も復元する。"""
import csv
from collections import defaultdict
from pathlib import Path

SRC = Path(r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\s1s3\s1s3_results.csv")
D = defaultdict(dict)
for r in csv.DictReader(open(SRC, encoding="utf-8")):
    D[(r["sleeve"], r["window"])][r["variant"]] = {
        "net": float(r["net"]), "pf": float(r["pf"]), "dd": float(r["dd"]), "n": int(r["n"])}

GRID_LB = [("B10L10", "10"), ("B10L20", "20"), ("B10L30", "30"), ("B10L50", "50"),
           ("B10L80", "80"), ("B10L120", "120")]
GRID_RR = [("B10R03", "0.3"), ("B10L20", "0.5"), ("B10R07", "0.7"), ("B10R10", "1.0")]

print("=" * 100)
print("PB_GOLD: B10構造TPの台地性（全期間21-26 / 後半24-26 / 独立前半21-24＝差分復元）")
bf, bl = D[("PB_GOLD", "IS")]["BASE"], D[("PB_GOLD", "OOS")]["BASE"]
base_early = bf["net"] - bl["net"]
print("%-14s %10s %8s %6s | %10s | %10s %6s"
      % ("variant", "全期間", "PF", "DD%", "後半24-26", "独立前半", "n増減"))
print("%-14s %+10.0f %8.2f %6.1f | %+10.0f | %+10.0f %6s"
      % ("BASE", bf["net"], bf["pf"], bf["dd"], bl["net"], base_early, "-"))


def row(tag, label):
    g, gl = D[("PB_GOLD", "IS")].get(tag), D[("PB_GOLD", "OOS")].get(tag)
    if not (g and gl):
        return None
    early = g["net"] - gl["net"]
    ok_full = g["net"] >= bf["net"]
    ok_late = gl["net"] >= bl["net"]
    ok_early = early >= base_early
    mark = "**全区間改善**" if (ok_full and ok_late and ok_early) else (
        "前半悪化" if not ok_early else "一部悪化")
    print("%-14s %+10.0f %8.2f %6.1f | %+10.0f | %+10.0f %+6d  %s"
          % (label, g["net"], g["pf"], g["dd"], gl["net"], early, g["n"] - bf["n"], mark))
    return ok_full and ok_late and ok_early


print("--- スイング探索期間（MinRR=0.5固定）---")
lb_ok = [row(t, "lookback " + l) for t, l in GRID_LB]
print("--- MinRR（lookback=20固定）---")
rr_ok = [row(t, "MinRR " + l) for t, l in GRID_RR]

print()
print("台地判定: lookback %d/%d 水準・MinRR %d/%d 水準で全区間改善"
      % (sum(1 for x in lb_ok if x), len(lb_ok), sum(1 for x in rr_ok if x), len(rr_ok)))

print()
print("=" * 100)
print("PB_GBPJPY（真の独立IS/OOSを持つ対照枠）でのB10")
b_is, b_oos = D[("PB_GBPJPY", "IS")]["BASE"], D[("PB_GBPJPY", "OOS")]["BASE"]
print("%-14s %10s %10s %s" % ("variant", "IS", "OOS", "判定"))
print("%-14s %+10.0f %+10.0f %s" % ("BASE", b_is["net"], b_oos["net"], "基準"))
for t, l in GRID_LB + GRID_RR[:1] + GRID_RR[2:]:
    g_is, g_oos = D[("PB_GBPJPY", "IS")].get(t), D[("PB_GBPJPY", "OOS")].get(t)
    if not (g_is and g_oos):
        continue
    ok = g_is["net"] >= b_is["net"] and g_oos["net"] >= b_oos["net"]
    print("%-14s %+10.0f %+10.0f %s"
          % (t, g_is["net"], g_oos["net"], "**合格**" if ok else "OOS悪化" if g_oos["net"] < b_oos["net"] else "IS悪化"))
