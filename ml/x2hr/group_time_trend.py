import sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, r'C:\Users\f\source\repos\mt5_backtester\ml\x2hr')
import sleeve_time_trend as st

rows = st.load_full()
years = sorted({y for y, _, _ in rows})

groups = {
    "FX枠": lambda m: st.SYMBOL_OF.get(m) not in st.CRYPTO | {"GOLD"},
    "GOLD枠": lambda m: st.SYMBOL_OF.get(m) == "GOLD",
    "暗号枠": lambda m: st.SYMBOL_OF.get(m) in st.CRYPTO,
}
print("【グループ別・年別】取引数 / 1取引平均円 / そのグループの年間合計円")
hdr = f"{'年':>6}"
for g in groups:
    hdr += f"{g+' 件':>10}{g+' 平均':>11}{g+' 合計':>12}"
print(hdr)
tot = defaultdict(float)
for y in years:
    line = f"{y:>6}"
    for g, f in groups.items():
        v = [p for yy, m, p in rows if yy == y and f(m)]
        if v:
            a = np.array(v)
            line += f"{len(a):>10}{a.mean():>11.0f}{a.sum():>12.0f}"
            tot[g] += a.sum()
        else:
            line += f"{'—':>10}{'—':>11}{'—':>12}"
    print(line)
print(f"\n{'全期間合計':>6}" + "".join(f"{'':>10}{'':>11}{tot[g]:>12.0f}" for g in groups))

print("\n【直近2年（2025-2026）のグループ別】")
for g, f in groups.items():
    v = [p for yy, m, p in rows if yy >= 2025 and f(m)]
    if v:
        a = np.array(v)
        print(f"  {g:>8}: {len(a):>4}取引  平均{a.mean():>8.0f}円  "
              f"合計{a.sum():>10.0f}円  シャープ{a.mean()/a.std(ddof=1):>8.4f}")

print("\n【2016-2020（初期5年）のグループ別】")
for g, f in groups.items():
    v = [p for yy, m, p in rows if yy <= 2020 and f(m)]
    if v:
        a = np.array(v)
        print(f"  {g:>8}: {len(a):>4}取引  平均{a.mean():>8.0f}円  "
              f"合計{a.sum():>10.0f}円  シャープ{a.mean()/a.std(ddof=1):>8.4f}")
