"""V083：**期限を確定させたうえでの期限意識サイジング**（簡易検証・2026-09-13）。

【V082の設計ミス（自己発見）】
V082は**18ヶ月の経路**を1本走らせ、その途中で3・6・12ヶ月の累積到達を読んでいた。
ところが期限意識サイジングの `τ` は**18ヶ月の残り時間**として計算していたため、
方策は「18ヶ月かけて届けばよい」と判断し、**序盤はほとんど張らない。**
結果、3ヶ月到達0.0%・6ヶ月到達3.5%まで崩れた。

**これは方策の失敗ではなく、評価系の設計ミスである。**
期限を意識する方策は、**どの期限に賭けるかを先に決めていなければ意味がない。**

【本スクリプトの設計】
期限 D（3・6・12ヶ月）ごとに——
- **経路を D ヶ月ちょうどで打ち切る**
- **τ = (残り時間)/D** として方策を計算する
- 起点は `起点 + D ≤ 2020-01-01`（経路全体が弱局面に収まる）
- **比例方策（基準）も同じ起点・同じ期限で測る**（公平な比較）
- **kは各期限・各方策ごとにIS窓で選び直す（OOSを見ない）**

**V073の36.0%とは起点集合が違うので、数字は直接比較できない。**
**比較すべきは、同じ表の中の「比例方策」と「期限意識」である。**

【限界】
- V080の u* は拡散近似の産物。実際の損益は裾が厚く系列相関がある
- 起点が重なるため独立ではない（期限が短いほど起点は増えるが重なりも増える）
- 含み損益・証拠金制約を考慮していない
- τ→0 で `1/√τ` が発散するので上限で頭打ちにする（上限も報告する）
- **段階2の簡易検証である。採用するならMT5バックテストが必要**
"""
from __future__ import annotations

import bisect
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_aware_sizing as das
import target_policy_gap as tpg

CAPITAL = co.CAPITAL
MIN_LOT = co.MIN_LOT
STEP = co.STEP
RUIN = co.RUIN
MULT = 2.0
QUIET_END = tpg.QUIET_END
ORIGIN_STEP_DAYS = 7
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
DEADLINES = [3, 6, 12]
CAPS = [2.0, 3.0, 5.0]


def simulate(rec, ti, t0, t_end, k, pol, cap):
    i0 = bisect.bisect_left(ti, t0)
    i1 = bisect.bisect_left(ti, t_end)
    span = float(t_end - t0)
    eq = CAPITAL
    pend, pi, ei = [], 0, i0
    while ei < i1 or pi < len(pend):
        t_ev = rec[ei][0] if ei < i1 else None
        if pi < len(pend):
            pend[pi:] = sorted(pend[pi:])
            t_pd = pend[pi][0]
        else:
            t_pd = None
        if t_pd is not None and (t_ev is None or t_pd <= t_ev):
            t, m, profit = pend[pi]
            pi += 1
            if t > t_end:
                continue
            eq += profit * m
            if eq >= CAPITAL * MULT:
                return True, False
            if eq <= CAPITAL * RUIN:
                return False, True
        else:
            t_in, t_out, profit, vol = rec[ei]
            ei += 1
            ratio = eq / CAPITAL
            mk = k * ratio
            if pol is not None:
                tau = max(t_end - t_in, 0) / span
                mk *= pol.mult(math.log(max(ratio, 1e-6)), tau, cap)
            actual = max(MIN_LOT, math.floor(vol * mk / STEP + 1e-9) * STEP)
            pend.append((t_out, actual / vol, profit))
    return False, False


def evaluate(rec, k, pol, cap, start, end_cap, months):
    """期限 months ちょうどの経路で、到達率と破綻率を返す。"""
    ti = [x[0] for x in rec]
    hit = ruin = n = 0
    d = start
    while cod.add_months(d, months) <= end_cap:
        t_end = cod.add_months(d, months)
        h, r = simulate(rec, ti, int(d.timestamp()), int(t_end.timestamp()),
                        k, pol, cap)
        hit += h
        ruin += r
        n += 1
        d += timedelta(days=ORIGIN_STEP_DAYS)
    return (hit / n if n else 0.0), (ruin / n if n else 0.0), n


