# -*- coding: utf-8 -*-
"""A級/B級案スイープ結果にゲートを適用して判定する。
ゲート: IS/OOS両期間で純益が BASE 以上（悪化なし）。
PB_GOLDは窓が入れ子（全期間 ⊃ 後半）なので、差分で独立な前半区間も併せて判定する。
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

VAR = ["A5H12", "A5H30", "A5H60", "A6ALL", "A6PRF", "B7L2", "B7L3",
       "B8P80", "B8P90", "B10L20", "B10L50", "A4A10", "A4A15"]
LABEL = {"A5H12": "A5 12本", "A5H30": "A5 30本", "A5H60": "A5 60本",
         "A6ALL": "A6 金曜全決済", "A6PRF": "A6 金曜益のみ",
         "B7L2": "B7 2連敗cd", "B7L3": "B7 3連敗cd",
         "B8P80": "B8 ATR80%", "B8P90": "B8 ATR90%",
         "B10L20": "B10 構造20", "B10L50": "B10 構造50",
         "A4A10": "A4 ATR1.0", "A4A15": "A4 ATR1.5"}
SLEEVES = ["PB_GOLD", "PB_USDJPY", "PB_GBPJPY", "RSI_EURUSD", "RSI_USDJPY", "RSI_GBPUSD"]

print("=" * 104)
print("A級/B級案のゲート判定（IS/OOS両期間でBASE以上）")
for s in SLEEVES:
    b_is, b_oos = D[(s, "IS")].get("BASE"), D[(s, "OOS")].get("BASE")
    if not (b_is and b_oos):
        continue
    print("-" * 104)
    note = "（IS=全期間21-26 / OOS=後半24-26・入れ子）" if s == "PB_GOLD" else ""
    print("%-11s BASE  IS %+8.0f (n=%d) / OOS %+8.0f (n=%d) %s"
          % (s, b_is["net"], b_is["n"], b_oos["net"], b_oos["n"], note))
    for v in VAR:
        g_is, g_oos = D[(s, "IS")].get(v), D[(s, "OOS")].get(v)
        if not (g_is and g_oos):
            continue
        d_is, d_oos = g_is["net"] - b_is["net"], g_oos["net"] - b_oos["net"]
        ok = (d_is >= 0 and d_oos >= 0)
        print("   %-12s IS %+8.0f (%+7.0f) / OOS %+8.0f (%+7.0f) | DD %4.1f→%4.1f | %s"
              % (LABEL[v], g_is["net"], d_is, g_oos["net"], d_oos,
                 b_is["dd"], g_is["dd"], "**合格**" if ok else ""))

print()
print("=" * 104)
print("合格した組み合わせ:")
hits = []
for s in SLEEVES:
    b_is, b_oos = D[(s, "IS")].get("BASE"), D[(s, "OOS")].get("BASE")
    for v in VAR:
        g_is, g_oos = D[(s, "IS")].get(v), D[(s, "OOS")].get(v)
        if not all([g_is, g_oos, b_is, b_oos]):
            continue
        if g_is["net"] >= b_is["net"] and g_oos["net"] >= b_oos["net"]:
            hits.append((s, v, b_is["net"], g_is["net"], b_oos["net"], g_oos["net"]))
            print("  %-11s %-12s IS %+8.0f→%+8.0f / OOS %+8.0f→%+8.0f"
                  % (s, LABEL[v], b_is["net"], g_is["net"], b_oos["net"], g_oos["net"]))
if not hits:
    print("  なし")

# PB_GOLDは入れ子窓なので差分で独立区間（2021.06-2024.01）を復元して再判定
print()
print("=" * 104)
print("PB_GOLD 差分分解（前半2021.06-2024.01＝後半と重ならない独立区間・固定ロットで加法的）")
bf, bl = D[("PB_GOLD", "IS")]["BASE"], D[("PB_GOLD", "OOS")]["BASE"]
base_early = bf["net"] - bl["net"]
print("  %-12s 前半 %+8.0f (n=%d)  基準" % ("BASE", base_early, bf["n"] - bl["n"]))
for v in VAR:
    gf, gl = D[("PB_GOLD", "IS")].get(v), D[("PB_GOLD", "OOS")].get(v)
    if not (gf and gl):
        continue
    early = gf["net"] - gl["net"]
    print("  %-12s 前半 %+8.0f (n=%d)  %s"
          % (LABEL[v], early, gf["n"] - gl["n"],
             ("改善 %+.0f" % (early - base_early)) if early >= base_early
             else ("**悪化 %+.0f**" % (early - base_early))))
