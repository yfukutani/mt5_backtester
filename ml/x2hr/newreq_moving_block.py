"""V057：新要件（資金10万円・期限3ヶ月・目標70%）を**移動ブロック**で測り直す。

【V055が無効だった理由】
V055は年ブロック（暦年ごと・6個）を復元抽出して使った。ところが**3ヶ月＝約100取引**は
1つの年ブロック（200〜450取引）に収まってしまうため、**パスは実質「6年のうちどれを
引いたか」だけで決まっていた。** 到達率がすべて 1/6 の倍数（16.7 / 33.3 / 50.0 / 66.7 /
83.3 / 100%）になっていたのがその証拠である。

CodexはV053の査読でこれを予告していた。
> 開始位置がブロックの先頭に固定され、任意の時点から始めるモデルではない。
> **第一ブロックだけで決着するパスが多ければ、年頭から始めるという設定が
> 先着確率に強く効く**可能性があります。

**まさにそのとおりだった。V055の数値は使えない。**

【本スクリプトの設計】
**移動ブロック・ブートストラップ**（任意の位置から連続L取引を取る）に変える。
ブロック長Lを3通り並べて、局面の持続をどこまで保持するかの感応度も同時に見る。

| L | 保持する構造 | 3ヶ月パスの作り方 |
|---:|---|---|
| 20 | 約半月 | 5ブロックの連結 |
| 33 | 約1ヶ月 | 3ブロックの連結 |
| **100** | **約3ヶ月** | **実際の履歴の連続した3ヶ月をそのまま使う** |

**L=100は「過去の任意の3ヶ月を実際に走ったらどうなったか」に最も近い。**
起点は約1,800通りあるので、V055のような退化は起きない。

【評価条件】
- 資金100,000円・目標2倍・破綻ライン10%（20%/50%の感応度も）
- 最小ロット制約あり（V047の Clamp）
- 倍率kは**IS窓で選ぶ**（OOSを見ない）。**IS窓の結果も必ず併記**
- 到達・破綻は**無条件の割合**（V054の訂正を反映）

【限界（V053でCodexが指摘した未解決点を引き継ぐ）】
- 入口時点でのロット固定を実装していない
- 丸め前の基準ロットではなく約定ロットに倍率を掛けている
- 含み損益・証拠金制約を考慮していない
- 暦時間ではなく取引数で期間を換算している
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import realistic_sim as rs

CAPITAL = 100000.0
TARGET_P = 0.70
DEADLINE = 3.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
RUIN_LEVELS = (0.10, 0.20, 0.50)
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0]
L_GRID = [20, 33, 100]
MONTHS = cc.MONTHS


def gen_moving(pr, vo, H, n_paths, L, seed):
    """移動ブロック・ブートストラップ（任意の位置から連続L取引）。"""
    rng = np.random.default_rng(seed)
    n = len(pr)
    nb = H // L + 2
    starts = rng.integers(0, n, size=(n_paths, nb))
    off = np.arange(L)
    idx = (starts[:, :, None] + off[None, None, :]) % n
    idx = idx.reshape(n_paths, -1)[:, :H]
    return pr[idx], vo[idx]


def run(pp, vv, k, ruin_frac):
    n_paths, H = pp.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    floor = 0
    cnt = 0
    for step in range(H):
        if not alive.any():
            break
        x = eq / CAPITAL
        v = vv[:, step]
        desired = v * k * x
        actual = np.maximum(MIN_LOT, np.floor(desired / STEP + 1e-9) * STEP)
        if step % 10 == 0:
            floor += int((alive & (desired < MIN_LOT)).sum())
            cnt += int(alive.sum())
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= CAPITAL * 2.0)
        ruin = alive & (eq <= CAPITAL * ruin_frac)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state, (floor / cnt if cnt else 0.0)


def main():
    print("=" * 118)
    print("V057：新要件を**移動ブロック**で測り直す（資金10万円・期限3ヶ月・目標70%）")
    print("=" * 118)
    print("⚠️ V055（年ブロック）は3ヶ月では実質6シナリオしか生成できておらず無効だった。")
    print("   移動ブロック（任意の位置から連続L取引）に変更し、Lの感応度も見る。\n")

    data = {}
    for w in ("IS", "OOS"):
        tt, pr, vo = rs.build(w)
        rate = len(pr) / MONTHS[w]
        data[w] = (pr, vo, rate, int(round(rate * DEADLINE)))
        print(f"  {w}窓: {len(pr)}取引 / 月{rate:.1f}件 / "
              f"3ヶ月＝{int(round(rate*DEADLINE))}取引")
    print()

    for ruin_frac in RUIN_LEVELS:
        print("=" * 118)
        print(f"【破綻ライン {100*ruin_frac:.0f}%】期限{DEADLINE:g}ヶ月・資金{CAPITAL:,.0f}円")
        print("=" * 118)
        for L in L_GRID:
            print(f"\n--- ブロック長 L={L}"
                  f"（{'約半月' if L==20 else '約1ヶ月' if L==33 else '約3ヶ月＝実履歴の連続'}）---")
            print(f"{'k':>6}{'床率':>8}"
                  f"{'IS到達':>9}{'IS破綻':>9}{'IS未決':>9}"
                  f"│{'OOS到達':>9}{'OOS破綻':>9}{'OOS未決':>9}{'R3(70%)':>9}")
            rows = {}
            for k in K_GRID:
                out = {}
                for w in ("IS", "OOS"):
                    pr, vo, rate, H = data[w]
                    hh, rr, ff = [], [], []
                    for sd in SEEDS:
                        pp, vv = gen_moving(pr, vo, H, N_PATHS, L, seed=220000 + sd)
                        st, f = run(pp, vv, k, ruin_frac)
                        hh.append(float((st == 1).mean()))
                        rr.append(float((st == 2).mean()))
                        ff.append(f)
                    out[w] = (float(np.mean(hh)), float(np.mean(rr)), float(np.mean(ff)))
                rows[k] = out
                ih, ir, ifl = out["IS"]
                oh, orr, _ = out["OOS"]
                print(f"{k:>6}{100*ifl:>7.1f}%"
                      f"{100*ih:>8.1f}%{100*ir:>8.1f}%{100*(1-ih-ir):>8.1f}%"
                      f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*(1-oh-orr):>8.1f}%"
                      f"{'✅' if oh >= TARGET_P else '❌':>9}")
            k_sel = max(K_GRID, key=lambda k: rows[k]["IS"][0])
            ih, ir, _ = rows[k_sel]["IS"]
            oh, orr, _ = rows[k_sel]["OOS"]
            k_oos = max(K_GRID, key=lambda k: rows[k]["OOS"][0])
            print(f"  → IS選択 k={k_sel}：IS {100*ih:.1f}% / OOS {100*oh:.1f}%"
                  f"（破綻{100*orr:.1f}%）→ R3(70%) "
                  f"{'✅ 達成' if oh >= TARGET_P else '❌ 未達'}")
            print(f"    （参考・先読み）OOS最良は k={k_oos} で "
                  f"{100*rows[k_oos]['OOS'][0]:.1f}%"
                  f"（破綻{100*rows[k_oos]['OOS'][1]:.1f}%）")
        print()

    print("=" * 118)
    print("【限界】")
    print("=" * 118)
    print("  ・入口時点でのロット固定を実装していない（決済時点で倍率を適用）")
    print("  ・丸め前の基準ロットではなく約定ロットに倍率を掛けている")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・暦時間ではなく取引数で期間を換算している")
    print("  ・L=100でも起点は同一履歴からの重複サンプルであり、独立な3ヶ月ではない")
    print("\n完了。")


if __name__ == "__main__":
    main()
