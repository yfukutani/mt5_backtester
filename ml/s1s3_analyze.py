# -*- coding: utf-8 -*-
"""S1/S3スイープ結果にゲートを適用して判定する。
ゲート: IS/OOS両期間で純益が BASE 以上（悪化なし）。台地性は隣接水準の符号一致で確認。
"""
import csv
from collections import defaultdict
from pathlib import Path

SRC = Path(r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\s1s3\s1s3_results.csv")
rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
D = defaultdict(dict)
for r in rows:
    D[(r["sleeve"], r["window"])][r["variant"]] = {
        "net": float(r["net"]), "pf": float(r["pf"]), "dd": float(r["dd"]), "n": int(r["n"])}

BE = ["BE40", "BE50", "BE75", "BE100"]
TR = ["TR15", "TR20", "TR25", "TR30"]
LABEL = {"BE40": "BE@0.4R", "BE50": "BE@0.5R", "BE75": "BE@0.75R", "BE100": "BE@1.0R",
         "TR15": "TRAIL1.5A", "TR20": "TRAIL2.0A", "TR25": "TRAIL2.5A", "TR30": "TRAIL3.0A"}
SLEEVES = ["PB_GOLD", "PB_USDJPY", "PB_GBPJPY", "RSI_EURUSD", "RSI_USDJPY", "RSI_GBPUSD"]


def show(title, variants):
    print("=" * 108)
    print(title)
    hdr = "%-11s %-9s" % ("sleeve", "variant")
    for w in ("IS", "OOS"):
        hdr += " | %9s %6s %6s %5s" % (w + "_net", "PF", "DD%", "n")
    print(hdr + " | 判定")
    for s in SLEEVES:
        if variants is TR and not s.startswith("PB"):
            continue
        base = {w: D[(s, w)].get("BASE") for w in ("IS", "OOS")}
        if not all(base.values()):
            continue
        print("-" * 108)
        line = "%-11s %-9s" % (s, "BASE")
        for w in ("IS", "OOS"):
            b = base[w]
            line += " | %+9.0f %6.2f %6.1f %5d" % (b["net"], b["pf"], b["dd"], b["n"])
        print(line + " | 基準")
        for v in variants:
            got = {w: D[(s, w)].get(v) for w in ("IS", "OOS")}
            if not all(got.values()):
                continue
            line = "%-11s %-9s" % ("", LABEL[v])
            ok = True
            for w in ("IS", "OOS"):
                g, b = got[w], base[w]
                line += " | %+9.0f %6.2f %6.1f %5d" % (g["net"], g["pf"], g["dd"], g["n"])
                if g["net"] < b["net"]:
                    ok = False
            d_is = got["IS"]["net"] - base["IS"]["net"]
            d_oos = got["OOS"]["net"] - base["OOS"]["net"]
            mark = "**合格**" if ok else ("両期間悪化" if (d_is < 0 and d_oos < 0) else "片側悪化")
            print(line + " | %s (IS%+.0f/OOS%+.0f)" % (mark, d_is, d_oos))


show("S1: ブレークイーブン（BE@X R）※PB_GOLDは入れ子窓のため参考値", BE)
print()
show("S3: ATR連動トレーリング（PullbackTrendのみ・×ATR）", TR)

print()
print("=" * 108)
print("合格した組み合わせ（IS/OOS両期間でBASE以上）:")
hits = 0
for s in SLEEVES:
    for v in BE + TR:
        g_is, g_oos = D[(s, "IS")].get(v), D[(s, "OOS")].get(v)
        b_is, b_oos = D[(s, "IS")].get("BASE"), D[(s, "OOS")].get("BASE")
        if not all([g_is, g_oos, b_is, b_oos]):
            continue
        if g_is["net"] >= b_is["net"] and g_oos["net"] >= b_oos["net"]:
            hits += 1
            print("  %-11s %-9s IS %+8.0f→%+8.0f / OOS %+8.0f→%+8.0f"
                  % (s, LABEL[v], b_is["net"], g_is["net"], b_oos["net"], g_oos["net"]))
if hits == 0:
    print("  なし")
