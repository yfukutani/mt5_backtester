"""V065：SCA型を新銘柄へ展開したとき、**1取引シャープが維持されるか**を見積もる。

【なぜこれが決定的か】
V063で、70%到達への唯一の頑健な道は「取引頻度を4〜5倍にする」であり、
その具体策は「**SCA型を主要通貨ペア20〜30銘柄へ展開する**」と分かった。

**ただしV056の天井の式は**

    天井 ＝ Φ( 1取引あたりシャープ × √(3ヶ月の取引数) )

なので、**銘柄を増やして頻度が4倍になっても、1取引シャープが半分に落ちれば
天井は上がらない**（√4 ＝ 2 なので、シャープが1/2になると相殺される）。

**したがって「新銘柄でシャープがどれだけ落ちるか」が成否を決める。**

【既存の4枠から見積もる】
SCA型は現在 USDJPY / GBPJPY / GOLD×2 の4枠で動いている。
**この4枠の銘柄間ばらつきが、新銘柄での期待値の目安になる。**

- ばらつきが小さい（どの銘柄でも同程度）→ 展開しても質は保たれる見込み
- ばらつきが大きい → 銘柄選択が効いており、**残りの銘柄では落ちる可能性が高い**

さらに、**期間を分けて**「どの銘柄でも安定して正か」も確認する。
一部の銘柄・一部の期間だけで効いているなら、展開の前提は崩れる。

【限界】
- 4銘柄（実質3銘柄）からの外挿であり、標本が極めて少ない
- 現在の3銘柄は**選ばれた結果**である可能性が高い（生存者バイアス）
- スプレッド・流動性・取引時間帯の違いは考慮していない
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import sleeve_time_trend as st
from sleeve_ablation import MAGIC_NAME
from fx_degradation import FAMILY, PERIODS

MONTHS = cc.MONTHS


def stats(v):
    if len(v) < 3:
        return None
    a = np.array(v, dtype=float)
    sd = a.std(ddof=1)
    sh = float(a.mean() / sd) if sd else 0.0
    return dict(n=len(a), mean=float(a.mean()), sd=float(sd), sharpe=sh,
                t=sh * math.sqrt(len(a)), total=float(a.sum()))


def main():
    rows = st.load_full()
    sca = [(y, m, p) for y, m, p in rows if FAMILY.get(m) == "SCA"]
    magics = sorted({m for _, m, _ in sca})

    print("=" * 104)
    print("V065：SCA型を新銘柄へ展開したとき1取引シャープが維持されるか")
    print("=" * 104)
    print("V056の天井：Φ(1取引シャープ × √(3ヶ月の取引数))")
    print("**頻度が4倍になってもシャープが半分に落ちれば天井は上がらない**（√4＝2）。")
    print("既存SCA 4枠の銘柄間ばらつきから、展開先での期待値を見積もる。\n")

    print("【SCA型の枠別・全期間】")
    print(f"{'枠':>16}{'銘柄':>9}{'取引':>7}{'月あたり':>10}{'平均円':>10}"
          f"{'標準偏差':>10}{'1取引ｼｬｰﾌﾟ':>12}{'t値':>8}")
    per = {}
    for m in magics:
        v = [p for _, mm, p in sca if mm == m]
        s = stats(v)
        per[m] = s
        if s:
            print(f"{MAGIC_NAME.get(m, str(m)):>16}{st.SYMBOL_OF.get(m, '?'):>9}"
                  f"{s['n']:>7}{s['n']/MONTHS['FULL']:>10.2f}{s['mean']:>10.0f}"
                  f"{s['sd']:>10.0f}{s['sharpe']:>12.4f}{s['t']:>8.2f}")

    sh = np.array([per[m]["sharpe"] for m in magics if per[m]])
    print(f"\n  銘柄間のばらつき: 平均 {sh.mean():.4f} / 標準偏差 {sh.std(ddof=1):.4f} / "
          f"最小 {sh.min():.4f} / 最大 {sh.max():.4f}")
    print(f"  最大/最小の比 = {sh.max()/max(sh.min(),1e-9):.2f}倍")

    print("\n【SCA型の枠別・期間別シャープ】（安定しているか）")
    hdr = f"{'枠':>16}{'銘柄':>9}"
    for lab, _, _ in PERIODS:
        hdr += f"{lab:>12}"
    print(hdr)
    for m in magics:
        line = f"{MAGIC_NAME.get(m, str(m)):>16}{st.SYMBOL_OF.get(m, '?'):>9}"
        for _, a, b in PERIODS:
            v = [p for y, mm, p in sca if mm == m and a <= y <= b]
            s = stats(v)
            line += f"{s['sharpe']:>12.4f}" if s else f"{'—':>12}"
        print(line)

    # --- 期間ごとに何枠が正か ---
    print("\n  期間ごとに『シャープが正』だった枠の数:")
    for lab, a, b in PERIODS:
        pos = 0
        tot = 0
        for m in magics:
            v = [p for y, mm, p in sca if mm == m and a <= y <= b]
            s = stats(v)
            if s:
                tot += 1
                pos += 1 if s["sharpe"] > 0 else 0
        print(f"    {lab}: {pos}/{tot}枠")

    # --- 展開したときの天井を、シャープ劣化の度合いで感応度分析 ---
    print("\n" + "=" * 104)
    print("【展開時のシャープ劣化と天井の関係】")
    print("=" * 104)
    # OOS窓のブック全体の基準
    import dynamic_k_lag as dkl
    books = dkl.build_books()
    pr_o, _, _ = books["OOS"]
    base_sh = float(pr_o.mean()) / float(pr_o.std(ddof=1))
    rate_o = len(pr_o) / MONTHS["OOS"]
    H0 = rate_o * 3.0
    print(f"  現状：1取引シャープ {base_sh:.4f} / 3ヶ月{H0:.0f}取引 → "
          f"3ヶ月シャープ {base_sh*math.sqrt(H0):.3f} → 天井 "
          f"{100*0.5*(1+math.erf(base_sh*math.sqrt(H0)/math.sqrt(2))):.1f}%")
    print(f"\n{'頻度倍率':>9}{'新枠のシャープ劣化':>18}{'合成ｼｬｰﾌﾟ':>12}"
          f"{'3ヶ月ｼｬｰﾌﾟ':>13}{'天井':>9}{'70%到達の目安':>16}")
    for f in (3.0, 4.0, 5.0):
        for deg in (1.0, 0.8, 0.6, 0.5, 0.4):
            # 既存1/f＋新規(f-1)/f の加重平均でシャープを近似（相関1と仮定しない粗い近似）
            mixed = base_sh * (1 / f) + base_sh * deg * (1 - 1 / f)
            s3 = mixed * math.sqrt(H0 * f)
            ceil = 0.5 * (1 + math.erf(s3 / math.sqrt(2)))
            # 実測では天井の約75%前後が実力（V057：天井74.4%に対し実測56.1%）
            est = ceil * 0.75
            print(f"{f:>8.0f}x{deg:>17.0%}{mixed:>12.4f}{s3:>13.3f}"
                  f"{100*ceil:>8.1f}%{100*est:>15.1f}%")
        print()

    print("=" * 104)
    print("【限界】")
    print("=" * 104)
    print("  ・4銘柄（実質3銘柄）からの外挿であり、標本が極めて少ない")
    print("  ・現在の3銘柄は**選ばれた結果**である可能性が高い（生存者バイアス）")
    print("  ・スプレッド・流動性・取引時間帯の違いを考慮していない")
    print("  ・合成シャープの計算は枠間の相関を無視した粗い近似")
    print("  ・『天井の75%が実力』はV057の1点から取った経験則であり実証値ではない")
    print("\n完了。")


if __name__ == "__main__":
    main()
