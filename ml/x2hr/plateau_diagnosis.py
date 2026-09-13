"""V024：24ヶ月のIS選択プラトーが「真に平坦」か「モンテカルロノイズ」かを切り分ける。

V023で、24ヶ月のIS窓P(到達)がk∈[0.4,0.7]でほぼ平坦（差0.06pt）と判明し、
どのkが選ばれるかでOOS結果が84.0%〜86.9%まで動いた。

【切り分け方法】
1. パス数を20,000→100,000に増やし、同じ現象（プラトーの形）が残るか確認する
   （MCノイズなら滑らかになり、真の平坦さなら形はほぼ変わらないはず）
2. IS窓を前半・後半の2期間に分割し、両方で安定して良いkがあるかを見る
   （IS内クロスバリデーション。過学習しにくいkの選び方の一案）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk

LIMIT = 24
FINE_GRID = [0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 1.0]


def part1_more_paths():
    print("=" * 80)
    print("【1】パス数を増やしてプラトーの形が変わるか確認（IS窓・24ヶ月）")
    print("=" * 80)
    books = cc.load()
    t_is = [p for _, p in books[("both", "IS")]]
    n_is = len(t_is)
    rate_is = n_is / dk.MONTHS["IS"]
    H_is = int(round(rate_is * LIMIT))

    for n_paths in (20000, 100000):
        dk.N_PATHS = n_paths
        print(f"\n  n_paths={n_paths}")
        for k in FINE_GRID:
            paths_is = dk.generate_paths(t_is, H_is, n_paths, dk.L, seed=999000)
            r = dk.run_policy(paths_is, dk.policy_constant(k), H_is)
            print(f"    k={k}: IS P(2倍)={100*r['p_hit']:.3f}%")
    dk.N_PATHS = 20000  # restore


def part2_split_is():
    print("\n" + "=" * 80)
    print("【2】IS窓を前半・後半に分割してのクロスバリデーション（24ヶ月）")
    print("=" * 80)
    books = cc.load()
    is_deals = books[("both", "IS")]   # list of (time, profit), sorted by time
    n = len(is_deals)
    mid = n // 2
    first_half = [p for _, p in is_deals[:mid]]
    second_half = [p for _, p in is_deals[mid:]]
    print(f"  IS窓合計{n}取引 → 前半{len(first_half)}取引 / 後半{len(second_half)}取引")

    # 月あたり取引数は全体レートを流用（期間もおおよそ半分と仮定）
    rate_is_full = n / dk.MONTHS["IS"]
    H = int(round(rate_is_full * LIMIT))
    H_half = H // 2   # 期間も半分なので取引期待数もおおよそ半分

    print(f"\n  {'k':>6}{'前半P(到達)':>13}{'後半P(到達)':>13}{'両方の最小値':>13}")
    scored = []
    for k in FINE_GRID:
        paths_f = dk.generate_paths(first_half, H_half, dk.N_PATHS, dk.L, seed=888000)
        paths_s = dk.generate_paths(second_half, H_half, dk.N_PATHS, dk.L, seed=888001)
        rf = dk.run_policy(paths_f, dk.policy_constant(k), H_half)
        rs = dk.run_policy(paths_s, dk.policy_constant(k), H_half)
        worst = min(rf["p_hit"], rs["p_hit"])
        scored.append((k, rf["p_hit"], rs["p_hit"], worst))
        print(f"  {k:>6}{100*rf['p_hit']:>12.2f}%{100*rs['p_hit']:>12.2f}%{100*worst:>12.2f}%")

    best_minmax = max(scored, key=lambda x: x[3])
    print(f"\n  min-max基準（両半分とも悪くならないk）: k={best_minmax[0]}"
          f"（前半{100*best_minmax[1]:.2f}% / 後半{100*best_minmax[2]:.2f}%）")


if __name__ == "__main__":
    part1_more_paths()
    part2_split_is()
