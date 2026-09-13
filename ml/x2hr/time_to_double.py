"""V044：期限なしで2倍に届くのは確定した。では**どれだけ時間がかかるか**。

【V043で分かったこと】
期限を外すと、破綻ライン10%・倍率k=0.25（IS選択）で **OOS到達率100.0%・破綻0.0%・
打ち切り0.0%**。ユーザーの標準指示「**破綻するまでに**資金が2倍になる確率85%」は、
**期限を外せば大きな余裕をもって達成される。** 難しかったのは一貫して R4（期限1〜2ヶ月）
のほうだった。

**したがって残る唯一の問いは「どれだけ待つのか」である。**

【本スクリプトが出すもの】
倍率kごとに、2倍到達までの所要期間の分布（中央値・25/75/90/95%点）を
**暦月換算**で出す。破綻確率・打ち切り率も併記する。IS窓・OOS窓の両方を出す。

【暦月換算の注意】
所要「取引数」を窓の平均月間頻度で割って月に直している。
**取引頻度が一定という仮定が入っている**（V040で頻度は年ごとに変動すると分かっている）。
したがって月数は目安であり、精密な予測ではない。
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
N_PATHS = 20000
SEEDS = (101, 202, 303)
K_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
LONG_MONTHS = 240.0      # 打ち切りを避けるため十分長く取る
RUIN = 0.10


def run(paths, k, ruin_frac):
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
    return state, stop


def main():
    books = dkl.build_books()
    out = {}
    for w in ("IS", "OOS"):
        pr, lg, _ = books[w]
        rate = len(pr) / MONTHS[w]
        H = int(round(rate * LONG_MONTHS))
        out[w] = (pr, rate, H)

    print("=" * 112)
    print("V044：期限なしで2倍に届くまでの**所要期間**（破綻ライン10%）")
    print("=" * 112)
    print("V043で、期限を外せば到達率はOOSでも100%（k=0.25）と確定した。")
    print("残る問いは『どれだけ待つのか』。以下は所要期間の分布（暦月換算）。\n")
    print("⚠️ 暦月換算は窓の平均月間頻度を使った目安。取引頻度が一定という仮定が入っている")
    print(f"   （IS {out['IS'][1]:.1f}件/月 / OOS {out['OOS'][1]:.1f}件/月）\n")

    for w in ("IS", "OOS"):
        pr, rate, H = out[w]
        print("=" * 112)
        print(f"【{w}窓】{len(pr)}取引 / 平均{pr.mean():.1f}円 / "
              f"月{rate:.1f}件 / ホライズン{LONG_MONTHS:.0f}ヶ月（{H}取引）")
        print("=" * 112)
        print(f"{'k':>6}{'到達':>8}{'破綻':>8}{'打切':>8}"
              f"│{'中央値':>9}{'25%点':>9}{'75%点':>9}{'90%点':>9}{'95%点':>9}"
              f"{'平均':>9}")
        for k in K_GRID:
            hits, ruins, cuts = [], [], []
            allsteps = []
            for sd in SEEDS:
                paths = dk.generate_paths(pr, H, N_PATHS, dkl.L, seed=990000 + sd)
                state, stop = run(paths, k, RUIN)
                hits.append(float((state == 1).mean()))
                ruins.append(float((state == 2).mean()))
                cuts.append(float((state == 0).mean()))
                allsteps.append(stop[state == 1])
            st = np.concatenate(allsteps) if allsteps else np.array([])
            if st.size:
                q = np.percentile(st, [25, 50, 75, 90, 95]) / rate
                mean_m = st.mean() / rate
                print(f"{k:>6}{100*np.mean(hits):>7.1f}%{100*np.mean(ruins):>7.1f}%"
                      f"{100*np.mean(cuts):>7.1f}%│{q[1]:>8.1f}月{q[0]:>8.1f}月"
                      f"{q[2]:>8.1f}月{q[3]:>8.1f}月{q[4]:>8.1f}月{mean_m:>8.1f}月")
            else:
                print(f"{k:>6}{100*np.mean(hits):>7.1f}%{100*np.mean(ruins):>7.1f}%"
                      f"{100*np.mean(cuts):>7.1f}%│  到達なし")
        print()

    print("=" * 112)
    print("【読み方】")
    print("=" * 112)
    print("  ・kを上げると速いが破綻確率が上がる。kを下げると確実だが遅い")
    print("  ・『破綻するまでに2倍』という目標だけなら低いkで100%に届く")
    print("  ・実務的な判断材料は『その期間を待てるか』であって到達確率ではない")
    print("  ・ホライズンを超えて未決着のパス（打切）が0%であることを必ず確認する")
    print("\n完了。")


if __name__ == "__main__":
    main()
