"""V074：**倍率2倍固定**での2つの方針に、何がどれだけ足りないか。

【ユーザー指示（2026-09-13）】
> このX2_HIGH_RISKはハイリスクハイリターンを目指して作っているため**倍率は2倍に固定**。
> 目標を達成するために倍率を下げるのは受け入れられない。
> 期間については相談の余地がある。**方針は2種類のみ**：
> - **方針A：3〜6ヶ月までで達成率65%以上**
> - **方針B：12ヶ月までかかるが達成率90%以上**（その場合の破綻率は限りなく低く）

**目標倍率を下げる案（1.2倍・1.3倍）はすべて破棄する。**

【現状（V073・保守評価＝弱局面のみ86起点・k=8.0）】

| 期限 | 到達 | 破綻 | 方針A(65%) | 方針B(90%) |
|---|---:|---:|---|---|
| 3ヶ月 | 23.3% | — | ❌ −41.7pt | — |
| 6ヶ月 | 36.0% | — | ❌ **−29.0pt** | — |
| 12ヶ月 | 41.9% | 54.7%(18月) | — | ❌ **−48.1pt** |

**どちらも大きく不足。** 本スクリプトは「**何がどれだけ足りないか**」を確定させる。

【V056の枠組み】
到達確率の天井は `Φ(期限シャープ)`、期限シャープ ＝ **1取引シャープ × √(期限内の取引数)**。
上げる手段は2つだけ——**①1取引あたりの質** ②**取引数**（√で効く）。

【本スクリプトの測定】
弱局面の実履歴評価（起点＋期限 ≤ 2020-01-01）の上で、
**取引機会を f 倍にした場合**の到達率を測る。

追加分は**同じ窓の実取引から復元抽出**し、元の取引と同じ時刻に置く。
**追加枠どうしの相関を無視しているので、これは楽観的な見積もりである。**

f ごとに、**方針A（6ヶ月65%）・方針B（12ヶ月90%）を満たすか**を判定する。
kも各fで選び直す（弱局面のISに相当する窓で選ぶ）。

【限界】
- 追加枠の相関を無視（実際は相関があり、分散低減効果は小さくなる＝**さらに不利**）
- 追加枠が既存と同じ1取引あたりの質を持つ前提（V066で42%まで落ちる可能性を確認済み）
- 弱局面の起点は86個。起点が重なるため独立ではない
- 測っているのは「含み損益・証拠金制約を無視した、確定損益残高の期限内到達割合」
"""
from __future__ import annotations

import bisect
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod

CAPITAL = co.CAPITAL
MIN_LOT = co.MIN_LOT
STEP = co.STEP
RUIN = co.RUIN
MULT = 2.0                      # ★ 倍率は2倍固定（ユーザー指示）
QUIET_END = datetime(2020, 1, 1, tzinfo=timezone.utc)
ORIGIN_STEP_DAYS = 7
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
F_GRID = [1, 2, 3, 4, 6, 8, 12]
CHECK = [3, 6, 12]
POLICY_A = (6, 0.65)            # 6ヶ月で65%
POLICY_B = (12, 0.90)           # 12ヶ月で90%
SEEDS = (11, 22, 33)


def expand(rec, f, seed):
    """取引機会を f 倍にする。追加分は同じ窓の実取引から復元抽出し、
    元の取引と同じ入口・決済時刻に置く。"""
    if f <= 1:
        return rec
    rng = np.random.default_rng(seed)
    n = len(rec)
    out = list(rec)
    for _ in range(f - 1):
        idx = rng.integers(0, n, size=n)
        for i, j in enumerate(idx):
            ti, to, _, _ = rec[i]          # 時刻は元の取引のもの
            _, _, profit, vol = rec[j]     # 損益とロットは抽選した取引のもの
            out.append((ti, to, profit, vol))
    out.sort()
    return out


def evaluate_quiet(rec, k, months_list, start, end_cap, max_months=18):
    """弱局面の起点だけで、各期限の累積到達率を返す。"""
    ti = [x[0] for x in rec]
    res = []
    d = start
    while cod.add_months(d, max_months) <= end_cap:
        t_end = cod.add_months(d, max_months)
        hit, ruin = cod.first_reach(rec, ti, int(d.timestamp()),
                                    int(t_end.timestamp()), k, MULT)
        res.append((d, hit, ruin))
        d += timedelta(days=ORIGIN_STEP_DAYS)
    out = {}
    for m in months_list:
        h, r, n = cod.cumulative(res, m)
        out[m] = (h, r, n)
    return out


