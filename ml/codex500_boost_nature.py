# -*- coding: utf-8 -*-
"""SCA Boost拡大が「単なるレバレッジ増」か「リスク調整後も改善」かを判別する。
取引数が不変ならエントリー集合は同じ＝サイズだけの変更。
利益/DD比が改善するなら、Boost対象取引に真のエッジがあることを示唆する。
"""
import csv

rows = {r['id']: r for r in csv.DictReader(open('ml/codex500/results3.csv', encoding='utf-8'))}
targets = [("現行 Boost4.0/RR2.0", None),
           ("Boost4.5/RR2.0", "R3F09_Boost_Mult-4p5_RR_Ratio-2p0"),
           ("Boost5.0/RR2.0", "R3F09_Boost_Mult-5p0_RR_Ratio-2p0"),
           ("Boost6.0/RR2.0", "R3F09_Boost_Mult-6p0_RR_Ratio-2p0")]
CUR = dict(is_net=50609.0, is_dd=26.4547, is_n=684, oos_net=35775.0, oos_dd=19.3223, oos_n=658)

print("%-22s %9s %7s %6s %8s | %9s %7s %6s %8s" %
      ("設定", "IS純益", "IS-DD", "IS取引", "IS益/DD", "OOS純益", "OOS-DD", "OOS取引", "OOS益/DD"))
for label, rid in targets:
    d = CUR if rid is None else rows.get(rid)
    if d is None:
        print(label, "NOT FOUND"); continue
    isn, isdd, isn_n = float(d['is_net']), float(d['is_dd']), int(d['is_n'])
    on, odd, on_n = float(d['oos_net']), float(d['oos_dd']), int(d['oos_n'])
    print("%-22s %9.0f %6.2f%% %6d %8.0f | %9.0f %6.2f%% %7d %8.0f" %
          (label, isn, isdd, isn_n, isn / isdd, on, odd, on_n, on / odd))
