"""V101：**新枠を何倍で足せば不毛期間が消えるか**（2026-09-13）。

【V100bで分かったこと】
RSI横展開4枠は**従来の運用ルール（IS/OOS両プラス）を4枠とも満たさない**。
しかし**V099の新基準では違う姿が見える。**

| 枠 | 弱局面 純益 | **弱局面の不毛月** | 月次相関 | IS窓の不毛月 |
|---|---:|---:|---:|---:|
| **RSI GOLD** | **−9,755** | **+8,986** | **−0.247** | +2,832 |
| RSI AUDUSD | −597 | +1,838 | −0.195 | +2,781 |
| RSI NZDUSD | +2,097 | +3,771 | −0.077 | −1,102 |
| RSI USDCAD | −1,408 | −2,594 | +0.012 | +202 |
| （参考）RSI GBPUSD | +16,136 | +6,475 | −0.177 | +1,101 |

**RSI GOLD は弱局面全体では赤字（−9,755円）なのに、不毛月では +8,986円 稼いでいる。**
**＝良い月に負けて、不毛な月に稼ぐ。** これはV099が求めた性質そのもの。

【本スクリプトで測ること】
既存ブックに新枠を **α倍** で足したとき、**12ヶ月移動合計の最小値**と
**マイナス窓の数**がどう変わるか。

**判定は「純益が増えるか」ではなく「不毛期間が消えるか」。**

α を上げると不毛月は埋まるが、良い月の足を引っ張る。**最適な α があるはず。**

【限界】
- 損益の線形な足し算。**最小ロット制約を無視している**
  （0.01ロットの枠をα倍するには実際にはロットを上げる必要がある）
- 弱局面は38ヶ月。12ヶ月窓は27個しかない
- **αを弱局面で選べば、弱局面で良く見えるのは当たり前**。IS窓でも確認する
- **段階3のバックテストは1×で回した。α倍は近似である**
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import barren_check as bc

WEAK = bc.WEAK
IS_W = bc.IS_W
NAMES = bc.NAMES
ALPHAS = [0, 1, 2, 3, 5, 8, 12, 20]


def rolling(v, w):
    if len(v) < w:
        return np.array([])
    return np.array([v[i:i + w].sum() for i in range(len(v) - w + 1)])


def main():
    print("=" * 112)
    print("V101：新枠を何倍で足せば不毛期間が消えるか")
    print("=" * 112)
    print("★ 判定は「純益が増えるか」ではなく「**不毛期間が消えるか**」。\n")

    res = list(csv.DictReader(open(ROOT / "results.csv", encoding="utf-8")))
    by_w = {r["window"]: r for r in res}

    for label, (a, b), wkey in (("OOS 弱局面（2016-11〜2019-12）", WEAK, "OOS"),
                                ("IS窓（2021-06〜2026-06）", IS_W, "IS")):
        ms, book = bc.book_monthly(a, b)
        deal = ROOT / "run_deals" / by_w[wkey]["deals"]
        new, cnt = bc.new_monthly(deal, a, b)
        print("=" * 112)
        print(f"【{label}】{len(ms)}ヶ月 / 既存ブック純益 {book.sum():+,.0f}円")
        print("=" * 112)
        base12 = rolling(book, 12)
        base6 = rolling(book, 6)
        print(f"  現状：12ヶ月移動の最小 {base12.min():+,.0f}円 / "
              f"マイナス窓 {int((base12 <= 0).sum())}/{len(base12)}"
              f" ｜ 6ヶ月移動の最小 {base6.min():+,.0f}円 / "
              f"マイナス窓 {int((base6 <= 0).sum())}/{len(base6)}\n")

        for m, name in NAMES.items():
            v = new.get(m)
            if v is None:
                continue
            print(f"--- {name}（{cnt[m]}件・単独純益 {v.sum():+,.0f}円）---")
            print(f"{'α':>5}{'合成 純益':>12}{'12月移動 最小':>15}"
                  f"{'12月マイナス窓':>15}{'6月移動 最小':>14}{'6月マイナス窓':>14}")
            for al in ALPHAS:
                c = book + al * v
                r12 = rolling(c, 12)
                r6 = rolling(c, 6)
                print(f"{al:>5}{c.sum():>12,.0f}{r12.min():>15,.0f}"
                      f"{f'{int((r12 <= 0).sum())}/{len(r12)}':>15}"
                      f"{r6.min():>14,.0f}"
                      f"{f'{int((r6 <= 0).sum())}/{len(r6)}':>14}")
            print()

        # 4枠まとめて足す
        allv = np.sum([new[m] for m in NAMES if m in new], axis=0)
        print(f"--- **4枠まとめて**（単独純益 {allv.sum():+,.0f}円）---")
        print(f"{'α':>5}{'合成 純益':>12}{'12月移動 最小':>15}"
              f"{'12月マイナス窓':>15}{'6月移動 最小':>14}{'6月マイナス窓':>14}")
        for al in ALPHAS:
            c = book + al * allv
            r12 = rolling(c, 12)
            r6 = rolling(c, 6)
            print(f"{al:>5}{c.sum():>12,.0f}{r12.min():>15,.0f}"
                  f"{f'{int((r12 <= 0).sum())}/{len(r12)}':>15}"
                  f"{r6.min():>14,.0f}"
                  f"{f'{int((r6 <= 0).sum())}/{len(r6)}':>14}")
        print()

    print("=" * 112)
    print("【読み方】")
    print("=" * 112)
    print("  ・**弱局面でもIS窓でも、12ヶ月のマイナス窓が0になるα**があれば採用候補")
    print("  ・弱局面だけで良く見えるαは**弱局面で選んだから**であり、根拠にならない")
    print("  ・純益が減ってもマイナス窓が消えるなら、**目的（2倍化）には有利**")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・損益の線形な足し算。**最小ロット制約を無視している**")
    print("  ・弱局面は38ヶ月。12ヶ月窓は27個しかない")
    print("  ・**段階3のバックテストは1×で回した。α倍は近似である**")
    print("    → αを決めたら、その倍率で改めてMT5バックテストが必要")
    print("\n完了。")


if __name__ == "__main__":
    main()
