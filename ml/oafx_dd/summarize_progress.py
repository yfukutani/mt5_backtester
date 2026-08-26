# -*- coding: utf-8 -*-
"""走査の途中経過を、重複を排除して要約する。

厳格改善の多くが純利益・PF・DDまで完全一致していた。パラメータ違いが結果に
効いていない重複と見られるため、(net,pf,dd)の組で束ねて実像を出す。
"""
import csv
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "oafx_dd" / "results.csv"

IS_BASE = {"net": 277106.0, "pf": 1.3945, "dd": 35.6479}
OOS_BASE = {"net": 390740.0, "pf": 1.3163, "dd": 30.7523}


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))]
props = {}
for r in csv.DictReader(open(REPO / "ml/oafx_dd/proposals.csv", encoding="utf-8-sig")):
    props[r["id"]] = r

# 案ごとに window -> 実測
by = defaultdict(dict)
for r in rows:
    if r.get("status") != "OK" or f(r.get("net")) is None:
        continue
    pid = r.get("proposal_id", "")
    if not pid.startswith("OAFX"):
        continue
    by[pid][r["window"]] = r

complete = {p: w for p, w in by.items() if "IS" in w and "OOS" in w}
print("IS/OOS両方が揃った案: %d" % len(complete))

# 重複を (IS指標, OOS指標) で束ねる
groups = defaultdict(list)
for pid, w in complete.items():
    key = (round(f(w["IS"]["net"]), 1), round(f(w["IS"]["dd_pct"]), 4),
           round(f(w["OOS"]["net"]), 1), round(f(w["OOS"]["dd_pct"]), 4))
    groups[key].append(pid)

print("重複排除後のユニークな効果: %d\n" % len(groups))

recs = []
for key, pids in groups.items():
    w = complete[pids[0]]
    i, o = w["IS"], w["OOS"]
    rec = {
        "pids": sorted(pids), "n": len(pids),
        "family": props.get(pids[0], {}).get("family", "?"),
        "is_net": f(i["net"]), "is_pf": f(i["pf"]), "is_dd": f(i["dd_pct"]),
        "oos_net": f(o["net"]), "oos_pf": f(o["pf"]), "oos_dd": f(o["dd_pct"]),
    }
    rec["is_dd_drop"] = IS_BASE["dd"] - rec["is_dd"]
    rec["oos_dd_drop"] = OOS_BASE["dd"] - rec["oos_dd"]
    rec["is_net_pct"] = (rec["is_net"] - IS_BASE["net"]) / IS_BASE["net"] * 100
    rec["oos_net_pct"] = (rec["oos_net"] - OOS_BASE["net"]) / OOS_BASE["net"] * 100
    rec["both_under30"] = rec["is_dd"] < 30.0 and rec["oos_dd"] < 30.0
    recs.append(rec)

both = [r for r in recs if r["both_under30"]]
print("===== 両期間でDD30%%未満: %d件 =====" % len(both))
for r in sorted(both, key=lambda x: x["is_dd"]):
    print("%-10s x%-2d %-24s IS[net%+8.1f%% dd%6.2f(%+5.2f)] OOS[net%+8.1f%% dd%6.2f(%+5.2f)]"
          % (r["pids"][0], r["n"], r["family"][:24],
             r["is_net_pct"], r["is_dd"], -r["is_dd_drop"],
             r["oos_net_pct"], r["oos_dd"], -r["oos_dd_drop"]))

print("\n===== 両期間でDD低下（30%%未満は未達を含む）上位12 =====")
down = [r for r in recs if r["is_dd_drop"] > 0 and r["oos_dd_drop"] > 0]
for r in sorted(down, key=lambda x: -(x["is_dd_drop"] + x["oos_dd_drop"]))[:12]:
    mark = " ★30%未満" if r["both_under30"] else ""
    print("%-10s x%-2d %-24s IS dd%6.2f(%+5.2f) net%+7.1f%% | OOS dd%6.2f(%+5.2f) net%+7.1f%%%s"
          % (r["pids"][0], r["n"], r["family"][:24],
             r["is_dd"], -r["is_dd_drop"], r["is_net_pct"],
             r["oos_dd"], -r["oos_dd_drop"], r["oos_net_pct"], mark))

fam = defaultdict(int)
for r in recs:
    fam[r["family"]] += 1
print("\n===== ユニーク効果のファミリー内訳 =====")
for k, v in sorted(fam.items(), key=lambda kv: -kv[1]):
    print("  %-30s %d" % (k, v))
