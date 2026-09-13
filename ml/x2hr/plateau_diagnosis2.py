"""V024（訂正版）：Codexの指摘を受け、真の train→test 手順でプラトー問題を再検証する。

【Codexの指摘（重要）】plateau_diagnosis.pyのmin-max選択（IS前半・後半の両方を見て
選ぶ）は「時期間の頑健性を使った選択」であって独立した検証ではない。さらに、複数の
選択方法（全期間argmax→k=0.5、細かいグリッド→k=0.6、min-max→k=0.8）を試して
OOSで一番良かったものを報告するのは、まさに排除しようとしていた先読みバイアスと
同じ構造（多重比較・researcher degrees of freedom）。

正しい手順：
1. IS前半だけで k を選ぶ（後半・OOSは一切見ない）
2. その固定k を IS後半へ適用する（独立したIS内検証）
3. その同じ固定k を OOS へ適用する（さらに独立した検証）
選択方法を1つに決めて固定し、複数の方法を試してから良いものを選ばない。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk

LIMIT = 24
GRID = [0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.0, 1.5, 2, 3]


def main():
    books = cc.load()
    is_deals = books[("both", "IS")]
    n = len(is_deals)
    mid = n // 2
    first_half = [p for _, p in is_deals[:mid]]      # 2021年側（先）
    second_half = [p for _, p in is_deals[mid:]]     # 2026年側（後）
    print(f"IS窓 {n}取引 → 前半(先){len(first_half)}取引 / 後半(後){len(second_half)}取引")

    rate_is_full = n / dk.MONTHS["IS"]
    H_half = int(round(rate_is_full * LIMIT)) // 2

    print("\n【手順1】IS前半だけでkを選ぶ（後半・OOSは見ない）")
    print(f"{'k':>6}{'前半P(到達)':>13}")
    scored = []
    paths_first = dk.generate_paths(first_half, H_half, dk.N_PATHS, dk.L, seed=111111)
    for k in GRID:
        r = dk.run_policy(paths_first, dk.policy_constant(k), H_half)
        scored.append((k, r["p_hit"]))
        print(f"  {k:>6}{100*r['p_hit']:>12.2f}%")
    best_k, best_p = max(scored, key=lambda x: x[1])
    print(f"→ 前半だけで選んだk = {best_k}（前半P(到達)={100*best_p:.2f}%）")

    print(f"\n【手順2】その固定k={best_k}を、見ていないIS後半へ適用（独立検証）")
    fn = dk.policy_constant(best_k)
    for seed in (222222, 333333, 444444):
        paths_second = dk.generate_paths(second_half, H_half, dk.N_PATHS, dk.L, seed=seed)
        r = dk.run_policy(paths_second, fn, H_half)
        print(f"  seed={seed}: 後半P(到達)={100*r['p_hit']:.2f}%  P(破綻)={100*r['p_ruin']:.2f}%"
              f"  P(期限切れ)={100*r['p_exp']:.2f}%")

    print(f"\n【手順3】その同じ固定k={best_k}を、OOS窓へ適用（さらに独立した検証）")
    t_oos = [p for _, p in books[("both", "OOS")]]
    rate_oos = len(t_oos) / dk.MONTHS["OOS"]
    H_oos = int(round(rate_oos * LIMIT))
    for seed in (62400, 70000, 80000, 90000, 100000):
        paths_oos = dk.generate_paths(t_oos, H_oos, dk.N_PATHS, dk.L, seed=seed)
        r = dk.run_policy(paths_oos, fn, H_oos)
        print(f"  seed={seed}: OOS P(到達)={100*r['p_hit']:.2f}%  P(破綻)={100*r['p_ruin']:.2f}%"
              f"  P(期限切れ)={100*r['p_exp']:.2f}%")


if __name__ == "__main__":
    main()
