"""V032：**85%に届くには取引機会が今の何倍必要か**を逆算する（V030の示唆）。

【動機】
V030で、到達確率は倍率kよりも**期限内の取引機会数H**に強く反応することが分かった
（OOS・6ヶ月でHを±30%振ると23.0pt動く）。V031（枠の取捨選択）が大きく悪化したのも、
枠を外してHが半減したことが主因だった。

そこで**「何が効くか」ではなく「どれだけ必要か」を逆算する。**
「2ヶ月で85%に届かせるには、取引機会が今の何倍必要か」が分かれば、
その倍率が現実的か（既定OFF枠の有効化・高頻度枠の追加で届くか）を判断できる。

【重要な前提（必ず併記すること）】
本測定は **「増えた取引機会も、既存ブックと同じ1取引あたりの損益分布に従う」** と仮定する。
これは**最も楽観的な仮定**である。実際には、

- 新しい枠が既存と同等の期待値・分散を持つ保証はない
- 枠が増えれば相関が上がり、実効的な分散低減効果は仮定より小さくなる
- 同じ相場を複数枠が奪い合えば、1取引あたりの質は下がる

したがってここで出る倍率は **「これだけあれば足りる」ではなく「これ未満では絶対に足りない」
という下限**として読むべきである。

【手続き（先読みを避ける）】
倍率fごとに、IS窓でkをグリッド総当たりして選び（IS選択）、そのkをOOS窓へ適用する。
OOSを見てkを選び直さない。動的方策はV029/V030でIS窓から選んだものを固定して使う。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

MONTHS = cc.MONTHS
N_PATHS = dkl.N_PATHS
TARGET = 0.85
K_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
F_GRID = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0]

# V029/V030でIS窓から選ばれた動的方策（期限ごと・選び直さない）
DYN = {2.0: ("B", (3.0,)), 6.0: ("A", (1.0, 1.0))}


def main():
    limits = [float(a) for a in sys.argv[1:]] or [2.0, 3.0, 4.0, 5.0, 6.0, 12.0]
    books = dkl.build_books()
    pr_is, lg_is, _ = books["IS"]
    pr_oos, lg_oos, _ = books["OOS"]
    s_is = float(pr_is.std(ddof=1)) / cc.CAPITAL
    rate_is = len(pr_is) / MONTHS["IS"]

    fam_fn = {"const": lambda p: dk.policy_constant(p[0]),
              "A": lambda p: dk.policy_A(*p),
              "B": lambda p: dk.policy_B(p[0]),
              "C": lambda p: dk.policy_C(p[0], s_is)}

    print("=" * 104)
    print("V032：85%に届くには取引機会が今の何倍必要か（逆算・V030の示唆）")
    print("=" * 104)
    print(f"\nIS窓の月間頻度 {rate_is:.2f}件/月（2,053取引 / 60ヶ月）")
    print("前提: 増えた取引機会も既存ブックと同じ1取引あたりの損益分布に従うと仮定する")
    print("      （最も楽観的な仮定。ここで出る倍率は『これ未満では絶対に足りない』下限）\n")

    summary = []
    for lim in limits:
        H_base = int(round(rate_is * lim))
        dyn = DYN.get(lim)
        print("=" * 104)
        print(f"【期限 {lim:g}ヶ月】基準H = {H_base}取引"
              + (f" / 動的方策 = {dyn[0]}{dyn[1]}" if dyn else " / 動的方策なし（IS未選択）"))
        print("=" * 104)
        print(f"{'頻度倍率':>9}{'H':>7}{'月間頻度':>10}"
              f"{'IS選択k':>9}{'IS定数':>9}{'OOS定数':>9}"
              f"{'OOS動的':>9}{'OOS破綻':>9}{'判定':>8}")

        hit_const = hit_dyn = None
        for f in F_GRID:
            H = int(round(H_base * f))
            if H < 5:
                continue
            # --- IS選択 ---
            p_is, l_is = dkl.generate_paths_lag(pr_is, lg_is, H, N_PATHS,
                                                seed=990000 + int(lim * 100) + int(f * 10))
            best_k, best_p, best_r = None, -1.0, None
            for k in K_GRID:
                r = dkl.run_policy_lag(p_is, l_is, dk.policy_constant(k), entry_sizing=True)
                if r["p_hit"] > best_p:
                    best_k, best_p, best_r = k, r["p_hit"], r
            # --- OOS適用 ---
            p_oos, l_oos = dkl.generate_paths_lag(pr_oos, lg_oos, H, N_PATHS,
                                                  seed=991000 + int(lim * 100) + int(f * 10))
            rc = dkl.run_policy_lag(p_oos, l_oos, dk.policy_constant(best_k),
                                    entry_sizing=True)
            if dyn:
                rd = dkl.run_policy_lag(p_oos, l_oos, fam_fn[dyn[0]](dyn[1]),
                                        entry_sizing=True)
                d_hit, d_ruin = rd["p_hit"], rd["p_ruin"]
            else:
                d_hit = d_ruin = float("nan")

            if hit_const is None and rc["p_hit"] >= TARGET:
                hit_const = f
            if dyn and hit_dyn is None and d_hit >= TARGET:
                hit_dyn = f

            mark = ""
            if rc["p_hit"] >= TARGET:
                mark = "✅定数"
            elif dyn and d_hit >= TARGET:
                mark = "✅動的"
            dstr = f"{100*d_hit:.1f}%" if dyn else "—"
            drstr = f"{100*d_ruin:.1f}%" if dyn else "—"
            print(f"{f:>8.1f}x{H:>7}{rate_is*f:>10.1f}{best_k:>9}"
                  f"{100*best_p:>8.1f}%{100*rc['p_hit']:>8.1f}%"
                  f"{dstr:>9}{drstr:>9}{mark:>8}")

            if (rc["p_hit"] >= TARGET) and (not dyn or d_hit >= TARGET):
                break

        need = hit_dyn if (hit_dyn is not None and
                           (hit_const is None or hit_dyn < hit_const)) else hit_const
        summary.append((lim, H_base, hit_const, hit_dyn, need))
        if need is None:
            print(f"\n  → 頻度を{F_GRID[-1]:g}倍（月{rate_is*F_GRID[-1]:.0f}件）にしても85%に届かない")
        else:
            print(f"\n  → 85%到達に必要な頻度倍率: 定数k {hit_const if hit_const else '—'}x / "
                  f"動的 {hit_dyn if hit_dyn else '—'}x  "
                  f"→ **最小 {need:g}倍（月 {rate_is*need:.0f}件・現在の{need:g}倍）**")

    print("\n" + "=" * 104)
    print("【まとめ：85%到達に必要な取引機会の倍率】")
    print("=" * 104)
    print(f"{'期限':>7}{'現在のH':>9}{'必要倍率':>10}{'必要な月間頻度':>16}"
          f"{'必要なH':>9}{'現実性':>10}")
    for lim, H_base, hc, hd, need in summary:
        if need is None:
            print(f"{lim:>6.0f}月{H_base:>9}{'32x超':>10}{'—':>16}{'—':>9}{'非現実的':>10}")
        else:
            real = "検討可" if need <= 3 else ("困難" if need <= 8 else "非現実的")
            print(f"{lim:>6.0f}月{H_base:>9}{need:>9.1f}x{rate_is*need:>15.0f}件"
                  f"{int(round(H_base*need)):>9}{real:>10}")
    print("\n完了。")


if __name__ == "__main__":
    main()
