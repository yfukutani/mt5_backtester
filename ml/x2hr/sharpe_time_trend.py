"""Codexの指摘「円ベースの平均損益の上昇だけでは、リスク当たりの優位性が改善したとは
言えない」を確かめる。シャープ（1取引あたり平均 ÷ 標準偏差）は尺度不変なので、
円建てスケールの上昇では動かない。**シャープも上がっていれば、規模ではなく質の変化。**
"""
import sys
import numpy as np
sys.path.insert(0, r'C:\Users\f\source\repos\mt5_backtester\ml\x2hr')
import sleeve_time_trend as st
from sleeve_ablation import MAGIC_NAME

rows = st.load_full()
PERIODS = [("2016-2018", 2016, 2018), ("2019-2021", 2019, 2021),
           ("2022-2023", 2022, 2023), ("2024-2026", 2024, 2026)]

def show(title, pred):
    print(f"\n【{title}】")
    print(f"{'期間':>12}{'取引':>7}{'平均円':>10}{'標準偏差':>10}"
          f"{'シャープ/取引':>14}{'合計円':>12}")
    for lab, a, b in PERIODS:
        v = [p for y, m, p in rows if a <= y <= b and pred(m)]
        if len(v) < 2:
            print(f"{lab:>12}{len(v):>7}{'—':>10}{'—':>10}{'—':>14}{'—':>12}")
            continue
        x = np.array(v)
        sd = x.std(ddof=1)
        print(f"{lab:>12}{len(x):>7}{x.mean():>10.0f}{sd:>10.0f}"
              f"{(x.mean()/sd if sd else 0):>14.4f}{x.sum():>12.0f}")

print("=" * 88)
print("シャープ（尺度不変）で見た時間トレンド——規模の変化か、質の変化か")
print("=" * 88)
show("ブック全体", lambda m: True)
show("FX枠のみ", lambda m: st.SYMBOL_OF.get(m) not in st.CRYPTO | {"GOLD"})
show("GOLD枠のみ", lambda m: st.SYMBOL_OF.get(m) == "GOLD")

print("\n" + "=" * 88)
print("GOLD枠を個別に分解（新しく追加・調整された枠が原因かを見る）")
print("=" * 88)
for g in (20260640, 20261002, 20261003):
    show(f"{MAGIC_NAME.get(g, str(g))} (magic {g})", lambda m, gg=g: m == gg)

print("\n" + "=" * 88)
print("【読み方】")
print("=" * 88)
print("  シャープは尺度不変なので、金価格の上昇だけでは動かない。")
print("  シャープも上がっているなら、規模ではなく『質』が変わっている——")
print("  それが本当の改善なのか、近年データへの調整（過学習）なのかは、")
print("  この測定だけでは分離できない。")