def main():
    print("=" * 108)
    print("V074：倍率2倍固定での2つの方針に、何がどれだけ足りないか")
    print("=" * 108)
    print("★ ユーザー指示：**倍率は2倍に固定**。目標倍率を下げる案は破棄。")
    print(f"  方針A：{POLICY_A[0]}ヶ月までで達成率{100*POLICY_A[1]:.0f}%以上")
    print(f"  方針B：{POLICY_B[0]}ヶ月までで達成率{100*POLICY_B[1]:.0f}%以上（破綻率は限りなく低く）\n")
    print("評価は**弱局面の実履歴**（起点＋18暦月 ≤ 2020-01-01・金が静かな時期のみ）。")
    print("取引機会を f 倍にした場合を測る。追加分は同じ窓の実取引から復元抽出。")
    print("**追加枠の相関を無視しており、楽観的な見積もりである。**\n")

    data = {w: co.load_events(w) for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    print(f"{'f':>4}{'取引数':>9}│{'IS選択k':>9}"
          f"{'IS 3月':>9}{'IS 6月':>9}{'IS 12月':>9}"
          f"│{'OOS 3月':>9}{'OOS 6月':>9}{'OOS 12月':>10}"
          f"{'12月破綻':>10}│{'方針A':>7}{'方針B':>7}")
    hitA = hitB = None
    for f in F_GRID:
        # --- 各fでkをIS窓から選ぶ（6ヶ月基準・共通起点） ---
        best, bp = None, -1.0
        for k in K_GRID:
            vals = []
            for sd in SEEDS:
                rec_is = expand(data["IS"][0], f, 1000 + sd)
                o = evaluate_quiet(rec_is, k, [6], a_is, b_is)
                vals.append(o[6][0])
            m = float(np.mean(vals))
            if m > bp:
                best, bp = k, m
        k_sel = best
        # --- IS/OOS を測る ---
        res = {}
        for w, (st, cap) in (("IS", (a_is, b_is)), ("OOS", (a_oos, QUIET_END))):
            acc = {m: [] for m in CHECK}
            ruin12 = []
            for sd in SEEDS:
                rec_w = expand(data[w][0], f, 2000 + sd)
                o = evaluate_quiet(rec_w, k_sel, CHECK, st, cap)
                for m in CHECK:
                    acc[m].append(o[m][0])
                ruin12.append(o[12][1])
            res[w] = ({m: float(np.mean(acc[m])) for m in CHECK},
                      float(np.mean(ruin12)))
        okA = res["OOS"][0][POLICY_A[0]] >= POLICY_A[1]
        okB = res["OOS"][0][POLICY_B[0]] >= POLICY_B[1]
        if okA and hitA is None:
            hitA = f
        if okB and hitB is None:
            hitB = f
        n_tr = len(data["OOS"][0]) * f
        print(f"{f:>3}x{n_tr:>9}│{k_sel:>9}"
              f"{100*res['IS'][0][3]:>8.1f}%{100*res['IS'][0][6]:>8.1f}%"
              f"{100*res['IS'][0][12]:>8.1f}%"
              f"│{100*res['OOS'][0][3]:>8.1f}%{100*res['OOS'][0][6]:>8.1f}%"
              f"{100*res['OOS'][0][12]:>9.1f}%{100*res['OOS'][1]:>9.1f}%"
              f"│{'✅' if okA else '❌':>7}{'✅' if okB else '❌':>7}")

    print()
    if hitA is None:
        print(f"  → **方針A（6ヶ月65%）は頻度{F_GRID[-1]}倍でも達成できない**")
    else:
        print(f"  → **方針A（6ヶ月65%）に必要な頻度倍率は {hitA}倍**")
    if hitB is None:
        print(f"  → **方針B（12ヶ月90%）は頻度{F_GRID[-1]}倍でも達成できない**")
    else:
        print(f"  → **方針B（12ヶ月90%）に必要な頻度倍率は {hitB}倍**")

    print("\n" + "=" * 108)
    print("【限界】")
    print("=" * 108)
    print("  ・追加枠の相関を無視（実際は相関があり分散低減効果は小さい＝さらに不利）")
    print("  ・追加枠が既存と同じ1取引あたりの質を持つ前提")
    print("    （V066でSCA-FX相当なら**ブック平均の42%**まで落ちることを確認済み）")
    print("  ・弱局面の起点は86個。起点が重なるため独立ではない")
    print("  ・測っているのは『含み損益・証拠金制約を無視した、確定損益残高の到達割合』")
    print("\n完了。")


if __name__ == "__main__":
    main()
