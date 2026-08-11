# -*- coding: utf-8 -*-
"""Codexの256部分集合結果を独立に再判定する。
baselineを上回る部分集合を、指標別に自前で抽出する。
"""
import csv

rows = list(csv.DictReader(open('ml/tradeoff8/subset_results.csv', encoding='utf-8')))
print('部分集合数:', len(rows))
print('列:', list(rows[0].keys()))


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# baseline行を特定（採用案が空のもの）
base = None
for r in rows:
    subset = (r.get('subset') or r.get('members') or r.get('combo') or '').strip()
    if subset in ('', '-', 'none', 'baseline'):
        base = r
        break
if base is None:
    base = min(rows, key=lambda r: len((r.get('subset') or '')))
print('\nbaseline行:', {k: base[k] for k in list(base)[:6]})

bp = f(base.get('net_profit') or base.get('net'))
bd = f(base.get('max_dd_pct') or base.get('dd'))
print('baseline: 純利益=%.0f DD=%.4f%% 比=%.0f' % (bp, bd, bp / bd))

cands = []
for r in rows:
    p = f(r.get('net_profit') or r.get('net'))
    d = f(r.get('max_dd_pct') or r.get('dd'))
    if p is None or d is None or d == 0:
        continue
    cands.append((p / d, p, d, (r.get('subset') or r.get('members') or r.get('combo') or '')))

print('\n=== 純利益÷DD%% 上位5 ===')
for ratio, p, d, s in sorted(cands, reverse=True)[:5]:
    print('  比%9.0f 利益%9.0f DD%7.4f%%  [%s]' % (ratio, p, d, s))

print('\n=== 純利益 上位5 ===')
for ratio, p, d, s in sorted(cands, key=lambda x: -x[1])[:5]:
    print('  利益%9.0f DD%7.4f%% 比%9.0f  [%s]' % (p, d, ratio, s))

print('\n=== 利益・DD・比の3指標すべてbaseline改善 ===')
allbetter = [(r_, p, d, s) for r_, p, d, s in cands if p > bp and d <= bd and r_ > bp / bd]
for ratio, p, d, s in sorted(allbetter, key=lambda x: -x[1])[:8]:
    print('  利益%9.0f(%+7.0f) DD%7.4f%%(%+.4f) 比%9.0f  [%s]'
          % (p, p - bp, d, d - bd, ratio, s))
print('該当数:', len(allbetter))
