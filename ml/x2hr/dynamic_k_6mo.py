"""V014の続き：動的サイジング(B方策)を6ヶ月期限へ拡張する。

2ヶ月期限でOOS有意改善(+6.25pt)が出たB方策（目標距離×残り時間）について、
期限を6ヶ月まで伸ばすと改善幅がどう変わるかを見る。dynamic_k.py と同じ
IS選択→OOS/FULL適用のプロトコルをそのまま踏襲する。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk

LIMIT_MONTHS = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def main():
    books = cc.load()
    t_is = [p for _, p in books[("both", "IS")]]
    n_is = len(t_is)
    rate_is = n_is / dk.MONTHS["IS"]
    H_is = int(round(rate_is * LIMIT_MONTHS))

    const_grid = [0.25, 0.5, 1, 1.5, 2, 3, 4]
    A_grid = [(k0, a) for k0 in const_grid for a in (0.5, 1.0)]
    B_grid = const_grid
    C_grid = [0.75, 1.0, 1.25]

    n_is_all = n_is
    mean_is = sum(t_is) / n_is_all
    import math
    sd_is = math.sqrt(sum((x - mean_is) ** 2 for x in t_is) / (n_is_all - 1))
    s_is = sd_is / dk.CAPITAL

    print(f"【IS選択（全方策族・pre-registered）】期限 {LIMIT_MONTHS}ヶ月（H_is={H_is}steps）")
    paths_is = dk.generate_paths(t_is, H_is, dk.N_PATHS, dk.L, seed=20260913 + LIMIT_MONTHS)

    candidates = []
    for k in const_grid:
        candidates.append(("const", (k,), dk.policy_constant(k)))
    for k0, a in A_grid:
        candidates.append(("A", (k0, a), dk.policy_A(k0, a)))
    for k0 in B_grid:
        candidates.append(("B", (k0,), dk.policy_B(k0)))
    for c in C_grid:
        candidates.append(("C", (c,), dk.policy_C(c, s_is)))

    scored = []
    for fam, params, fn in candidates:
        r = dk.run_policy(paths_is, fn, H_is)
        scored.append((fam, params, r["p_hit"]))

    best_const = max((x for x in scored if x[0] == "const"), key=lambda x: x[2])
    best_by_fam = {}
    for fam in ("A", "B", "C"):
        best_by_fam[fam] = max((x for x in scored if x[0] == fam), key=lambda x: x[2])
    best_dyn = max(best_by_fam.values(), key=lambda x: x[2])

    print(f"  IS最良 constant: k={best_const[1][0]}  P(2倍)={100*best_const[2]:.1f}%")
    for fam, x in best_by_fam.items():
        print(f"  IS最良 {fam}: params={x[1]}  P(2倍)={100*x[2]:.1f}%")
    winner = "動的" if best_dyn[2] > best_const[2] else "constant"
    print(f"  → 全体のIS勝者: {winner}"
          f"（動的最良={best_dyn[0]}{best_dyn[1]}={100*best_dyn[2]:.1f}% "
          f"vs constant={100*best_const[2]:.1f}%）")

    best_const_k = best_const[1][0]
    fam_fn = {"const": dk.policy_constant, "A": lambda p: dk.policy_A(*p),
              "B": lambda p: dk.policy_B(*p), "C": lambda p: dk.policy_C(p[0], s_is)}
    const_fn = dk.policy_constant(best_const_k)
    dyn_fam, dyn_params = best_dyn[0], best_dyn[1]
    dyn_fn = fam_fn[dyn_fam](dyn_params)
    print(f"\n  ※以下はIS勝者に関わらず両方をOOS/FULLで比較する（診断目的）")

    print(f"\n【固定方策をIS/OOS/FULLへ適用】constant=k{best_const_k} / 動的={dyn_fam}{dyn_params}")
    print(f"{'窓':>5}{'方策':>9}{'P(2倍)':>9}{'P(破綻)':>9}{'P(期限切れ)':>12}{'到達中央値':>11}")
    for w in ("IS", "OOS", "FULL"):
        t = [p for _, p in books[("both", w)]]
        n = len(t)
        rate = n / dk.MONTHS[w]
        H = int(round(rate * LIMIT_MONTHS))
        paths = dk.generate_paths(t, H, dk.N_PATHS, dk.L, seed=40000 + LIMIT_MONTHS * 100 + hash(w) % 97)
        r_const = dk.run_policy(paths, const_fn, H)
        r_dyn = dk.run_policy(paths, dyn_fn, H)
        for name, r in (("constant", r_const), (f"動的{dyn_fam}", r_dyn)):
            med = f"{r['median_steps']}" if r['median_steps'] is not None else "—"
            print(f"{w:>5}{name:>9}{100*r['p_hit']:>8.1f}%{100*r['p_ruin']:>8.1f}%"
                  f"{100*r['p_exp']:>11.1f}%{med:>11}")
        diff, ci = dk.paired_diff(r_dyn, r_const, dk.N_PATHS)
        sig = "有意" if ci[0] > 0 else ("有意に劣る" if ci[1] < 0 else "有意差なし")
        print(f"      差(動的-constant): {100*diff:+.2f}pt  95%CI [{100*ci[0]:+.2f}, {100*ci[1]:+.2f}]pt  ({sig})")


if __name__ == "__main__":
    main()
