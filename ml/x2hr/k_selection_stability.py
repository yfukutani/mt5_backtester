"""V068：**IS選択によるk決定の不安定さ**を抑える手続きを探す。

【なぜこれが最優先か】
V062で、この評価系の最大の不安定要因が**パス生成のノイズではなくk選択**だと判明した。

- パス生成のシード間SD：**0.29〜0.35pt**（小さい）
- **同じ条件でIS選択がk=6とk=8で揺れ、OOSが約6pt動く**

V067でも症状が出ている——**5ヶ月のOOS到達率48.2%が4ヶ月の53.0%より低い。**
固定方策なら期限が延びて到達率が下がることはあり得ず、
**IS選択がk=6からk=4へ変わったため**である。

**この不安定さを抑えないと、どの数値も±6ptの幅を持ってしまう。**

【原因の仮説】
IS窓の到達確率は**kに対して平坦**なのではないか。平坦なら、わずかなノイズで
argmax が別のkへ飛ぶ。V023で24ヶ月について同じ現象を確認している
（「IS成績がk∈[0.4,0.7]でほぼ平坦になり、グリッドの粗さで結論が反転する」）。

【本スクリプトがすること】
1. **IS窓の到達確率のkに対する形**を、多シードで精密に出す（平坦かどうかを見る）
2. **3つの選択規則を事前登録して比較する**

| 規則 | 内容 | 狙い |
|---|---|---|
| **R1 argmax（現行）** | IS到達率が最大のk | 基準 |
| **R2 平坦域の中央** | IS到達率が「最大−1pt」以内のkの中央値 | 平坦域での飛びを抑える |
| **R3 破綻控除後のargmax** | IS到達率 −0.5×IS破綻率 が最大のk | 破綻の多い端を避ける |

各規則について**10シードで選択を繰り返し、選ばれるkのばらつきとOOSのばらつき**を出す。
**選択が安定し、かつOOSが下がらない規則があれば採用する。**

【限界】
- 3規則はこの記録で事前に決めたものであり、結果を見てから増やさない
- 「最大−1pt以内」「0.5×破綻率」という係数は設計上の選択である
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import realistic_sim as rs
from newreq_moving_block import gen_moving

CAPITAL = 100000.0
TARGET_M = 2.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEL_SEEDS = tuple(400000 + 777 * i for i in range(10))
EVAL_SEED = 500001
RUIN = 0.10
L = 20
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
D_GRID = [3.0, 6.0, 12.0]
MONTHS = cc.MONTHS
FLAT_TOL = 0.01      # 「最大−1pt以内」
RUIN_PEN = 0.5       # 破綻控除の係数


def run(pp, vv, k):
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
        hit = alive & (eq >= CAPITAL * TARGET_M)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state


def select(rule, hits, ruins):
    """hits/ruins は {k: 値}。規則に従ってkを選ぶ。"""
    if rule == "R1 argmax":
        return max(K_GRID, key=lambda k: hits[k])
    if rule == "R2 平坦域の中央":
        best = max(hits.values())
        flat = [k for k in K_GRID if hits[k] >= best - FLAT_TOL]
        return flat[len(flat) // 2]
    if rule == "R3 破綻控除":
        return max(K_GRID, key=lambda k: hits[k] - RUIN_PEN * ruins[k])
    raise ValueError(rule)


def main():
    print("=" * 108)
    print("V068：IS選択によるk決定の不安定さを抑える手続きを探す")
    print("=" * 108)
    print("V062：パス生成のノイズは0.3pt。**k選択の揺れがOOSを約6pt動かす。**")
    print("V067：5ヶ月(48.2%)が4ヶ月(53.0%)より低いのも、k=6→k=4の選択変化が原因。\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        data[w] = (pr, vo, len(pr) / MONTHS[w])

    for d in D_GRID:
        print("=" * 108)
        print(f"【期限 {d:.0f}ヶ月】")
        print("=" * 108)

        # --- IS窓の形を多シードで精密に出す ---
        pr, vo, rate = data["IS"]
        H = int(round(rate * d))
        is_hits = {k: [] for k in K_GRID}
        is_ruins = {k: [] for k in K_GRID}
        for sd in SEL_SEEDS:
            pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=sd)
            for k in K_GRID:
                st_ = run(pp, vv, k)
                is_hits[k].append(float((st_ == 1).mean()))
                is_ruins[k].append(float((st_ == 2).mean()))

        print("  【IS窓の到達確率のkに対する形】（10シード）")
        print(f"{'k':>6}{'IS到達(平均)':>14}{'最小':>9}{'最大':>9}{'SD':>9}"
              f"{'IS破綻':>9}{'最大との差':>12}")
        means = {k: float(np.mean(is_hits[k])) for k in K_GRID}
        best = max(means.values())
        for k in K_GRID:
            v = np.array(is_hits[k])
            mark = "  ←最大" if means[k] == best else ""
            print(f"{k:>6}{100*means[k]:>13.1f}%{100*v.min():>8.1f}%"
                  f"{100*v.max():>8.1f}%{100*v.std(ddof=1):>8.2f}pt"
                  f"{100*np.mean(is_ruins[k]):>8.1f}%"
                  f"{100*(best-means[k]):>11.2f}pt{mark}")
        flat = [k for k in K_GRID if means[k] >= best - FLAT_TOL]
        print(f"\n  最大−1pt以内のk：{flat}  → **{len(flat)}個が実質同等**")

        # --- 3規則で選択を繰り返す ---
        pr_o, vo_o, rate_o = data["OOS"]
        H_o = int(round(rate_o * d))
        pp_o, vv_o = gen_moving(pr_o, vo_o, H_o, N_PATHS, L, seed=EVAL_SEED)
        oos_cache = {}
        for k in K_GRID:
            st_ = run(pp_o, vv_o, k)
            oos_cache[k] = (float((st_ == 1).mean()), float((st_ == 2).mean()))

        print(f"\n  【3つの選択規則の比較】（各シードで選択→同じOOSパスで評価）")
        print(f"{'規則':>16}{'選ばれたk（10シード）':>26}"
              f"{'OOS到達(平均)':>15}{'最小':>9}{'最大':>9}{'幅':>9}")
        for rule in ("R1 argmax", "R2 平坦域の中央", "R3 破綻控除"):
            ks, ohs = [], []
            for i, sd in enumerate(SEL_SEEDS):
                h = {k: is_hits[k][i] for k in K_GRID}
                r = {k: is_ruins[k][i] for k in K_GRID}
                k_sel = select(rule, h, r)
                ks.append(k_sel)
                ohs.append(oos_cache[k_sel][0])
            c = Counter(ks)
            desc = " ".join(f"k={k}×{n}" for k, n in sorted(c.items()))
            v = np.array(ohs)
            print(f"{rule:>16}{desc:>26}{100*v.mean():>14.1f}%"
                  f"{100*v.min():>8.1f}%{100*v.max():>8.1f}%"
                  f"{100*(v.max()-v.min()):>8.1f}pt")
        print()

    print("=" * 108)
    print("【判定の見方】")
    print("=" * 108)
    print("  ・『幅』が小さい規則ほど選択が安定している")
    print("  ・ただし安定していてもOOS平均が下がるなら意味がない")
    print("  ・『最大−1pt以内のk』が複数あるなら、IS窓の形が平坦で")
    print("    argmaxがノイズで飛んでいるということ")
    print("\n完了。")


if __name__ == "__main__":
    main()
