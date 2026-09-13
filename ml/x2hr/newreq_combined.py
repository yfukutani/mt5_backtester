"""V061：**2つのレバーを組み合わせる**——頻度増 × 加速サイジング。

【第1ラウンドで分かったこと】
| 検証 | 結果 |
|---|---|
| V057 | 現状：資金10万円・3ヶ月・2倍で **OOS 41.9〜51.7%**（目標70%） |
| V058 | 加速サイジング A(a=0.5) で **+5.68pt**（到達47.9%・破綻12.8%） |
| V059 | 70%到達に必要な頻度倍率は **5倍**（月167件・75枠相当） |
| V060 | 3ヶ月・70%で狙える倍率は **1.1倍**まで（2倍では45.8%） |

**単独ではどちらも足りない。組み合わせて何倍の頻度が必要になるかを測る。**

【設計（事前登録）】
- 頻度倍率 f ∈ {1, 2, 3, 4, 5}
- 方策 ∈ {P 比例（基準）, A 加速 a=0.5, A 加速 a=1.0}
- **全組み合わせを報告する。良かったものだけを選ばない。**
- 目標は **2倍**（ユーザー要件）。資金10万円・期限3ヶ月・破綻ライン10%
- kは**IS窓で選ぶ**（OOSを見ない）。IS窓の結果も併記
- 判定基準は **OOS到達率 ≥ 70%**。破綻確率は副次情報として併記するが、
  **ユーザー指示「DDは制約にしない」に従い、判定には使わない**
  （V058で私が誤って破綻を判定条件に入れていたのを修正）

【限界】
- 「増えた取引の質が既存と同等」という最も楽観的な仮定
- V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ
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
DEADLINE = 3.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
RUIN = 0.10
L = 20
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0]
F_GRID = [1.0, 2.0, 3.0, 4.0, 5.0]
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
    return state


def main():
    print("=" * 116)
    print("V061：頻度増 × 加速サイジングの組み合わせ（資金10万円・3ヶ月・2倍・目標70%）")
    print("=" * 116)
    print("**全組み合わせを報告する。良かったものだけを選ばない。**")
    print("判定は OOS到達率 ≥ 70% のみ。破綻は併記するが判定に使わない")
    print("（ユーザー指示「DDは制約にしない」に従う）\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        data[w] = (pr, vo, len(pr) / MONTHS[w])

    print(f"{'頻度':>6}{'方策':>14}{'3ヶ月取引数':>12}"
          f"│{'IS選択k':>9}{'IS到達':>9}{'IS破綻':>9}"
          f"│{'OOS到達':>9}{'OOS破綻':>9}{'R3(70%)':>9}")
    found = []
    for f in F_GRID:
        for name, a in POLICIES:
            rec = {}
            for w in ("IS", "OOS"):
                pr, vo, rate = data[w]
                H = int(round(rate * f * DEADLINE))
                r = {}
                for k in K_GRID:
                    hh, rr = [], []
                    for sd in SEEDS:
                        pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=260000 + sd)
                        st = run(pp, vv, k, a)
                        hh.append(float((st == 1).mean()))
                        rr.append(float((st == 2).mean()))
                    r[k] = (float(np.mean(hh)), float(np.mean(rr)))
                rec[w] = (r, H)
            k_sel = max(K_GRID, key=lambda k: rec["IS"][0][k][0])
            ih, ir = rec["IS"][0][k_sel]
            oh, orr = rec["OOS"][0][k_sel]
            ok = oh >= TARGET_P
            if ok:
                found.append((f, name, k_sel, oh, orr))
            print(f"{f:>5.0f}x{name:>14}{rec['OOS'][1]:>12}"
                  f"│{k_sel:>9}{100*ih:>8.1f}%{100*ir:>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{'✅' if ok else '❌':>9}")
        print()

    print("=" * 116)
    print("【判定】OOS到達率 ≥ 70% を満たした組み合わせ")
    print("=" * 116)
    if not found:
        print("  なし。頻度5倍×加速でも70%に届かない")
    else:
        for f, name, k, oh, orr in found:
            rate = data["OOS"][2]
            print(f"  頻度{f:g}倍（月{rate*f:.0f}件・{15*f:.0f}枠相当） × {name} × k={k}"
                  f" → OOS到達 {100*oh:.1f}%（破綻 {100*orr:.1f}%）")
        f_min = min(x[0] for x in found)
        print(f"\n  → **必要な最小の頻度倍率は {f_min:g}倍**")

    print("\n" + "=" * 116)
    print("【限界】")
    print("  ・「増えた取引の質が既存と同等」という最も楽観的な仮定")
    print("  ・V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ")
    print("\n完了。")


if __name__ == "__main__":
    main()
