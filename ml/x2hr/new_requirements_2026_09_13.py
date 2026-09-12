"""V055：**新要件**での検証——資金10万円・期限3ヶ月・目標70%。

【ユーザーによる要件変更（2026-09-13）】

| 項目 | 旧 | **新** |
|---|---|---|
| R1 初期資金 | 30,000円 | **100,000円** |
| R3 到達確率の目標 | 85% | **70%** |
| R4 期限 | 理想1ヶ月・上限2ヶ月 | **3ヶ月** |

R7（破綻ライン10%）は変更指示が無いので維持し、感応度も併せて出す。

【資金を10万円にすると何が変わるか——2つの効果が逆向きに働く】

**効果1：相対リスクが1/3.33になる（不利）**
dealログの損益は**円建ての絶対額**である。資金が3万円→10万円になると、
同じ取引の損益が資金に占める割合は 1/3.33 になる。
2倍にするのに必要な利益も 3万円→10万円と3.33倍になる。
**つまり同じ倍率kなら、10万円のほうが2倍までずっと遠い。**

**効果2：最小ロット床が効きにくくなる（有利）**
資金10万円で「3万円のk=1.0と同じ相対リスク」を取るには k≈3.33 が必要になる。
このとき希望ロットは 0.01×3.33＝0.033 となり、**最小ロット0.01の3倍以上**。
したがって**資金が1/3以下に減るまで床に当たらない。**
3万円のときは k<1 が一切実現しなかった（V046）が、この制約が大きく緩む。

**相対的な動きは (損益 × k / 資金) だけで決まるので、
「資金10万円・k」は「資金3万円・k/3.33」と数学的に同値である（床を除けば）。**
したがってkの探索範囲は旧測定の3.33倍に取る。

【評価条件】
- 最小ロット制約あり（V047）＋年ブロック再標本化あり（V045）＝V048の★両方
- 倍率kは**IS窓で選ぶ**（OOSを見ない）。**IS窓の結果も必ず併記する**
- 到達・破綻は**無条件の累積確率**で出す（V054の訂正を反映）
- 期限3ヶ月を主評価とし、1/2/3/6/12ヶ月も併記する

【限界（V053でCodexが指摘した未解決点をすべて引き継ぐ）】
- 入口時点でのロット固定を実装していない（決済時点で倍率を適用している）
- 丸め前の基準ロットではなく、すでに丸められた約定ロットに倍率を掛けている
- 含み損益・証拠金制約を考慮していない
- 暦時間ではなく取引数で期間を換算している
- 年ブロック6個・開始位置固定による階段状の歪み
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import realistic_sim as rs

CAPITAL = 100000.0          # 新R1
TARGET_P = 0.70             # 新R3
DEADLINE = 3.0              # 新R4（ヶ月）
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
RUIN_LEVELS = (0.10, 0.20, 0.50)
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0]
CHECKPOINTS = [1, 2, 3, 6, 12, 24]
MONTHS = cc.MONTHS
LONG_MONTHS = 240.0


def run(pp, vv, k, ruin_frac):
    """最小ロット制約つき。資金はCAPITAL（10万円）基準。"""
    n_paths, H = pp.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    floor_hits = 0
    cnt = 0
    for step in range(H):
        if not alive.any():
            break
        x = eq / CAPITAL
        v = vv[:, step]
        desired = v * k * x
        actual = np.maximum(MIN_LOT, np.floor(desired / STEP + 1e-9) * STEP)
        if step % 50 == 0:
            sub = alive & (desired < MIN_LOT)
            floor_hits += int(sub.sum()); cnt += int(alive.sum())
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= CAPITAL * 2.0)
        ruin = alive & (eq <= CAPITAL * ruin_frac)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
    return state, stop, (floor_hits / cnt if cnt else 0.0)


def main():
    print("=" * 116)
    print("V055：新要件での検証——資金10万円・期限3ヶ月・目標70%（2026-09-13）")
    print("=" * 116)
    print(f"R1 初期資金 = {CAPITAL:,.0f}円（旧30,000円）")
    print(f"R3 到達確率の目標 = {100*TARGET_P:.0f}%（旧85%）")
    print(f"R4 期限 = {DEADLINE:g}ヶ月（旧 理想1ヶ月・上限2ヶ月）")
    print("R7 破綻ライン = 10%（変更指示なし・20%/50%の感応度も併記）")
    print("\n条件：最小ロット制約あり(V047)＋年ブロック再標本化あり(V045)")
    print("      kはIS窓で選択（OOSを見ない）。IS窓の結果も併記。")
    print("      到達・破綻は**無条件の累積確率**（V054の訂正を反映）\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        data[w] = (tt, pr, vo, len(pr) / MONTHS[w], rs.year_blocks(tt, pr, vo))

    for ruin_frac in RUIN_LEVELS:
        print("=" * 116)
        print(f"【破綻ライン {100*ruin_frac:.0f}%】期限{DEADLINE:g}ヶ月での到達確率")
        print("=" * 116)
        print(f"{'k':>6}{'床に当たる率':>13}"
              f"{'IS到達':>9}{'IS破綻':>9}{'IS未決':>9}"
              f"│{'OOS到達':>9}{'OOS破綻':>9}{'OOS未決':>9}{'R3(70%)':>10}")
        rows = {}
        for k in K_GRID:
            out = {}
            for w in ("IS", "OOS"):
                tt, pr, vo, rate, yb = data[w]
                H = int(round(rate * LONG_MONTHS))
                sc = int(round(rate * DEADLINE))
                hh, rr, fl = [], [], []
                for sd in SEEDS:
                    pp, vv = rs.gen_year(yb, H, N_PATHS, seed=210000 + sd)
                    st, stp, f = run(pp, vv, k, ruin_frac)
                    hh.append(float(((st == 1) & (stp <= sc)).mean()))
                    rr.append(float(((st == 2) & (stp <= sc)).mean()))
                    fl.append(f)
                out[w] = (float(np.mean(hh)), float(np.mean(rr)), float(np.mean(fl)))
            rows[k] = out
            ih, ir, ifl = out["IS"]
            oh, orr, _ = out["OOS"]
            print(f"{k:>6}{100*ifl:>12.1f}%"
                  f"{100*ih:>8.1f}%{100*ir:>8.1f}%{100*(1-ih-ir):>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*(1-oh-orr):>8.1f}%"
                  f"{'✅' if oh >= TARGET_P else '❌':>10}")
        # IS選択
        k_sel = max(K_GRID, key=lambda k: rows[k]["IS"][0])
        oh, orr, _ = rows[k_sel]["OOS"]
        ih, ir, _ = rows[k_sel]["IS"]
        print(f"\n  → **IS選択 k={k_sel}** ： IS到達 {100*ih:.1f}% / "
              f"OOS到達 {100*oh:.1f}% / OOS破綻 {100*orr:.1f}%  "
              f"→ R3(70%) {'✅ 達成' if oh >= TARGET_P else '❌ 未達'}")
        best_oos = max(K_GRID, key=lambda k: rows[k]["OOS"][0])
        print(f"    （参考・先読み）OOS最良は k={best_oos} で "
              f"{100*rows[best_oos]['OOS'][0]:.1f}%")
        print()

    # --- 期限別の累積確率（破綻ライン10%・IS選択k） ---
    print("=" * 116)
    print("【期限別の無条件累積確率】破綻ライン10%")
    print("=" * 116)
    rows10 = {}
    for k in K_GRID:
        out = {}
        for w in ("IS", "OOS"):
            tt, pr, vo, rate, yb = data[w]
            H = int(round(rate * LONG_MONTHS))
            acc_h = np.zeros(len(CHECKPOINTS))
            acc_r = np.zeros(len(CHECKPOINTS))
            for sd in SEEDS:
                pp, vv = rs.gen_year(yb, H, N_PATHS, seed=210000 + sd)
                st, stp, _ = run(pp, vv, k, 0.10)
                for i, c in enumerate(CHECKPOINTS):
                    s_c = int(round(rate * c))
                    acc_h[i] += float(((st == 1) & (stp <= s_c)).mean())
                    acc_r[i] += float(((st == 2) & (stp <= s_c)).mean())
            out[w] = (acc_h / len(SEEDS), acc_r / len(SEEDS))
        rows10[k] = out
    k_sel = max(K_GRID, key=lambda k: rows10[k]["IS"][0][CHECKPOINTS.index(3)])
    print(f"IS窓で期限3ヶ月の到達率が最大になる k = {k_sel}\n")
    for w in ("IS", "OOS"):
        print(f"--- {w}窓 ---")
        hdr = f"{'k':>6}{'区分':>8}"
        for c in CHECKPOINTS:
            hdr += f"{f'{c}ヶ月':>9}"
        print(hdr)
        for k in K_GRID:
            h, r = rows10[k][w]
            mark = " ←IS選択" if k == k_sel else ""
            line = f"{k:>6}{'到達':>8}"
            for v in h:
                line += f"{100*v:>8.1f}%"
            print(line + mark)
            line = f"{'':>6}{'破綻':>8}"
            for v in r:
                line += f"{100*v:>8.1f}%"
            print(line)
        print()

    print("=" * 116)
    print("【限界】V053でCodexが指摘した未解決点をすべて引き継ぐ")
    print("=" * 116)
    print("  ・入口時点でのロット固定を実装していない（決済時点で倍率を適用）")
    print("  ・丸め前の基準ロットではなく、すでに丸められた約定ロットに倍率を掛けている")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・暦時間ではなく取引数で期間を換算している")
    print("  ・年ブロック6個・開始位置固定による階段状の歪み")
    print("\n完了。")


if __name__ == "__main__":
    main()
