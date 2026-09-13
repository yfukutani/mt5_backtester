"""V084：**期限意識サイジングの頑健性**（簡易検証・2026-09-13）。

【V083で出た結果】同一kのOOS対比で、全セルが改善した。

| 期限 | k | 比例 | 期限意識 | 差 |
|---:|---:|---:|---:|---:|
| 6月 | 4 | 13.8% | **52.2%** | **+38.4pt** |
| 12月 | 4 | 17.0% | **62.5%** | **+45.5pt** |

**比例方策は k をどう選んでも 6月40.6% / 12月40.2% 止まり。**
**「実効的にkを上げただけ」では説明できない。**

【しかし疑うべきこと】
1. **循環**：方策の形を決める H=0.48 は、**この同じ弱局面OOSから測った値**である
2. **上限（クリップ）の選択**：2/3/5倍で結果が大きく変わる（6月 18.8% / 52.2% / 55.8%）
3. **起点の重なり**：6ヶ月期限で138起点（7日刻み）だが独立ではない
4. **単純化の余地**：x に依存しない単純な代理方策で同じ効果が出るなら、
   **MQL5の実装がずっと簡単になる**

【本スクリプトで確認すること】
- **A. H感度**：H を 0.3 / 0.48 / 0.7 / 1.0 / 1.5 に変えても同じ改善が出るか
- **B. 完全窓外化**：方策の H と 上限の両方を **IS窓だけ**で決めて OOS で評価する
- **C. 非重複起点**：起点を重ならない集合に限って測る
- **D. 単純代理方策**：`倍率 = min(cap, 1/√τ)`（**x に依存しない**）で同じ効果が出るか

【限界】
- これらはすべて**段階2の簡易検証**であり、採用の根拠にはしない
- 非重複起点にすると件数が減り、区間が広くなる
- 含み損益・証拠金制約を考慮していない
"""
from __future__ import annotations

import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_aware_sizing as das
import deadline_committed as dc
import target_policy_gap as tpg

QUIET_END = tpg.QUIET_END
K_SHOW = [2.0, 4.0, 8.0]
DEADLINES = [6, 12]


class Simple:
    """x に依存しない代理方策：倍率 = min(cap, 1/√τ)。"""

    def mult(self, x, tau, cap):
        tau = min(max(tau, 1e-4), 1.0)
        return min(1.0 / math.sqrt(tau), cap)


