# -*- coding: utf-8 -*-
"""560案の最終判定。

基準は現行本番（RR採用＋時間帯ゲート適用後）:
  IS 2429.34 / OOS 647.28 / XM5 4242.6・DD 10.403%

厳格改善 = IS/OOS両期間で純利益・PFが向上し、DDが悪化しない。
途中のdecisionラベルではなく記録された実数値で判定し直す。
"""
import csv
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "gold_dd2" / "results.csv"
PROP = REPO / "ml" / "gold_dd" / "proposals.csv"

IS_B = {"net": 2429.34, "pf": 1.9860, "dd": 12.304}
OOS_B = {"net": 647.28, "pf": 1.4886, "dd": 12.008}
XM5_B = {"net": 4242.6, "pf": 1.9293, "dd": 10.403}


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))]
props = {}
for r in csv.DictReader(open(PROP, encoding="utf-8-sig")):
    pid = r.get("id") or r.get("proposal_id")
    if pid:
        props[pid] = r

# 同一(案, window)は最後の成功行を採用（再実行分を優先）
best = {}
for r in rows:
    if r.get("status") != "OK" or f(r.get("net")) is None:
        continue
    if r.get("decision") == "REGRESSION_PASS":
        continue
    # 枠が取引しなくなったものは成績として扱わない
    if r.get("magic_gate_pass", "").lower() in ("false", "0"):
        continue
    best[(r["proposal_id"], r["window"])] = r

by = defaultdict(dict)
for (pid, win), r in best.items():
    by[pid][win] = r

strict = []
for pid, w in by.items():
    if "IS" not in w or "OOS" not in w:
        continue
    i, o = w["IS"], w["OOS"]
    inet, ipf, idd = f(i["net"]), f(i["pf"]), f(i["dd_pct"])
    onet, opf, odd = f(o["net"]), f(o["pf"]), f(o["dd_pct"])
    if None in (inet, ipf, idd, onet, opf, odd):
        continue
    if (inet > IS_B["net"] and ipf > IS_B["pf"] and idd <= IS_B["dd"] and
            onet > OOS_B["net"] and opf > OOS_B["pf"] and odd <= OOS_B["dd"]):
        strict.append({"id": pid, "family": i["family"], "is": (inet, ipf, idd),
                       "oos": (onet, opf, odd), "xm5": w.get("XM5"),
                       "var": props.get(pid, {}).get("variation", "?")})

print("基準 IS  net=%.2f pf=%.4f dd=%.3f" % (IS_B["net"], IS_B["pf"], IS_B["dd"]))
print("基準 OOS net=%.2f pf=%.4f dd=%.3f" % (OOS_B["net"], OOS_B["pf"], OOS_B["dd"]))
print("基準 XM5 net=%.1f pf=%.4f dd=%.3f" % (XM5_B["net"], XM5_B["pf"], XM5_B["dd"]))
print("\n両期間の実測が揃った案: %d / 厳格改善: %d"
      % (len([1 for w in by.values() if "IS" in w and "OOS" in w]), len(strict)))

# XM5まで到達した厳格改善を、XM5純利益の降順で
withx = [r for r in strict if r["xm5"]]
without = [r for r in strict if not r["xm5"]]
withx.sort(key=lambda r: -f(r["xm5"]["net"]))

print("\n===== 厳格改善（XM5実測あり）: %d件 =====" % len(withx))
for r in withx:
    x = r["xm5"]
    inet, ipf, idd = r["is"]
    onet, opf, odd = r["oos"]
    print("%-9s %-24s %-22s\n          IS %8.1f(%+6.1f) pf%.4f dd%6.3f | OOS %7.1f(%+6.1f) pf%.4f dd%6.3f"
          "\n          XM5 %7.1f(%+6.1f / %+5.2f%%) pf%.4f dd%6.3f(%+6.3f)"
          % (r["id"], r["family"], r["var"][:22],
             inet, inet - IS_B["net"], ipf, idd, onet, onet - OOS_B["net"], opf, odd,
             f(x["net"]), f(x["net"]) - XM5_B["net"],
             100.0 * (f(x["net"]) - XM5_B["net"]) / XM5_B["net"],
             f(x["pf"]), f(x["dd_pct"]), f(x["dd_pct"]) - XM5_B["dd"]))

print("\n===== 厳格改善（XM5未実行）: %d件 =====" % len(without))
for r in sorted(without, key=lambda r: -r["oos"][0])[:10]:
    print("%-9s %-24s %-20s IS %8.1f OOS %7.1f"
          % (r["id"], r["family"], r["var"][:20], r["is"][0], r["oos"][0]))

fam = defaultdict(int)
for r in strict:
    fam[r["family"]] += 1
print("\n===== 厳格改善のファミリー内訳 =====")
for k, v in sorted(fam.items(), key=lambda kv: -kv[1]):
    print("  %-26s %d" % (k, v))
