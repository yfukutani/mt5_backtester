"""V067：**2倍を維持したまま期限を延ばす**と、いつ70%に届くか。

【残った最後のレバー】
新要件（資金10万円・3ヶ月・2倍・70%）に対し、これまでの結果：

| 軸 | 結果 |
|---|---|
| 破綻ラインの変更 | ❌ 50%は緩和でなく厳格化（V057） |
| 減速サイジング | ❌ −4.0〜−11.5pt（V058） |
| 加速サイジング | ❌ 一貫した利得なし（V062） |
| 目標倍率を1.3倍に下げる | ✅ OOS 74.8%（V060・**ただし要件変更**） |
| 頻度増（ブック平均の質を仮定） | ✅ 5倍で76.1%（V059・V061・**仮定が楽観的**） |
| **頻度増（SCA-FX相当の現実的な質）** | ❌ **8倍でも64.9%**（V066） |

**2倍を維持する道は「期限を延ばす」しか残っていない。**

【設計】
期限 ∈ {3, 4, 5, 6, 9, 12, 18, 24}ヶ月を事前に固定し、**すべて報告する。**
資金10万円・2倍・破綻ライン10%・最小ロット制約あり・移動ブロックL=20。
kは**IS窓で選ぶ**（OOSを見ない）。IS窓の結果も併記。

**判定は OOS到達率 ≥ 70%。破綻は併記するが判定に使わない**
（ユーザー指示「DDは制約にしない」に従う）。

【限界】
- 「ヶ月」は取引件数からの換算であり暦の期間ではない
- V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ
- **V062で判明したIS選択によるk決定の不安定さ（OOSで約6pt）が乗る**
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
TARGET_M = 2.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303, 404, 505)
RUIN = 0.10
L = 20
K_GRID = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0]
D_GRID = [3.0, 4.0, 5.0, 6.0, 9.0, 12.0, 18.0, 24.0]
MONTHS = cc.MONTHS


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


def main():
    print("=" * 112)
    print("V067：2倍を維持したまま期限を延ばすと、いつ70%に届くか")
    print("=" * 112)
    print(f"資金{CAPITAL:,.0f}円 / 目標2倍 / 破綻ライン{100*RUIN:.0f}% / "
          f"最小ロット制約あり / 移動ブロックL={L} / シード{len(SEEDS)}本")
    print("kはIS窓で選択（OOSを見ない）。**全期限を報告する。**\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        data[w] = (pr, vo, len(pr) / MONTHS[w])

    print(f"{'期限':>7}{'3ヶ月換算の取引数':>18}{'必要月利(複利)':>16}"
          f"│{'IS選択k':>9}{'IS到達':>9}{'IS破綻':>9}"
          f"│{'OOS到達':>9}{'OOS破綻':>9}{'OOS未決':>9}{'R3(70%)':>9}")
    first = None
    for d in D_GRID:
        rec = {}
        for w in ("IS", "OOS"):
            pr, vo, rate = data[w]
            H = int(round(rate * d))
            r = {}
            for k in K_GRID:
                hh, rr = [], []
                for sd in SEEDS:
                    pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=280000 + sd)
                    st_ = run(pp, vv, k)
                    hh.append(float((st_ == 1).mean()))
                    rr.append(float((st_ == 2).mean()))
                r[k] = (float(np.mean(hh)), float(np.mean(rr)))
            rec[w] = (r, H)
        k_sel = max(K_GRID, key=lambda k: rec["IS"][0][k][0])
        ih, ir = rec["IS"][0][k_sel]
        oh, orr = rec["OOS"][0][k_sel]
        ok = oh >= TARGET_P
        if ok and first is None:
            first = d
        mrate = (2.0 ** (1 / d) - 1) * 100
        print(f"{d:>6.0f}月{rec['OOS'][1]:>18}{mrate:>15.1f}%"
              f"│{k_sel:>9}{100*ih:>8.1f}%{100*ir:>8.1f}%"
              f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*(1-oh-orr):>8.1f}%"
              f"{'✅' if ok else '❌':>9}")

    print()
    if first is None:
        print(f"  → **{D_GRID[-1]:.0f}ヶ月まで延ばしてもOOSで70%に届かない**")
    else:
        print(f"  → **2倍・OOSで70%を満たす最短の期限は {first:.0f}ヶ月**")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・「ヶ月」は取引件数からの換算であり暦の期間ではない")
    print("  ・V062で判明したIS選択によるk決定の不安定さ（OOSで約6pt）が乗る")
    print("  ・V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ")
    print("\n完了。")


if __name__ == "__main__":
    main()
