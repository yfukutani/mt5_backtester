"""V059：新要件で**70%に届くには取引機会が何倍必要か**を逆算する。

【V056の枠組み】
3ヶ月・2倍の到達確率には **P → Φ(3ヶ月シャープ)** という天井がある。

    3ヶ月シャープ ＝ 1取引あたりシャープ × √(3ヶ月の取引数)

OOS窓：0.0656 × √100 ＝ 0.657 → 天井 74.4%（破綻無視）
実測（V057・L=20・先読み最良）：**56.1%**。差の18.3ptが破綻で失われている。

**天井を上げる方法は「1取引あたりのシャープを上げる」か
「3ヶ月の取引数を増やす」かの2つしかない。** 後者は√で効く。

本スクリプトは**取引機会を何倍にすれば70%に届くか**を逆算する。

【前提（必ず併記すること）】
「増えた取引機会も既存ブックと同じ1取引あたりの損益分布に従う」と仮定する。
**最も楽観的な仮定であり、ここで出る倍率は「これ未満では絶対に足りない」下限。**

【評価条件】
資金100,000円・期限3ヶ月・破綻ライン10%・最小ロット制約あり・
移動ブロック L=20（頻度を上げると3ヶ月の取引数が増えるのでブロックは短めにする）
kはIS窓で選択（OOSを見ない）。IS窓の結果も併記。
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
TARGET_P = 0.70
DEADLINE = 3.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
RUIN = 0.10
L = 20
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0]
F_GRID = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0, 16.0]
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
        hit = alive & (eq >= CAPITAL * 2.0)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state


def main():
    print("=" * 112)
    print("V059：新要件で70%に届くには取引機会が何倍必要か（資金10万円・期限3ヶ月）")
    print("=" * 112)
    print("⚠️ 前提：増えた取引機会も既存ブックと同じ損益分布に従うと仮定する。")
    print("   **最も楽観的な仮定であり、ここで出る倍率は「これ未満では絶対に足りない」下限。**\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        rate = len(pr) / MONTHS[w]
        sd = float(pr.std(ddof=1))
        sh = float(pr.mean()) / sd
        data[w] = (pr, vo, rate, sh)
        print(f"  {w}窓: 月{rate:.1f}件 / 1取引あたりシャープ {sh:.4f}")
    print()

    print(f"{'頻度倍率':>9}{'3ヶ月の取引数':>14}{'3ヶ月ｼｬｰﾌﾟ(OOS)':>17}"
          f"{'天井(破綻無視)':>16}│{'IS選択k':>9}{'IS到達':>9}"
          f"│{'OOS到達':>9}{'OOS破綻':>9}{'R3(70%)':>9}")
    hit_f = None
    for f in F_GRID:
        out = {}
        for w in ("IS", "OOS"):
            pr, vo, rate, sh = data[w]
            H = int(round(rate * f * DEADLINE))
            best, bp, rec = None, -1.0, {}
            for k in K_GRID:
                hh, rr = [], []
                for sd_ in SEEDS:
                    pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=240000 + sd_)
                    st = run(pp, vv, k)
                    hh.append(float((st == 1).mean()))
                    rr.append(float((st == 2).mean()))
                rec[k] = (float(np.mean(hh)), float(np.mean(rr)))
                if w == "IS" and rec[k][0] > bp:
                    best, bp = k, rec[k][0]
            out[w] = (rec, best)
        k_sel = out["IS"][1]
        ih, _ = out["IS"][0][k_sel]
        oh, orr = out["OOS"][0][k_sel]
        pr_o, _, rate_o, sh_o = data["OOS"]
        H_o = int(round(rate_o * f * DEADLINE))
        s3 = sh_o * math.sqrt(H_o)
        ceil = 0.5 * (1 + math.erf(s3 / math.sqrt(2)))
        if hit_f is None and oh >= TARGET_P:
            hit_f = f
        print(f"{f:>8.1f}x{H_o:>14}{s3:>17.3f}{100*ceil:>15.1f}%"
              f"│{k_sel:>9}{100*ih:>8.1f}%"
              f"│{100*oh:>8.1f}%{100*orr:>8.1f}%"
              f"{'✅' if oh >= TARGET_P else '❌':>9}")
        if hit_f is not None:
            break

    print()
    if hit_f is None:
        print(f"  → 頻度を{F_GRID[-1]:g}倍にしてもOOSで70%に届かない")
    else:
        rate_o = data["OOS"][2]
        print(f"  → **70%到達に必要な頻度倍率は {hit_f:g}倍**"
              f"（月{rate_o:.1f}件 → 月{rate_o*hit_f:.0f}件）")
        print(f"     現在15枠なので、**同等の質の枠が{15*hit_f:.0f}枠相当**必要")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・増えた取引の質が既存と同等という前提。実際には相関が上がり質は下がる")
    print("  ・頻度を上げるとブロック長L=20が相対的に短くなり、系列依存の保持が弱まる")
    print("  ・V053でCodexが指摘した評価器の未解決点をすべて引き継ぐ")
    print("\n完了。")


if __name__ == "__main__":
    main()
