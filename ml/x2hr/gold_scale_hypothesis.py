"""V050：GOLDの円建て損益が大きくなった原因を、**約定価格**から切り分ける。

【なぜこれが最重要か】
V040で、ブック純益の56%（593,322円 / 1,055,149円）がGOLD枠であり、
**直近2年（2025-2026）に限れば実質100%がGOLDと暗号**だと分かった。
GOLD枠の1取引あたり損益は 2017-2019年の11〜15円から 2026年の7,089円へ、
**約500倍**になっている。

**この上昇が何によるものかで、将来の見通しが正反対になる。**

| 原因 | 将来への含意 |
|---|---|
| **(a) 金価格の水準上昇** | 固定0.01ロットでは同じ%変動でも円建て損益が比例して大きくなる。**価格が下がれば戻る** |
| **(b) ボラティリティの上昇** | 値幅そのものが広がった。**平常化すれば戻る** |
| **(c) 戦略の優位性の向上** | シャープが上がっているなら質の改善。**持続しうる** |

【本スクリプトがすること】
dealログには `price`（約定価格）が入っている。**これを使えば外部データなしで
金価格の推移が復元できる。** 年ごとに、

1. GOLD枠の**平均約定価格**（＝金価格の水準の代理）
2. 1取引あたり損益を**約定価格で割った値**（＝価格水準を正規化した損益）
3. 1取引あたりの**値幅**（損益 ÷ ロット ÷ 契約サイズ）とその標準偏差
4. シャープ（尺度不変）

を出す。**正規化後も上昇が残るなら、原因は(c)＝質の改善である。**

【限界】
- 約定価格は入口dealのものを使う（決済価格ではない）
- 契約サイズは100（XAUUSDの標準）と仮定
- 円換算レート（usdjpy列）も年で変わるため、その影響も分離して見る
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl

GOLD_MAGICS = {20260640, 20261002, 20261003}
CONTRACT = 100.0     # XAUUSD 1ロット = 100オンス（XM標準）


def load():
    """FULL窓の GOLD枠について (year, profit, volume, entry_price, usdjpy) を返す。"""
    fx, gold = dkl.resolve_runs()
    rows = []
    for src in (fx.get("FULL"), gold.get("FULL")):
        if src is None:
            continue
        raw = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            if m not in GOLD_MAGICS:
                continue
            raw.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                        float(r["profit"]), float(r["volume"]),
                        float(r["price"]), float(r.get("usdjpy") or 0.0)))
        raw.sort()
        opened = {}
        for t, entry, pid, profit, vol, price, uj in raw:
            if entry == 0:
                opened[pid] = (price, vol, uj)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                y = datetime.fromtimestamp(t, tz=timezone.utc).year
                rows.append((y, profit, o[1], o[0], o[2]))
    return rows


def main():
    rows = load()
    if not rows:
        print("GOLD枠のデータが取得できなかった")
        return
    years = sorted({y for y, *_ in rows})

    print("=" * 118)
    print("V050：GOLDの円建て損益の上昇は、価格水準か・ボラか・質か")
    print("=" * 118)
    print("dealログの約定価格から金価格の推移を復元し、正規化して比較する。\n")

    print(f"{'年':>6}{'取引':>7}{'平均約定価格':>13}{'USDJPY':>9}"
          f"{'1取引平均円':>12}{'価格で正規化':>13}{'値幅(USD)':>11}"
          f"{'値幅の標準偏差':>15}{'シャープ':>10}")
    prev_norm = None
    for y in years:
        sub = [(p, v, pr, uj) for yy, p, v, pr, uj in rows if yy == y]
        if len(sub) < 2:
            continue
        prof = np.array([x[0] for x in sub])
        vol = np.array([x[1] for x in sub])
        price = np.array([x[2] for x in sub])
        uj = np.array([x[3] for x in sub])
        # 値幅(USD) = 円損益 / usdjpy / (ロット × 契約サイズ)
        ujv = np.where(uj > 0, uj, np.nan)
        move = prof / ujv / (vol * CONTRACT)
        sd = prof.std(ddof=1)
        # 価格水準で正規化した円損益（1取引あたり／約定価格）
        norm = float((prof / price).mean())
        print(f"{y:>6}{len(prof):>7}{price.mean():>13.1f}{np.nanmean(ujv):>9.1f}"
              f"{prof.mean():>12.0f}{norm:>13.3f}"
              f"{np.nanmean(move):>11.2f}{np.nanstd(move, ddof=1):>15.2f}"
              f"{(prof.mean()/sd if sd else 0):>10.4f}")

    print("\n" + "=" * 118)
    print("【期間でまとめる】")
    print("=" * 118)
    P = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023),
         ("2024-2026", 2024, 2026)]
    print(f"{'期間':>12}{'取引':>7}{'平均約定価格':>13}{'1取引平均円':>12}"
          f"{'価格で正規化':>13}{'値幅(USD)':>11}{'値幅の標準偏差':>15}{'シャープ':>10}")
    base = {}
    for lab, a, b in P:
        sub = [(p, v, pr, uj) for yy, p, v, pr, uj in rows if a <= yy <= b]
        if len(sub) < 2:
            continue
        prof = np.array([x[0] for x in sub])
        vol = np.array([x[1] for x in sub])
        price = np.array([x[2] for x in sub])
        uj = np.array([x[3] for x in sub])
        ujv = np.where(uj > 0, uj, np.nan)
        move = prof / ujv / (vol * CONTRACT)
        sd = prof.std(ddof=1)
        base[lab] = dict(price=price.mean(), yen=prof.mean(),
                         norm=float((prof / price).mean()),
                         move=float(np.nanmean(move)),
                         movesd=float(np.nanstd(move, ddof=1)),
                         sharpe=float(prof.mean() / sd) if sd else 0.0)
        print(f"{lab:>12}{len(prof):>7}{price.mean():>13.1f}{prof.mean():>12.0f}"
              f"{base[lab]['norm']:>13.3f}{base[lab]['move']:>11.2f}"
              f"{base[lab]['movesd']:>15.2f}{base[lab]['sharpe']:>10.4f}")

    if "2016-2019" in base and "2024-2026" in base:
        a, b = base["2016-2019"], base["2024-2026"]
        print("\n" + "=" * 118)
        print("【2016-2019 → 2024-2026 の倍率で原因を分解する】")
        print("=" * 118)
        def r(x, y):
            return (y / x) if x else float("nan")
        print(f"  円建ての1取引平均      : {a['yen']:>8.0f}円 → {b['yen']:>8.0f}円"
              f"   **{r(a['yen'], b['yen']):.1f}倍**")
        print(f"  金価格の水準           : {a['price']:>8.1f}   → {b['price']:>8.1f}"
              f"     {r(a['price'], b['price']):.2f}倍  ← (a)価格水準の寄与")
        print(f"  値幅の標準偏差(USD)    : {a['movesd']:>8.2f}   → {b['movesd']:>8.2f}"
              f"     {r(a['movesd'], b['movesd']):.2f}倍  ← (b)ボラの寄与")
        print(f"  シャープ(尺度不変)     : {a['sharpe']:>8.4f} → {b['sharpe']:>8.4f}"
              f"     {r(a['sharpe'], b['sharpe']):.2f}倍  ← (c)質の寄与")
        print(f"\n  (a)×(b) = {r(a['price'], b['price']) * r(a['movesd'], b['movesd']):.1f}倍"
              f"  ／ 実際の円建て倍率 = {r(a['yen'], b['yen']):.1f}倍")
        print("  → (a)×(b) が実際の倍率をほぼ説明できるなら、原因は価格水準とボラであり、")
        print("     質の改善ではない。その場合、金が落ち着けば円建て損益は戻る。")

    print("\n完了。")


if __name__ == "__main__":
    main()
