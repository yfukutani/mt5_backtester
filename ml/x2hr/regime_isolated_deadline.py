"""V073：期限延長の効果から**「途中で相場が好転する」寄与を分離**する。

【V072で残った疑問】
共通起点（2016-11〜2019-12）で測ると期限延長は単調に効いた。
しかし**18ヶ月経路は2020-2021年の金の大相場を含む**（2019年起点なら2021年まで走る）。

> **「弱い時期に始めて、途中で相場が好転する」経路が長期の改善を支えている。**

**これを分離しないと「期限を延ばせば届く」とは言えない。**

【設計】
**経路全体が「金が静かな時期」に収まる起点だけ**を使う。

- V050・V051で、**金が動き始めたのは2020年**と特定済み
  （GOLD枠のシャープ：2016-2019 = 0.0248、2020-2021.06 = 0.2298）
- したがって **起点 ＋ 18暦月 ≤ 2020-01-01** を満たす起点だけを使う
- 起点は 2016-11-09 〜 2018-07 の範囲（**約90個**）
- **kは固定**（V072と同じ選び方）
- 各起点について1本の18ヶ月経路を走らせ、初回到達日を記録

**これで「単一の弱い局面の中で、期限を延ばすと届くのか」が測れる。**

【比較する3条件】
| 条件 | 起点の範囲 | 経路が含む相場 |
|---|---|---|
| **A 弱局面のみ** | 2016-11〜2018-07 | 2016-2019（金が静か）のみ |
| **B V072の共通起点** | 2016-11〜2019-12 | 2016-2021（好転を含む） |
| **C IS窓** | 2021-06〜2024-12 | 2021-2026（全期間が大相場） |

【限界】
- 弱局面のみの起点は約90個で、**V072の163個よりさらに少ない**
- 起点が重なるため独立ではない
- 「2020年が境目」というのはV050・V051の観測に基づく事後的な区切りである
- 測っているのは「含み損益・証拠金制約を無視した、確定損益残高の到達割合」
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod

MAX_MONTHS = 18
CHECK_MONTHS = [3, 6, 9, 12, 18]
MULTS = [2.0, 1.5, 1.3, 1.2]
QUIET_END = datetime(2020, 1, 1, tzinfo=timezone.utc)   # 金が動き始めた境目


def run_range(rec, ti, start, end_cap, k, mult):
    """起点 ＋ 18暦月 ≤ end_cap を満たす起点だけで走らせる。"""
    out = []
    d = start
    while cod.add_months(d, MAX_MONTHS) <= end_cap:
        t_end = cod.add_months(d, MAX_MONTHS)
        hit, ruin = cod.first_reach(rec, ti, int(d.timestamp()),
                                    int(t_end.timestamp()), k, mult)
        out.append((d, hit, ruin))
        d += timedelta(days=cod.ORIGIN_STEP_DAYS)
    return out


def main():
    print("=" * 104)
    print("V073：期限延長の効果から「途中で相場が好転する」寄与を分離する")
    print("=" * 104)
    print("V050・V051で、金が動き始めたのは**2020年**と特定済み")
    print("（GOLD枠のシャープ：2016-2019 = 0.0248、2020-2021.06 = 0.2298）")
    print(f"→ **起点 ＋ {MAX_MONTHS}暦月 ≤ {QUIET_END:%Y-%m-%d}** を満たす起点だけを使い、")
    print("   経路全体が「金が静かな時期」に収まるようにする。\n")

    data = {w: co.load_events(w) for w in ("IS", "OOS")}
    a_oos, b_oos = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    for mult in MULTS:
        print("=" * 104)
        print(f"【目標 {mult:g}倍】")
        print("=" * 104)
        # kはV072と同じ選び方（IS窓・3ヶ月・共通起点）
        hits = {}
        for k in co.K_GRID:
            res = cod.run_window(*data["IS"], "IS", k, mult)
            h, _, _ = cod.cumulative(res, 3)
            hits[k] = h
        best = max(hits.values())
        flat = [k for k in co.K_GRID if hits[k] >= best - co.FLAT_TOL]
        k_sel = flat[len(flat) // 2]
        print(f"  固定k = {k_sel}（V072と同じ選び方）\n")

        conds = [
            ("A 弱局面のみ(OOS)", data["OOS"], a_oos, QUIET_END),
            ("B V072共通起点(OOS)", data["OOS"], a_oos, b_oos),
            ("C IS窓", data["IS"], a_is, b_is),
        ]
        print(f"{'条件':>20}{'起点':>7}"
              + "".join(f"{f'{m}ヶ月':>9}" for m in CHECK_MONTHS)
              + f"{'3→18の伸び':>13}")
        for label, (rec, ti), st, cap in conds:
            res = run_range(rec, ti, st, cap, k_sel, mult)
            if not res:
                print(f"{label:>20}  起点なし")
                continue
            vals = []
            for m in CHECK_MONTHS:
                h, r, n = cod.cumulative(res, m)
                vals.append(h)
            print(f"{label:>20}{len(res):>7}"
                  + "".join(f"{100*v:>8.1f}%" for v in vals)
                  + f"{100*(vals[-1]-vals[0]):>+12.1f}pt")
        # 破綻も出す
        print(f"\n{'条件':>20}{'18ヶ月の破綻':>14}{'18ヶ月の未決着':>16}")
        for label, (rec, ti), st, cap in conds:
            res = run_range(rec, ti, st, cap, k_sel, mult)
            if not res:
                continue
            h, r, n = cod.cumulative(res, 18)
            print(f"{label:>20}{100*r:>13.1f}%{100*(1-h-r):>15.1f}%")
        print()

    print("=" * 104)
    print("【読み方】")
    print("=" * 104)
    print("  ・A（弱局面のみ）で3→18ヶ月の伸びが小さければ、")
    print("    V072で見た改善は**相場好転の寄与**だったことになる")
    print("  ・Aでも伸びるなら、**期限延長そのものに効果がある**")
    print("\n【限界】")
    print("  ・Aの起点は約90個でV072の163個よりさらに少ない")
    print("  ・起点が重なるため独立ではない")
    print("  ・「2020年が境目」はV050・V051の観測に基づく**事後的な区切り**である")
    print("\n完了。")


if __name__ == "__main__":
    main()
