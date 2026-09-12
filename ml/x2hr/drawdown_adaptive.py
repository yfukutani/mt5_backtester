"""V058：方向②——**破綻で失われる分**を、資金水準に応じた減速で取り戻せるか。

【V056の枠組みから導かれる唯一の余地】
V056で、3ヶ月・2倍の到達確率には **P → Φ(3ヶ月シャープ)** という天井があり、
OOS窓では **74.4%**（破綻無視）と分かった。一方 V035 の先読み探索の最大値は
**65.3%** だった。**差の9.1ptが破綻によって失われている分**である。

**したがって「破綻を減らしつつ到達を保つ」ことができれば、最大9.1pt取り戻せる。**
これは新要件（70%）との差を埋めるのに十分な大きさである。

【案：資金水準に応じた非対称な倍率】
比例サイジング（k×資金比）は、資金が減ると自動的にロットも減る。
しかし**破綻ラインの手前でさらに強く減速すれば、破綻を避けながら
「期限切れ」に変えられる**はずである。期限切れは失敗だが、破綻と違って
資金が残る——そして3ヶ月という短い期限では、**破綻を期限切れに変えるだけでは
到達率は上がらない。**

**だから逆を試す。** 破綻が近いパスは「どうせ届かない」ので、
**むしろ賭けを大きくして到達を狙う**ほうが到達率は上がるはずである。
到達率だけを目的関数にするなら、**資金が減ったら増額する**のが正しい
（Browne式のC族が持っている性質でもある）。

【3つの方策を事前登録して全て報告する】

| 方策 | 式 | 意図 |
|---|---|---|
| **P（比例・基準）** | `k` | 資金比に比例（従来） |
| **D（減速）** | `k × x^a`（a>0） | 資金が減ったら**さらに減らす**＝破綻回避 |
| **A（加速）** | `k × x^(−a)`（a>0） | 資金が減ったら**増やす**＝到達を狙う |

`x = 現在資金 / 初期資金`。実装は比例サイジングの上に `x^(±a)` を掛ける形。
a ∈ {0.5, 1.0} を事前に固定する。

**k と a は IS窓で選ぶ。OOSを見て選び直さない。全条件を報告する。**
継続基準：OOS到達率が P（比例）比 **+2pt以上**、かつ破綻確率が悪化しないこと。

【評価条件】
資金100,000円・期限3ヶ月・破綻ライン10%・最小ロット制約あり・
移動ブロック L=100（実履歴の連続3ヶ月に最も近い）
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
L = 100
K_GRID = [2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0]
POLICIES = [("P 比例（基準）", 0.0), ("D 減速 a=0.5", 0.5), ("D 減速 a=1.0", 1.0),
            ("A 加速 a=0.5", -0.5), ("A 加速 a=1.0", -1.0)]
MONTHS = cc.MONTHS
X_CLIP = (0.25, 4.0)     # x^(±a) の倍率が暴れないよう上下限を置く


def run(pp, vv, k, a):
    """k × x^(-a) 型。a>0で減速、a<0で加速。x は資金比。"""
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
        desired = v * k * x * adj
        actual = np.maximum(MIN_LOT, np.floor(desired / STEP + 1e-9) * STEP)
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= CAPITAL * 2.0)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state


def main():
    print("=" * 118)
    print("V058：資金水準に応じた非対称な倍率で、破綻で失われる分を取り戻せるか")
    print("=" * 118)
    print(f"資金{CAPITAL:,.0f}円 / 期限{DEADLINE:g}ヶ月 / 破綻ライン{100*RUIN:.0f}% / "
          f"最小ロット制約あり / 移動ブロックL={L}")
    print("V056の天井は OOS 74.4%（破綻無視）。V035の先読み最大値は65.3%。")
    print("**差の9.1ptが破綻で失われている分**であり、ここが唯一の余地。\n")
    print("**全方策・全kを報告する。良かったものだけを選ばない。**\n")

    data = {}
    for w in ("IS", "OOS"):
        pr, vo, _ = rs.build(w)[1], rs.build(w)[2], None
        tt, pr, vo = rs.build(w)
        rate = len(pr) / MONTHS[w]
        data[w] = (pr, vo, int(round(rate * DEADLINE)))

    results = {}
    for name, a in POLICIES:
        print(f"--- {name} ---")
        print(f"{'k':>6}{'IS到達':>9}{'IS破綻':>9}{'IS未決':>9}"
              f"│{'OOS到達':>9}{'OOS破綻':>9}{'OOS未決':>9}{'R3(70%)':>9}")
        best_is, bp = None, -1.0
        rows = {}
        for k in K_GRID:
            out = {}
            for w in ("IS", "OOS"):
                pr, vo, H = data[w]
                hh, rr = [], []
                for sd in SEEDS:
                    pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=230000 + sd)
                    st = run(pp, vv, k, a)
                    hh.append(float((st == 1).mean()))
                    rr.append(float((st == 2).mean()))
                out[w] = (float(np.mean(hh)), float(np.mean(rr)))
            rows[k] = out
            ih, ir = out["IS"]
            oh, orr = out["OOS"]
            if ih > bp:
                best_is, bp = k, ih
            print(f"{k:>6}{100*ih:>8.1f}%{100*ir:>8.1f}%{100*(1-ih-ir):>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*(1-oh-orr):>8.1f}%"
                  f"{'✅' if oh >= TARGET_P else '❌':>9}")
        results[name] = (best_is, rows[best_is]["IS"], rows[best_is]["OOS"])
        ih, ir = rows[best_is]["IS"]
        oh, orr = rows[best_is]["OOS"]
        print(f"  → IS選択 k={best_is}：IS {100*ih:.1f}% / OOS {100*oh:.1f}%"
              f"（破綻{100*orr:.1f}%）\n")

    print("=" * 118)
    print("【継続基準】OOS到達率が P（比例）比 +2pt以上、かつ破綻確率が悪化しないこと")
    print("=" * 118)
    base = results["P 比例（基準）"]
    print(f"{'方策':>16}{'IS選択k':>9}{'OOS到達':>10}{'OOS破綻':>10}"
          f"{'基準比':>10}{'判定':>14}")
    ok = False
    for name, _ in POLICIES:
        k, (ih, ir), (oh, orr) = results[name]
        d = (oh - base[2][0]) * 100
        dr = (orr - base[2][1]) * 100
        if name == "P 比例（基準）":
            v = "（基準）"
        else:
            good = (d >= 2.0 and dr <= 0.0)
            ok = ok or good
            v = "✅ 満たす" if good else "❌ 満たさない"
        print(f"{name:>16}{k:>9}{100*oh:>9.1f}%{100*orr:>9.1f}%"
              f"{d:>+9.2f}pt{v:>14}")
    print(f"\n判定: {'**この軸は有望**' if ok else '**この軸は却下**'}")
    print("\n完了。")


if __name__ == "__main__":
    main()