def main():
    print("=" * 116)
    print("V083：期限を確定させたうえでの期限意識サイジング（簡易検証）")
    print("=" * 116)
    print("★ V082は18ヶ月の経路で3/6ヶ月の到達を読んでいたため、方策が序盤に張らず崩れた。")
    print("  **期限を意識する方策は、どの期限に賭けるかを先に決めていなければ意味がない。**")
    print("  本スクリプトは期限ごとに経路を区切り、τ をその期限に対する残り時間として測る。\n")
    print("  起点は「起点 + 期限 ≤ 2020-01-01」（経路全体が弱局面に収まる）")
    print("  資金10万円・破綻ライン10%・最小ロット制約あり・**倍率2倍固定**")
    print("  **kは各期限・各方策ごとにIS窓で選び直す（OOSを見ない）**")
    print("  ※ 起点集合がV073と違うので、V073の36.0%とは直接比較できない。")
    print("    **比較すべきは同じ表の中の『比例方策』と『期限意識』。**\n")

    print("  方策表を作成中（HJB）...", flush=True)
    pol = das.Policy()
    print(f"  基準 u*(0, τ=1) = {pol.u_ref:.3f}\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    for D in DEADLINES:
        tgt = 0.65 if D in (3, 6) else 0.90
        print("=" * 116)
        print(f"【期限 {D}ヶ月】判定水準 {100*tgt:.0f}%"
              f"（方針A＝3〜6ヶ月65% / 方針B＝12ヶ月90%）")
        print("=" * 116)
        print(f"{'方策':<28}{'IS選択k':>9}{'IS起点':>8}{'IS到達':>9}{'IS破綻':>9}"
              f"│{'OOS起点':>9}{'**OOS到達**':>13}{'OOS破綻':>10}{'判定':>7}")
        rows = [("比例方策（基準）", None, 0.0)]
        rows += [(f"期限意識（上限{c:.0f}倍）", pol, c) for c in CAPS]
        for label, p, cap in rows:
            # --- R2ルール：IS最大から1pt以内のkの中央値を採る ---
            # （単純なargmaxだと、IS到達が飽和したときにタイで最小kが選ばれ、
            #   比較が不公平になる。V041・V062で確認済みのk選択の不安定さ）
            hs = [evaluate(data["IS"], k, p, cap, a_is, b_is, D)[0]
                  for k in K_GRID]
            top = max(hs)
            near = [k for k, h in zip(K_GRID, hs) if h >= top - 0.01]
            best = float(np.median(near))
            if best not in K_GRID:
                best = min(near, key=lambda k: abs(k - best))
            ih, ir, inn = evaluate(data["IS"], best, p, cap, a_is, b_is, D)
            oh, orr, onn = evaluate(data["OOS"], best, p, cap,
                                    a_oos, QUIET_END, D)
            ok = oh >= tgt
            print(f"{label:<28}{best:>9.0f}{inn:>8}{100*ih:>8.1f}%{100*ir:>8.1f}%"
                  f"│{onn:>9}{100*oh:>12.1f}%{100*orr:>9.1f}%"
                  f"{'OK' if ok else 'NG':>7}")
        print()

    # ---------- 同一kでの対比（k選択の効果を分離する） ----------
    print("=" * 116)
    print("【同一kでの対比】**k選択の効果を分離する**（V062の教訓）")
    print("=" * 116)
    print("  上の表はkをISで選び直しているため、方策の効果とk選択の効果が混ざっている。")
    print("  ここでは**同じkで比例方策と期限意識を並べる**。OOSの数字のみ。")
    print(f"{'期限':>5}{'k':>5}│{'比例 到達':>11}{'比例 破綻':>11}"
          f"│{'期限意識 到達':>15}{'期限意識 破綻':>15}│{'**差**':>10}")
    for D in DEADLINES:
        for k in (2.0, 4.0, 8.0, 16.0):
            bh, br, _ = evaluate(data["OOS"], k, None, 0.0, a_oos, QUIET_END, D)
            ph, pr, _ = evaluate(data["OOS"], k, pol, 3.0, a_oos, QUIET_END, D)
            print(f"{D:>4}月{k:>5.0f}│{100*bh:>10.1f}%{100*br:>10.1f}%"
                  f"│{100*ph:>14.1f}%{100*pr:>14.1f}%│{100*(ph-bh):>9.1f}pt")
        print()

    print("=" * 116)
    print("【限界】")
    print("=" * 116)
    print("  ・V080の u* は拡散近似の産物。実際の損益は裾が厚く系列相関がある")
    print("  ・起点が重なるため独立ではない（期限が短いほど起点は増えるが重なりも増える）")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・**段階2の簡易検証である。採用するならMT5バックテストが必要**")
    print("\n完了。")


if __name__ == "__main__":
    main()
