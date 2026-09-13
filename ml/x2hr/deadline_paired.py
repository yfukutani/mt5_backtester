"""V085：**期限意識サイジングの対比較**（簡易検証・2026-09-13）。

【V084で残った弱点】
非重複起点にすると、弱局面では6ヶ月期限で**6起点**・12ヶ月期限で**3起点**しかない。
Wilson区間は [10,70] のように極端に広く、**有意性を主張できない。**
しかも k=4 では比例と期限意識の差がゼロだった（33.3% vs 33.3%／66.7% vs 66.7%）。

**弱局面は約38ヶ月しかない。独立な標本は原理的に足りない。**

【本スクリプトの方針】
2つの方策は**同じ起点・同じ取引列**で走っている。**対比較すればよい。**

起点ごとに (比例が到達したか, 期限意識が到達したか) の組を作り——

| | 期限意識 到達 | 期限意識 未達 |
|---|---:|---:|
| **比例 到達** | a（どちらも） | **b（比例だけ）** |
| **比例 未達** | **c（期限意識だけ）** | d（どちらも未達） |

**McNemar検定は b と c だけを使う。** 「両方とも到達／両方とも未達」の起点は情報を持たない。
**同じ相場・同じ取引列での差だけを見るので、独立でない起点の影響を大きく減らせる。**

**ただし起点が重なる以上、b・c 自体も独立ではない。**
そこで**非重複起点だけの対比較も併記する**（こちらが厳しいほうの数字）。

さらに、**IS窓でも同じ対比較を出す**（IS窓は60ヶ月あり、非重複起点が多く取れる）。

【限界】
- 重なりのある起点でのMcNemar検定は、**p値を楽観側に偏らせる**
- 非重複起点では件数が少なく、検出力が低い
- 含み損益・証拠金制約を考慮していない
- **段階2の簡易検証である。採用の根拠にはしない**
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
CAP = 3.0


def paired(rec, k, pol, cap, start, end_cap, months, step_days):
    """起点ごとに (比例の到達, 期限意識の到達) を集める。"""
    ti = [x[0] for x in rec]
    pairs = []
    d = start
    while cod.add_months(d, months) <= end_cap:
        t_end = cod.add_months(d, months)
        t0, t1 = int(d.timestamp()), int(t_end.timestamp())
        hb, _ = dc.simulate(rec, ti, t0, t1, k, None, 0.0)
        hp, _ = dc.simulate(rec, ti, t0, t1, k, pol, cap)
        pairs.append((hb, hp))
        d += timedelta(days=step_days)
    return pairs


def mcnemar(pairs):
    """(a, b, c, d, 両側p) を返す。b＝比例だけ到達、c＝期限意識だけ到達。"""
    a = sum(1 for x, y in pairs if x and y)
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if not x and y)
    d = sum(1 for x, y in pairs if not x and not y)
    n = b + c
    if n == 0:
        return a, b, c, d, 1.0
    # 二項検定（p=0.5）の両側
    lo = min(b, c)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / (2.0 ** n)
    return a, b, c, d, min(1.0, 2.0 * tail)


def main():
    print("=" * 112)
    print("V085：期限意識サイジングの対比較（簡易検証）")
    print("=" * 112)
    print("★ 2つの方策は同じ起点・同じ取引列で走っている。**対比較すればよい。**")
    print("  McNemar検定は『片方だけ到達した起点』だけを使うので、")
    print("  同じ相場を共有することによる見かけの差を大きく減らせる。\n")
    print("  ただし起点が重なる以上 b・c 自体も独立ではない。")
    print("  **重なりのある起点のp値は楽観側に偏る。非重複起点の数字も併記する。**\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    pol = das.Policy(H=0.48)

    for wname, rec, st, cap_end in (
            ("OOS 弱局面（〜2020-01）", data["OOS"], a_oos, QUIET_END),
            ("IS窓（2021-06〜2026-06）", data["IS"], a_is, b_is)):
        print("=" * 112)
        print(f"【{wname}】期限意識は上限{CAP:.0f}倍・H=0.48")
        print("=" * 112)
        for D in DEADLINES:
            print(f"\n--- 期限 {D}ヶ月 ---")
            print(f"{'起点の取り方':<18}{'k':>4}{'起点数':>7}"
                  f"{'両方':>6}{'比例だけ':>9}{'意識だけ':>9}{'両方未達':>9}"
                  f"{'比例':>8}{'期限意識':>10}{'差':>8}{'両側p':>9}")
            for step, lab in ((7, "重なりあり(7日)"), (D * 30, "**非重複**")):
                for k in K_SHOW:
                    pr = paired(rec, k, pol, CAP, st, cap_end, D, step)
                    a, b, c, d, p = mcnemar(pr)
                    n = len(pr)
                    rb = (a + b) / n if n else 0.0
                    rp = (a + c) / n if n else 0.0
                    print(f"{lab:<18}{k:>4.0f}{n:>7}{a:>6}{b:>9}{c:>9}{d:>9}"
                          f"{100*rb:>7.1f}%{100*rp:>9.1f}%"
                          f"{100*(rp-rb):>7.1f}{p:>9.3f}")
        print()

    print("=" * 112)
    print("【読み方】")
    print("=" * 112)
    print("  ・『比例だけ』が0に近く『意識だけ』が大きいほど、方策の改善は一方向的")
    print("  ・**『比例だけ』が0なら、期限意識は比例が取れた起点をすべて取れている**")
    print("  ・重なりのある起点のp値は**楽観側に偏る**ので、非重複の行を重く見る")
    print("  ・非重複の行は件数が少なく検出力が低い。**弱局面は約38ヶ月しかない**")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・重なりのある起点でのMcNemar検定はp値を楽観側に偏らせる")
    print("  ・非重複起点では件数が少なく、検出力が低い")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
