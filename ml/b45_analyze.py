# -*- coding: utf-8 -*-
"""B-4/B-5スイープ結果の集計と判定ゲート適用。"""
import csv
from pathlib import Path

RES = Path(r"C:\Users\f\source\repos\mt5_backtester\results")


def load(name):
    d = {}
    with open(RES / name / "summary.csv", newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                d[row[0]] = row[1]
    return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
            "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"]),
            "win": float(d["勝率%"])}


print("=== B-4 RangeShiftLow_Pips (Boost ON) ===")
print("%6s | %9s %6s %6s %4s | %9s %6s %6s %4s | %s"
      % ("shift", "IS_net", "PF", "DD%", "n", "OOS_net", "PF", "DD%", "n", "both+"))
first_break = None
for s in range(-10, 11):
    tag = ("P%02d" % s) if s >= 0 else ("M%02d" % -s)
    i = load("B4_IS_" + tag)
    o = load("B4_OOS_" + tag)
    both = i["net"] > 0 and o["net"] > 0
    if not both and (first_break is None or abs(s) < first_break):
        first_break = abs(s)
    print("%+6d | %9.0f %6.2f %6.1f %4d | %9.0f %6.2f %6.1f %4d | %s"
          % (s, i["net"], i["pf"], i["dd"], i["n"], o["net"], o["pf"], o["dd"], o["n"],
             "OK" if both else "**NG**"))
print("両期間プラスが崩れる最小|摂動| = %s pips（判定閾値5.2pips）" % first_break)

print()
print("=== B-5 Boost_MinDrift_ATRd ===")
base_is = load("B4_IS_P00")
base_oos = load("B4_OOS_P00")
nb_is = load("B5_IS_NOBOOST")
nb_oos = load("B5_OOS_NOBOOST")
print("%8s | %9s %6s %6s | %9s %6s %6s | %8s %8s" % ("k", "IS_net", "PF", "DD%", "OOS_net", "PF", "DD%", "IS劣化", "OOS劣化"))
print("%8s | %9.0f %6.2f %6.1f | %9.0f %6.2f %6.1f | %8s %8s"
      % ("NOBOOST", nb_is["net"], nb_is["pf"], nb_is["dd"], nb_oos["net"], nb_oos["pf"], nb_oos["dd"], "-", "-"))
print("%8s | %9.0f %6.2f %6.1f | %9.0f %6.2f %6.1f | %8s %8s"
      % ("0.00", base_is["net"], base_is["pf"], base_is["dd"], base_oos["net"], base_oos["pf"], base_oos["dd"], "基準", "基準"))
for k in ("05", "10", "15", "20"):
    i = load("B5_IS_K" + k)
    o = load("B5_OOS_K" + k)
    di = (i["net"] - base_is["net"]) / base_is["net"] * 100
    do = (o["net"] - base_oos["net"]) / base_oos["net"] * 100
    ok = i["net"] > 0 and o["net"] > 0
    print("%8s | %9.0f %6.2f %6.1f | %9.0f %6.2f %6.1f | %+7.1f%% %+7.1f%% %s"
          % ("0." + k, i["net"], i["pf"], i["dd"], o["net"], o["pf"], o["dd"], di, do,
             "" if ok else "**NG**"))
print()
print("Boost寄与: IS %+d円（%+.0f%%） / OOS %+d円（NOBOOSTは赤字）"
      % (base_is["net"] - nb_is["net"], (base_is["net"] / nb_is["net"] - 1) * 100,
         base_oos["net"] - nb_oos["net"]))
