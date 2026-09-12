"""V062：加速サイジングの効果は**シードノイズではないか**を多シードで確認する。

【なぜ疑うか】
同じ条件（頻度1倍・資金10万円・3ヶ月・2倍・破綻10%）で、加速方策 A(a=0.5) の
OOS到達率が**測定によって符号が逆になった。**

| 測定 | シード | P 比例 | A 加速 a=0.5 | 差 |
|---|---|---:|---:|---:|
| V058 | 230000系 | 42.2% | **47.9%** | **+5.68pt** |
| V061 | 260000系 | 51.4% | **46.0%** | **−5.40pt** |

**+5.68pt と −5.40pt。同じ方策・同じ条件で符号が逆である。**
V058で「加速は効く」と報告したが、**シードノイズだった可能性が高い。**

【設計】
シードを10本に増やし、**同一パスでのペア比較**（P と A に同じパスを見せる）にする。
ペア比較なら方策間の差だけを取り出せるので、パス生成のノイズが相殺される。

- 頻度倍率 f ∈ {1, 3, 5}
- 方策 ∈ {P 比例, A 加速 a=0.5, A 加速 a=1.0}
- kは各方策についてIS窓で選ぶ（OOSを見ない）
- **対応のある差と95%CIを出す**
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import realistic_sim as rs
from newreq_moving_block import gen_moving

CAPITAL = 100000.0
TARGET_M = 2.0
DEADLINE = 3.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = tuple(300000 + 1111 * i for i in range(10))
RUIN = 0.10
L = 20
K_GRID = [2.0, 3.0, 4.0, 6.0, 8.0, 12.0]
F_GRID = [1.0, 3.0, 5.0]
POLICIES = [("P 比例", 0.0), ("A 加速 a=0.5", -0.5), ("A 加速 a=1.0", -1.0)]
X_CLIP = (0.25, 4.0)
MONTHS = cc.MONTHS


def run(pp, vv, k, a):
    n_paths, H = pp.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    for step in range(H):
        if not alive.any():
            break
        x = np.maximum(eq / CAPITAL, 1e-6)
        adj = np.clip(x ** a, X_CLIP[0], X_CLIP[1]) if a != 0.0 else 1.0
        v = vv[:, step]
        actual = np.maximum(MIN_LOT, np.floor(v * k * x * adj / STEP + 1e-9) * STEP)
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= CAPITAL * TARGET_M)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state == 1


def main():
    print("=" * 108)
    print("V062：加速サイジングの効果はシードノイズではないか（多シード・ペア比較）")
    print("=" * 108)
    print(f"シード{len(SEEDS)}本・各{N_PATHS:,}パス。**同一パスでP とA を比較する**（ペア比較）")
    print("V058は+5.68pt、V061は−5.40pt。同じ条件で符号が逆だった\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        data[w] = (pr, vo, len(pr) / MONTHS[w])

    for f in F_GRID:
        print("=" * 108)
        print(f"【頻度倍率 {f:g}倍】")
        print("=" * 108)
        # --- 各方策のkをIS窓で選ぶ ---
        ksel = {}
        for name, a in POLICIES:
            pr, vo, rate = data["IS"]
            H = int(round(rate * f * DEADLINE))
            best, bp = None, -1.0
            for k in K_GRID:
                vals = []
                for sd in SEEDS[:3]:
                    pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=sd)
                    vals.append(float(run(pp, vv, k, a).mean()))
                m = float(np.mean(vals))
                if m > bp:
                    best, bp = k, m
            ksel[name] = (best, bp)

        # --- OOSで多シード・ペア比較 ---
        pr, vo, rate = data["OOS"]
        H = int(round(rate * f * DEADLINE))
        per_seed = {name: [] for name, _ in POLICIES}
        diffs = {name: [] for name, _ in POLICIES if name != "P 比例"}
        for sd in SEEDS:
            pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=sd)
            succ = {}
            for name, a in POLICIES:
                succ[name] = run(pp, vv, ksel[name][0], a)
                per_seed[name].append(float(succ[name].mean()))
            for name, _ in POLICIES:
                if name == "P 比例":
                    continue
                d = succ[name].astype(float) - succ["P 比例"].astype(float)
                diffs[name].append(float(d.mean()))

        print(f"{'方策':>14}{'IS選択k':>9}{'IS到達':>9}"
              f"│{'OOS到達(平均)':>15}{'最小':>9}{'最大':>9}{'シード間SD':>12}")
        for name, _ in POLICIES:
            v = np.array(per_seed[name])
            print(f"{name:>14}{ksel[name][0]:>9}{100*ksel[name][1]:>8.1f}%"
                  f"│{100*v.mean():>14.1f}%{100*v.min():>8.1f}%{100*v.max():>8.1f}%"
                  f"{100*v.std(ddof=1):>11.2f}pt")

        print(f"\n{'方策':>14}{'ペア差(平均)':>14}{'95%CI':>22}{'符号が安定か':>14}")
        for name in diffs:
            d = np.array(diffs[name])
            m = float(d.mean())
            se = float(d.std(ddof=1) / math.sqrt(len(d)))
            lo, hi = m - 1.96 * se, m + 1.96 * se
            same = "✅ 一定" if (lo > 0 or hi < 0) else "❌ 符号不定"
            pos = int((d > 0).sum())
            print(f"{name:>14}{100*m:>+13.2f}pt"
                  f"{f'[{100*lo:+.2f}, {100*hi:+.2f}]pt':>22}{same:>14}"
                  f"  （+の回数 {pos}/{len(d)}）")
        print()

    print("=" * 108)
    print("【読み方】")
    print("=" * 108)
    print("  ・ペア差の95%CIが0を跨ぐなら、その方策の効果は**確認できていない**")
    print("  ・シード間SDが大きいなら、単一シードの測定は信用できない")
    print("\n完了。")


if __name__ == "__main__":
    main()
