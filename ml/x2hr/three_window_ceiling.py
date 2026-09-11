"""V007訂正の裏づけを3窓そろえて出す。

correct_ceiling.py は OOS窓だけだった。ユーザー指示（IS窓も必ず併記）に従い
IS / OOS / FULL の3窓すべてで
  (1) 閉形式の k 依存（無期限）
  (2) 期限つきの最良 k と P(2倍)
を出す。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import math
import correct_ceiling as cc

books = cc.load()
MONTHS = cc.MONTHS
KS = (0.5, 1, 2, 4, 8, 32, 1000)

print('=' * 78)
print('【A】無期限・破綻ライン10%：閉形式 P(2倍) の k 依存（3窓）')
print('=' * 78)
head = ''.join(f'{"k=" + str(k):>9}' for k in KS)
print(f'{"窓":>5}{"ケリーk*":>10}' + head)
kelly = {}
for w in ('IS', 'OOS', 'FULL'):
    t = [p for _, p in books[('both', w)]]
    n = len(t)
    m = sum(t) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in t) / (n - 1))
    mr, sr = m / cc.CAPITAL, sd / cc.CAPITAL
    kk = mr / sr ** 2
    kelly[w] = (kk, mr, sr, n)
    row = ''.join(f'{100 * cc.closed_form(mr, sr, k):>8.1f}%' for k in KS)
    print(f'{w:>5}{kk:>10.3f}' + row)
print()
for w in ('IS', 'OOS', 'FULL'):
    kk, mr, sr, n = kelly[w]
    print(f'  {w}（{n}取引）: ケリー k*={kk:.3f} のとき P={100 * cc.closed_form(mr, sr, kk):.1f}%')

print()
print('=' * 78)
print('【B】期限つき・破綻ライン10%：最良の k と P(2倍)（3窓・20,000パス）')
print('=' * 78)
print(f'{"窓":>5}{"期限":>8}{"最良k":>8}{"P(2倍)":>9}{"P(破綻)":>9}'
      f'{"P(期限切れ)":>12}{"到達中央値":>12}')
for w in ('IS', 'OOS', 'FULL'):
    t = [p for _, p in books[('both', w)]]
    rate = len(t) / MONTHS[w]
    for limit in (1, 2, 3, 6, 12, 24):
        hs = int(round(rate * limit))
        best = None
        for k in (0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 16, 32):
            h, r, med = cc.simulate(t, k, 0.10, hs)
            if best is None or h > best[1]:
                best = (k, h, r, med)
        k, h, r, med = best
        mo = f'{med / rate:.2f}か月' if med else '—'
        star = '  ★85%達成' if h >= 0.85 else ''
        print(f'{w:>5}{limit:>7}月{k:>8.2f}{100 * h:>8.1f}%{100 * r:>8.1f}%'
              f'{100 * (1 - h - r):>11.1f}%{mo:>12}{star}')
    print()
