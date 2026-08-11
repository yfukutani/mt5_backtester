# -*- coding: utf-8 -*-
"""Codexの再最適化レポートの「厳格改善4件」を独立検証する。
現行値と候補値を results.csv から引き当て、6指標の同時優越を自前で再判定する。
"""
import csv
import ast

BASE = {  # 現行本番値 (IS net, IS pf, IS dd, OOS net, OOS pf, OOS dd)
    "PB_GBPJPY":   (33133, 3.1179, 5.9298, 20763, 1.6392, 14.6751),
    "RSI_EURUSD":  (8253, 1.0869, 9.76, -1867, 0.9764, 13.10),
    "SCA_USDJPY":  (16913, 1.1410, 11.0572, -4875, 0.9324, 10.2599),
    "ETH_ETHUSD":  (4128, 1.4919, 3.84, 3410, 4.6471, 0.67),
}

rows = list(csv.DictReader(open('ml/param_reopt/results.csv', encoding='utf-8')))
print('総行数:', len(rows))
cols = rows[0].keys()
print('列:', list(cols))

def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

# 全行を走査し、BASEを持つスリーブについて厳格改善を独立判定
strict = []
for r in rows:
    sl = r.get('sleeve') or r.get('family') or ''
    b = BASE.get(sl)
    if not b:
        continue
    vals = [f(r.get(k)) for k in ('is_net', 'is_pf', 'is_dd', 'oos_net', 'oos_pf', 'oos_dd')]
    if any(v is None for v in vals):
        continue
    isn, ispf, isdd, on, opf, odd = vals
    if (isn > b[0] and ispf > b[1] and isdd <= b[2]
            and on > b[3] and opf > b[4] and odd <= b[5]):
        strict.append((sl, r.get('overrides', ''), isn, ispf, isdd, on, opf, odd))

print('\n【独立再判定】厳格改善(6指標同時優越):', len(strict))
seen = set()
for sl, ov, isn, ispf, isdd, on, opf, odd in sorted(strict):
    key = (sl, ov)
    if key in seen:
        continue
    seen.add(key)
    print('  %-12s %-52s' % (sl, ov[:52]))
    print('     IS %+9.0f pf%.4f dd%6.2f%%  |  OOS %+9.0f pf%.4f dd%6.2f%%'
          % (isn, ispf, isdd, on, opf, odd))
    b = BASE[sl]
    print('     現行比: IS%+.0f/pf%+.4f/dd%+.2fpt  OOS%+.0f/pf%+.4f/dd%+.2fpt'
          % (isn - b[0], ispf - b[1], isdd - b[2], on - b[3], opf - b[4], odd - b[5]))
