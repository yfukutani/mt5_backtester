# -*- coding: utf-8 -*-
"""OANDA FX DD低減ラウンド1の最終判定。

【重要な検証】DDが下がった案の多くでOOS利益が6割以上落ちていた。これは
「DDが下がった」のではなく「取引しなくなった」可能性がある。取引しなければ
DDは出ないので、取引数を必ず確認して枠停止と改善を区別する。

【重複排除】パラメータ違いが結果に効かない案が多いため、(IS指標,OOS指標)で束ねる。
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "oafx_dd"

IS_BASE = {"net": 277106.0, "pf": 1.3945, "dd": 35.6479, "n": 1573}
OOS_BASE = {"net": 390740.0, "pf": 1.3163, "dd": 30.7523, "n": 2926}


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


rows = list(csv.DictReader(open(ROOT / "results.csv", encoding="utf-8-sig")))
props = {r["id"]: r for r in csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8-sig"))}

by = defaultdict(dict)
for r in rows:
    if r.get("status") != "OK" or f(r.get("net")) is None:
        continue
    pid = r.get("proposal_id", "")
    if pid.startswith("OAFX"):
        by[pid][r["window"]] = r

complete = {p: w for p, w in by.items() if "IS" in w and "OOS" in w}
print("実装対象900案中、IS/OOS両方の実測が揃った案: %d" % len(complete))

groups = defaultdict(list)
for pid, w in complete.items():
    key = (round(f(w["IS"]["net"]), 1), round(f(w["IS"]["dd_pct"]), 4),
           round(f(w["OOS"]["net"]), 1), round(f(w["OOS"]["dd_pct"]), 4))
    groups[key].append(pid)
print("重複排除後のユニークな効果: %d\n" % len(groups))

recs = []
for pids in groups.values():
    w = complete[sorted(pids)[0]]
    i, o = w["IS"], w["OOS"]
    r = {
        "id": sorted(pids)[0], "dup": len(pids),
        "family": props.get(sorted(pids)[0], {}).get("family", "?"),
        "is_net": f(i["net"]), "is_dd": f(i["dd_pct"]), "is_n": int(f(i["trades"]) or 0),
        "oos_net": f(o["net"]), "oos_dd": f(o["dd_pct"]), "oos_n": int(f(o["trades"]) or 0),
    }
    r["is_net_pct"] = (r["is_net"] - IS_BASE["net"]) / IS_BASE["net"] * 100
    r["oos_net_pct"] = (r["oos_net"] - OOS_BASE["net"]) / OOS_BASE["net"] * 100
    r["is_n_pct"] = (r["is_n"] - IS_BASE["n"]) / IS_BASE["n"] * 100
    r["oos_n_pct"] = (r["oos_n"] - OOS_BASE["n"]) / OOS_BASE["n"] * 100
    r["both_under30"] = r["is_dd"] < 30.0 and r["oos_dd"] < 30.0
    r["dd_down"] = r["is_dd"] < IS_BASE["dd"] and r["oos_dd"] < OOS_BASE["dd"]
    # 取引数が3割以上減った案は「枠停止に近い」として区別する
    r["trade_collapse"] = r["is_n_pct"] < -30 or r["oos_n_pct"] < -30
    recs.append(r)

print("===== 両期間でDD30%%未満、かつ取引が崩壊していない案 =====")
best = [r for r in recs if r["both_under30"] and not r["trade_collapse"]]
if not best:
    print("該当なし\n")
else:
    for r in sorted(best, key=lambda x: x["is_dd"]):
        print("%-9s x%-2d %-26s IS[dd%6.2f 利益%+7.1f%% 取引%+6.1f%%] OOS[dd%6.2f 利益%+7.1f%% 取引%+6.1f%%]"
              % (r["id"], r["dup"], r["family"][:26], r["is_dd"], r["is_net_pct"], r["is_n_pct"],
                 r["oos_dd"], r["oos_net_pct"], r["oos_n_pct"]))

print("\n===== 両期間でDD30%%未満（取引崩壊を含む・参考）=====")
for r in sorted([x for x in recs if x["both_under30"]], key=lambda x: x["is_dd"])[:10]:
    mark = "  ⚠️取引崩壊" if r["trade_collapse"] else ""
    print("%-9s x%-2d %-26s IS[dd%6.2f 利益%+7.1f%% 取引%5d(%+6.1f%%)] OOS[dd%6.2f 利益%+7.1f%% 取引%5d(%+6.1f%%)]%s"
          % (r["id"], r["dup"], r["family"][:26], r["is_dd"], r["is_net_pct"], r["is_n"], r["is_n_pct"],
             r["oos_dd"], r["oos_net_pct"], r["oos_n"], r["oos_n_pct"], mark))

print("\n===== 両期間でDD低下かつ利益毀損10%%以内、取引崩壊なし =====")
mild = [r for r in recs if r["dd_down"] and not r["trade_collapse"]
        and r["is_net_pct"] > -10 and r["oos_net_pct"] > -10]
if not mild:
    print("該当なし")
else:
    for r in sorted(mild, key=lambda x: (x["is_dd"] + x["oos_dd"]))[:15]:
        u = " ★30%未満" if r["both_under30"] else ""
        print("%-9s x%-2d %-26s IS[dd%6.2f 利益%+7.1f%%] OOS[dd%6.2f 利益%+7.1f%%]%s"
              % (r["id"], r["dup"], r["family"][:26], r["is_dd"], r["is_net_pct"],
                 r["oos_dd"], r["oos_net_pct"], u))

print("\n===== 集計 =====")
print("  両期間DD低下            : %d" % len([r for r in recs if r["dd_down"]]))
print("  うち取引崩壊(±30%%超減)  : %d" % len([r for r in recs if r["dd_down"] and r["trade_collapse"]]))
print("  両期間DD30%%未満         : %d" % len([r for r in recs if r["both_under30"]]))
print("  うち取引崩壊なし        : %d" % len(best))
