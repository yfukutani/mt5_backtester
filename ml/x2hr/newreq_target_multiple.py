"""V060：**3ヶ月・70%で狙える倍率はいくつか**（Codex提案）。

【なぜこれを測るのか】
Codexは要件のどこを緩めるのが効果的かについて次のように答えた。

> **2倍という目標を残すなら期限延長。3ヶ月を残すなら目標倍率引下げです。**
> 目標倍率を下げるのは**3ヶ月固定なら最も直接的**。同じ方策なら、低い目標への到達確率は
> 下がりません。1.2倍・1.3倍・1.5倍などを比較する価値がありますが、
> **どこで70%になるかは未検証です。**

ユーザーの要件は「2倍」で固定されているが、**「3ヶ月・70%なら何倍まで狙えるか」は
ユーザーが要件を再検討するための材料になる。** 2倍が届かないことを報告するだけでなく、
**届く水準を示す。**

【設計】
目標倍率 M ∈ {1.1, 1.2, 1.3, 1.5, 1.75, 2.0} を事前に固定し、**すべて報告する。**
各Mについて、資金10万円・期限3ヶ月・破綻ライン10%・最小ロット制約あり・移動ブロックL=20で、
**kをIS窓で選び**（OOSを見ない）、OOS窓へ適用する。IS窓の結果も併記する。

【限界】
V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ。
また「ヶ月」は取引件数からの換算であり暦の期間ではない。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import realistic_sim as rs
from newreq_moving_block import gen_moving

CAPITAL = 100000.0
TARGET_P = 0.70
DEADLINE = 3.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
RUIN = 0.10
L = 20
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0]
M_GRID = [1.1, 1.2, 1.3, 1.5, 1.75, 2.0]
MONTHS = cc.MONTHS


def run(pp, vv, k, mult):
    n_paths, H = pp.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    for step in range(H):
        if not alive.any():
            break
        x = eq / CAPITAL
        v = vv[:, step]
        actual = np.maximum(MIN_LOT, np.floor(v * k * x / STEP + 1e-9) * STEP)
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= CAPITAL * mult)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state


def main():
    print("=" * 112)
    print("V060：3ヶ月・70%で狙える倍率はいくつか（資金10万円・破綻ライン10%）")
    print("=" * 112)
    print("Codex：「3ヶ月を残すなら目標倍率引下げが最も直接的」")
    print("**全ての倍率を報告する。良かったものだけを選ばない。**\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        rate = len(pr) / MONTHS[w]
        data[w] = (pr, vo, int(round(rate * DEADLINE)))

    print(f"{'目標倍率':>9}{'必要利益':>11}{'必要月利(複利)':>16}"
          f"│{'IS選択k':>9}{'IS到達':>9}{'IS破綻':>9}"
          f"│{'OOS到達':>9}{'OOS破綻':>9}{'R3(70%)':>9}")
    reached = None
    for M in M_GRID:
        rec = {}
        for w in ("IS", "OOS"):
            pr, vo, H = data[w]
            r = {}
            for k in K_GRID:
                hh, rr = [], []
                for sd in SEEDS:
                    pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=250000 + sd)
                    st = run(pp, vv, k, M)
                    hh.append(float((st == 1).mean()))
                    rr.append(float((st == 2).mean()))
                r[k] = (float(np.mean(hh)), float(np.mean(rr)))
            rec[w] = r
        k_sel = max(K_GRID, key=lambda k: rec["IS"][k][0])
        ih, ir = rec["IS"][k_sel]
        oh, orr = rec["OOS"][k_sel]
        need = CAPITAL * (M - 1)
        mrate = (M ** (1 / 3) - 1) * 100
        ok = oh >= TARGET_P
        if ok and reached is None:
            reached = M
        print(f"{M:>8.2f}x{need:>11,.0f}{mrate:>15.1f}%"
              f"│{k_sel:>9}{100*ih:>8.1f}%{100*ir:>8.1f}%"
              f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{'✅' if ok else '❌':>9}")

    print()
    if reached is None:
        print(f"  → **{M_GRID[0]:g}倍でもOOSで70%に届かない**")
    else:
        print(f"  → **3ヶ月・OOSで70%を満たす最大の倍率は {reached:g}倍**")
        print(f"     （それより上の倍率は70%に届かない）")

    print("\n" + "=" * 112)
    print("【限界】V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ")
    print("  ・入口時点でのロット固定を実装していない")
    print("  ・丸め前の基準ロットではなく約定ロットに倍率を掛けている")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・「ヶ月」は取引件数からの換算であり暦の期間ではない")
    print("\n完了。")


if __name__ == "__main__":
    main()