def evaluate_step(rec, k, pol, cap, start, end_cap, months, step_days):
    ti = [x[0] for x in rec]
    hit = ruin = n = 0
    d = start
    while cod.add_months(d, months) <= end_cap:
        t_end = cod.add_months(d, months)
        h, r = dc.simulate(rec, ti, int(d.timestamp()), int(t_end.timestamp()),
                           k, pol, cap)
        hit += h
        ruin += r
        n += 1
        d += timedelta(days=step_days)
    return (hit / n if n else 0.0), (ruin / n if n else 0.0), n


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def main():
    print("=" * 112)
    print("V084：期限意識サイジングの頑健性（簡易検証）")
    print("=" * 112)
    print("★ V083の +38〜45pt が本物か。循環・上限選択・起点の重なりを疑う。\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    # ---------- A. H感度 ----------
    print("=" * 112)
    print("【A. 方策を決める H への感度】H=0.48 は弱局面OOSから測った値なので循環の疑いがある")
    print("=" * 112)
    print(f"{'期限':>5}{'k':>4}{'比例':>9}" +
          "".join(f"{f'H={h}':>10}" for h in (0.30, 0.48, 0.70, 1.00, 1.50)))
    pols = {}
    for h in (0.30, 0.48, 0.70, 1.00, 1.50):
        pols[h] = das.Policy(H=h)
    for D in DEADLINES:
        for k in K_SHOW:
            bh, _, _ = evaluate_step(data["OOS"], k, None, 0.0,
                                     a_oos, QUIET_END, D, 7)
            cells = ""
            for h in (0.30, 0.48, 0.70, 1.00, 1.50):
                ph, _, _ = evaluate_step(data["OOS"], k, pols[h], 3.0,
                                         a_oos, QUIET_END, D, 7)
                cells += f"{100*ph:>9.1f}%"
            print(f"{D:>4}月{k:>4.0f}{100*bh:>8.1f}%{cells}")
    print("\n  → Hを0.30〜1.50まで変えても同じ水準なら、**循環の疑いは薄い**")

    # ---------- B. 完全窓外化 ----------
    print("\n" + "=" * 112)
    print("【B. 完全窓外化】H も 上限も **IS窓だけ**で決めて OOS で評価する")
    print("=" * 112)
    # IS窓の1取引シャープから H を作る
    prof_is = np.array([x[2] for x in data["IS"]], dtype=float)
    s_is = float(prof_is.mean() / prof_is.std(ddof=1))
    per_is = len(data["IS"]) / 60.0
    print(f"  IS窓：1取引シャープ {s_is:.4f}・月あたり {per_is:.1f}取引")
    for D in DEADLINES:
        h_is = s_is * math.sqrt(per_is * D)
        pol_is = das.Policy(H=round(h_is, 2))
        # 上限もISで選ぶ
        best_cap, bp = None, -1.0
        for cap in (2.0, 3.0, 5.0, 8.0):
            ih, _, _ = evaluate_step(data["IS"], 4.0, pol_is, cap,
                                     a_is, b_is, D, 7)
            if ih > bp:
                best_cap, bp = cap, ih
        print(f"\n  期限{D}ヶ月：IS窓のH = {h_is:.2f} / IS選択の上限 = {best_cap:.0f}倍"
              f"（IS到達 {100*bp:.1f}%）")
        print(f"{'k':>5}{'比例 OOS':>11}{'期限意識 OOS（完全窓外）':>26}{'差':>10}")
        for k in K_SHOW:
            bh, _, _ = evaluate_step(data["OOS"], k, None, 0.0,
                                     a_oos, QUIET_END, D, 7)
            ph, pr, n = evaluate_step(data["OOS"], k, pol_is, best_cap,
                                      a_oos, QUIET_END, D, 7)
            print(f"{k:>5.0f}{100*bh:>10.1f}%{100*ph:>25.1f}%"
                  f"{100*(ph-bh):>9.1f}pt")

    # ---------- C. 非重複起点 ----------
    print("\n" + "=" * 112)
    print("【C. 非重複起点】起点が重ならないように間隔を期限と同じにする")
    print("=" * 112)
    pol = das.Policy(H=0.48)
    print(f"{'期限':>5}{'k':>4}{'起点数':>8}{'比例':>9}{'期限意識':>11}"
          f"{'差':>9}{'差の95%区間（Wilson・粗い）':>30}")
    for D in DEADLINES:
        for k in K_SHOW:
            bh, _, n = evaluate_step(data["OOS"], k, None, 0.0,
                                     a_oos, QUIET_END, D, D * 30)
            ph, _, n2 = evaluate_step(data["OOS"], k, pol, 3.0,
                                      a_oos, QUIET_END, D, D * 30)
            lb, ub = wilson(round(bh * n), n)
            lp, up = wilson(round(ph * n2), n2)
            print(f"{D:>4}月{k:>4.0f}{n:>8}{100*bh:>8.1f}%{100*ph:>10.1f}%"
                  f"{100*(ph-bh):>8.1f}pt"
                  f"{f'比例[{100*lb:.0f},{100*ub:.0f}] 意識[{100*lp:.0f},{100*up:.0f}]':>30}")
    print("\n  ※ 非重複でも起点は少数になるので区間は広い。**有意性の主張には使えない**")

    # ---------- D. 単純代理方策 ----------
    print("\n" + "=" * 112)
    print("【D. 単純な代理方策】倍率 = min(上限, 1/√τ)。**x に依存しない**")
    print("=" * 112)
    print("  もし単純版で同じ効果が出るなら、**MQL5の実装がずっと簡単になる**")
    simple = Simple()
    print(f"{'期限':>5}{'k':>4}{'比例':>9}{'HJB方策':>10}{'単純 1/√τ':>12}{'単純−HJB':>11}")
    for D in DEADLINES:
        for k in K_SHOW:
            bh, _, _ = evaluate_step(data["OOS"], k, None, 0.0,
                                     a_oos, QUIET_END, D, 7)
            hh, _, _ = evaluate_step(data["OOS"], k, pol, 3.0,
                                     a_oos, QUIET_END, D, 7)
            sh, _, _ = evaluate_step(data["OOS"], k, simple, 3.0,
                                     a_oos, QUIET_END, D, 7)
            print(f"{D:>4}月{k:>4.0f}{100*bh:>8.1f}%{100*hh:>9.1f}%"
                  f"{100*sh:>11.1f}%{100*(sh-hh):>10.1f}pt")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・すべて段階2の簡易検証。**採用の根拠にはしない**")
    print("  ・非重複起点にすると件数が減り、区間が広くなる")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・最小ロット制約により、倍率を下げても実際には下がらない建玉が多い")
    print("\n完了。")


if __name__ == "__main__":
    main()
