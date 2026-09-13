"""V043：**期限なし**での「破綻するまでに2倍になる確率」を実測する。

【なぜ今これを測るのか】
ユーザーの標準指示は一貫して次の文面である。

> **破綻するまでに**資金が2倍になる確率85%を目標に、戦略案の検討→実力値の検証を繰り返す。

**これは期限付きの問題ではない。** 「破綻するまでに」＝「破綻より先に2倍へ到達する」
という古典的な gambler's ruin の問題であり、期限（R4）は後から要件として追加されたもの
（要件書 §2 R4「理想1ヶ月・上限2ヶ月」）である。

V034で判明したとおり、**定数方策では6ヶ月以上の破綻確率は0.0〜0.1%しかなく、
失敗のほぼ全ては「期限内に届かなかった」だけ**である。
つまり **R3（85%）を阻んでいたのはR4（期限）**であって、破綻リスクではない。

V009では閉形式（拡散近似）で「ケリー値 k=m/s² のとき P=94.7%（破綻ライン10%）」と
計算したが、**実際の取引分布を使ったシミュレーションで期限なしを測ったことはない。**
本スクリプトはそれを埋める。

【手続き】
- 期限を実質的に外す（120ヶ月＝10年相当のホライズンで打ち切り、打ち切り率も報告する）
- 倍率kは**IS窓で選ぶ**（OOSを見ない）。V029のエントリー時サイジング
- **IS窓の結果も必ず併記する**（ユーザー指示）
- 破綻ラインは10%（R7の暫定値）。感応度として20%・50%も出す

【限界】
- 「期限なし」といっても計算上は120ヶ月で打ち切っている。打ち切り率が高ければ
  実質的に期限付きと変わらない
- 実運用では、10年間同じ枠が同じ性質で動き続ける保証はない。
  V040で見たとおり、ブックの期待値は時期によって大きく変わる
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

MONTHS = cc.MONTHS
N_PATHS = 10000
SEEDS = (101, 202, 303)
TARGET = 0.85
K_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
LONG_MONTHS = 120.0     # 実質的に期限なしとみなすホライズン
RUIN_LEVELS = (0.10, 0.20, 0.50)


def run_ruin(paths, k, ruin_frac):
    """定数倍率kで、2倍到達 / 破綻 / 打ち切り を数える。"""
    n_paths, H = paths.shape
    eq = np.full(n_paths, cc.CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    for step in range(H):
        if not alive.any():
            break
        eq = np.where(alive, eq + paths[:, step] * k * (eq / cc.CAPITAL), eq)
        hit = alive & (eq >= cc.CAPITAL * 2.0)
        ruin = alive & (eq <= cc.CAPITAL * ruin_frac)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
    hs = stop[state == 1]
    return dict(p_hit=float((state == 1).mean()),
                p_ruin=float((state == 2).mean()),
                p_cut=float((state == 0).mean()),
                med_steps=int(np.median(hs)) if hs.size else None)


def main():
    books = dkl.build_books()
    pr_is, lg_is, _ = books["IS"]
    pr_o, lg_o, _ = books["OOS"]
    rate_is = len(pr_is) / MONTHS["IS"]
    rate_o = len(pr_o) / MONTHS["OOS"]

    m_is, s_is = float(pr_is.mean()), float(pr_is.std(ddof=1))
    m_o, s_o = float(pr_o.mean()), float(pr_o.std(ddof=1))
    kelly_is = (m_is / cc.CAPITAL) / ((s_is / cc.CAPITAL) ** 2)
    kelly_o = (m_o / cc.CAPITAL) / ((s_o / cc.CAPITAL) ** 2)

    print("=" * 112)
    print("V043：**期限なし**での「破綻するまでに2倍になる確率」")
    print("=" * 112)
    print("ユーザーの標準指示の文面は『**破綻するまでに**資金が2倍になる確率85%』であり、")
    print("期限（R4）は後から追加された別要件である。本測定は期限を実質的に外して測る。\n")
    print(f"IS窓: {len(pr_is)}取引 / 平均{m_is:.1f}円 / 標準偏差{s_is:.0f}円 / "
          f"ケリー値k*={kelly_is:.3f}")
    print(f"OOS窓: {len(pr_o)}取引 / 平均{m_o:.1f}円 / 標準偏差{s_o:.0f}円 / "
          f"ケリー値k*={kelly_o:.3f}")
    print(f"ホライズン: {LONG_MONTHS:.0f}ヶ月相当"
          f"（IS {int(rate_is*LONG_MONTHS)}取引 / OOS {int(rate_o*LONG_MONTHS)}取引）\n")

    for ruin_frac in RUIN_LEVELS:
        print("=" * 112)
        print(f"【破綻ライン {100*ruin_frac:.0f}%（初期資金の{100*ruin_frac:.0f}%を割ったら破綻）】")
        print("=" * 112)

        # --- IS窓で k を選ぶ ---
        H_is = int(round(rate_is * LONG_MONTHS))
        is_scores = {}
        for k in K_GRID:
            vals, ruins, cuts = [], [], []
            for sd in SEEDS:
                p = dk.generate_paths(pr_is, H_is, N_PATHS, dkl.L, seed=970000 + sd)
                r = run_ruin(p, k, ruin_frac)
                vals.append(r["p_hit"]); ruins.append(r["p_ruin"]); cuts.append(r["p_cut"])
            is_scores[k] = (float(np.mean(vals)), float(np.mean(ruins)),
                            float(np.mean(cuts)))
        k_sel = max(K_GRID, key=lambda k: is_scores[k][0])

        print(f"{'k':>7}{'IS到達':>9}{'IS破綻':>9}{'IS打切':>9}"
              f"│{'OOS到達':>9}{'OOS破綻':>9}{'OOS打切':>9}{'R3':>6}")
        H_o = int(round(rate_o * LONG_MONTHS))
        for k in K_GRID:
            ih, ir, ic = is_scores[k]
            hs, rs, cs = [], [], []
            for sd in SEEDS:
                p = dk.generate_paths(pr_o, H_o, N_PATHS, dkl.L, seed=980000 + sd)
                r = run_ruin(p, k, ruin_frac)
                hs.append(r["p_hit"]); rs.append(r["p_ruin"]); cs.append(r["p_cut"])
            oh, orr, oc = float(np.mean(hs)), float(np.mean(rs)), float(np.mean(cs))
            mark = "  ←IS選択" if k == k_sel else ""
            print(f"{k:>7}{100*ih:>8.1f}%{100*ir:>8.1f}%{100*ic:>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*oc:>8.1f}%"
                  f"{'✅' if oh >= TARGET else '❌':>6}{mark}")
        print(f"\n  → IS選択 k={k_sel}")
        print()

    print("=" * 112)
    print("【この測定の位置づけ】")
    print("=" * 112)
    print("  ・ユーザーの標準指示『破綻するまでに2倍になる確率85%』に、文面どおり答える測定")
    print("  ・要件書R4（期限1〜2ヶ月）を外した場合の姿を示す")
    print("  ・打ち切り率が高ければ『期限なし』とは言えないので必ず確認すること")
    print("\n完了。")


if __name__ == "__main__":
    main()
