# -*- coding: utf-8 -*-
"""GOLD DD低減ラウンドの最終判定。

厳格改善 = IS/OOS 両期間で純利益・PFが向上し、DDが悪化しない。
DD低下候補 = 両期間でDDが下がる（利益毀損は別途記録）。
XM5枠は増レバ可否（DD30%以下）を実測値で見る。

途中の decision ラベルではなく、記録された実数値で判定し直す。
"""
import csv
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "gold_dd" / "screen_results.csv"

IS_BASE = {"net": 331176.79, "pf": 1.8718825447675405, "dd": 32.05272}
OOS_BASE = {"net": 60050.52, "pf": 1.3961922853288133, "dd": 13.80608}
XM5_BASE = {"net": 538302.83, "pf": 1.85304667671607, "dd": 35.67178}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
# 同一(id, window)が複数ある場合は最後の成功行を採用（再実行分）
best = {}
for r in rows:
    if r.get("status") != "OK":
        continue
    if num(r.get("net_jpy")) is None:
        continue
    best[(r["id"], r["window"])] = r

by_id = defaultdict(dict)
for (pid, win), r in best.items():
    by_id[pid][win] = r

strict, dd_both, tradeoff = [], [], []
for pid, w in by_id.items():
    if "IS" not in w or "OOS" not in w:
        continue
    i, o = w["IS"], w["OOS"]
    inet, ipf, idd = num(i["net_jpy"]), num(i["pf_jpy"]), num(i["dd_jpy"])
    onet, opf, odd = num(o["net_jpy"]), num(o["pf_jpy"]), num(o["dd_jpy"])
    if None in (inet, ipf, idd, onet, opf, odd):
        continue
    rec = {"id": pid, "family": i["family"],
           "is": (inet, ipf, idd), "oos": (onet, opf, odd),
           "xm5": w.get("XM5")}
    is_strict = (inet > IS_BASE["net"] and ipf > IS_BASE["pf"] and idd <= IS_BASE["dd"]
                 and onet > OOS_BASE["net"] and opf > OOS_BASE["pf"] and odd <= OOS_BASE["dd"])
    if is_strict:
        strict.append(rec)
    elif idd < IS_BASE["dd"] and odd < OOS_BASE["dd"]:
        dd_both.append(rec)
    elif (inet > IS_BASE["net"] or onet > OOS_BASE["net"]) and (idd < IS_BASE["dd"] or odd < OOS_BASE["dd"]):
        tradeoff.append(rec)


def show(title, items, limit=None):
    print("\n===== %s : %d件 =====" % (title, len(items)))
    items = sorted(items, key=lambda r: r["oos"][0], reverse=True)
    for r in (items[:limit] if limit else items):
        inet, ipf, idd = r["is"]
        onet, opf, odd = r["oos"]
        x = r["xm5"]
        xs = ("XM5 net=%.0f pf=%.4f dd=%.4f" % (num(x["net_jpy"]), num(x["pf_jpy"]), num(x["dd_jpy"]))
              if x else "XM5 未実行")
        print("%-10s %-18s IS[%+9.0f %.4f %7.4f] OOS[%+8.0f %.4f %7.4f] %s"
              % (r["id"], r["family"], inet, ipf, idd, onet, opf, odd, xs))


print("基準 IS  net=%+.0f pf=%.4f dd=%.4f" % (IS_BASE["net"], IS_BASE["pf"], IS_BASE["dd"]))
print("基準 OOS net=%+.0f pf=%.4f dd=%.4f" % (OOS_BASE["net"], OOS_BASE["pf"], OOS_BASE["dd"]))
print("基準 XM5 net=%+.0f pf=%.4f dd=%.4f" % (XM5_BASE["net"], XM5_BASE["pf"], XM5_BASE["dd"]))
print("\n両期間の実測が揃った案: %d" % len([1 for w in by_id.values() if "IS" in w and "OOS" in w]))
show("厳格改善", strict)
show("両期間DD低下", dd_both, limit=15)
show("トレードオフ", tradeoff, limit=10)

# XM5でDD30%以下に到達した案（増レバ可否の分かれ目）
print("\n===== XM5でDD30%%以下 =====")
hit = [r for r in best.values() if r["window"] == "XM5" and num(r["dd_jpy"]) is not None
       and num(r["dd_jpy"]) <= 30.0]
if not hit:
    print("なし（全XM5実行でDD30%超）")
    xs = [num(r["dd_jpy"]) for r in best.values() if r["window"] == "XM5" and num(r["dd_jpy"]) is not None]
    if xs:
        print("XM5 DDの最小値: %.4f%%（基準 %.4f%%）" % (min(xs), XM5_BASE["dd"]))
