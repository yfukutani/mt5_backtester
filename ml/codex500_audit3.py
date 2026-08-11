# -*- coding: utf-8 -*-
"""Codexラウンド3レポートの主張を独立検証する。
現行値を基準に「厳格改善(6指標同時優越)」「利益のみ改善」を自前で再判定する。
"""
import csv
from collections import defaultdict

BASE = {  # 現行本番値 (IS net, IS pf, IS dd, OOS net, OOS pf, OOS dd)
    "configs/pullback_gbpjpy_h4.yaml": (33133, 3.1179, 5.9298, 20763, 1.6392, 14.6751),
    "configs/rsi_robust_gbpusd_h4.yaml": (13398, 1.5083, 3.5222, 18922, 2.0279, 2.6760),
    "configs/sca_gbpjpy_m15.yaml": (50609, 1.1520, 26.4547, 35775, 1.1243, 19.3223),
    "configs/carry_audjpy_d1.yaml": (105817, 3.5057, 28.5360, 33912, 2.1952, 23.8033),
    "configs/pairtrade_eurusd_gbpusd.yaml": (11373, 1.1617, 8.3964, 9526, 1.6716, 3.7436),
}

rows = list(csv.DictReader(open('ml/codex500/results3.csv', encoding='utf-8')))
print('総候補数:', len(rows))

def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

strict, profit_only, by_fam = [], [], defaultdict(lambda: [0, 0])
for r in rows:
    b = BASE.get(r['base'])
    if not b:
        continue
    isn, ispf, isdd, on, opf, odd = (f(r['is_net']), f(r['is_pf']), f(r['is_dd']),
                                     f(r['oos_net']), f(r['oos_pf']), f(r['oos_dd']))
    if None in (isn, ispf, isdd, on, opf, odd):
        continue
    by_fam[r['family']][1] += 1
    if isn > 0 and on > 0:
        by_fam[r['family']][0] += 1
    # 厳格: 両期間で純利益・PFが上昇し、DDが悪化しない
    if (isn > b[0] and ispf > b[1] and isdd <= b[2]
            and on > b[3] and opf > b[4] and odd <= b[5]):
        strict.append(r)
    elif isn > b[0] and on > b[3]:
        profit_only.append(r)

print('\n【独立再判定】厳格改善(6指標同時優越):', len(strict))
for r in strict:
    print('  ', r['id'], r['overrides'][:60])

print('\n【独立再判定】両期間で純利益のみ増加(DD等は問わず):', len(profit_only))
for r in sorted(profit_only, key=lambda r: -(f(r['is_net']) + f(r['oos_net'])))[:20]:
    b = BASE[r['base']]
    print('   %-42s IS=%+8.0f(pf%.3f,dd%5.2f%%) OOS=%+8.0f(pf%.3f,dd%5.2f%%)'
          % (r['id'], f(r['is_net']), f(r['is_pf']), f(r['is_dd']),
             f(r['oos_net']), f(r['oos_pf']), f(r['oos_dd'])))
    print('      現行比 IS純利益%+.0f / OOS純利益%+.0f / IS-DD%+.2fpt / OOS-DD%+.2fpt'
          % (f(r['is_net']) - b[0], f(r['oos_net']) - b[3],
             f(r['is_dd']) - b[2], f(r['oos_dd']) - b[5]))

print('\n【ファミリー別生存】')
for fam in sorted(by_fam):
    s, t = by_fam[fam]
    print('  %-8s %2d/%2d' % (fam, s, t))
