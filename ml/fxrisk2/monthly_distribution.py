"""月利の分布を出す（段階2・採用の根拠にはしない）。

【何に答えるか】
- Claude D1「そもそも月利6%の定義を確定する」
- Claude D3「期間を長く取る——目標到達までの期間で考える」
- Claude D10「月利の分布を見る——平均でなく『6%を超える月の割合』で評価する」

【なぜ必要か】
これまで「月利」は**115か月／55か月の幾何平均**1つで報告してきた。
複利の資産曲線から作る幾何平均は、**数か月の大勝ちが全体を持ち上げていても
高く出る**。「毎月6%」と「均せば6%」はまったく違う要求である。
実運用で意味があるのは後者ではなく前者に近い。

【出すもの】各構成について、月ごとの複利リターンの
中央値・平均・最悪・最良・プラス月の割合・6%超の月の割合・
12か月移動リターンがマイナスの窓の割合。

【限界】
- equityは決済損益のみ＝含み損を含まない（DDは下限値・§4b）。
- 月末の建玉は評価されないので、月の切れ目で損益がずれる。
- **段階2の簡易検証であり、採用の根拠にはしない。**
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEPOSIT = 500000
TARGET = 6.0     # ユーザー指定の目標（%/月）


def monthly_returns(path):
    """月ごとの複利リターン（%）。月初equityに対する当月の確定損益。"""
    per = defaultdict(float)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0:
            continue
        d = datetime.fromtimestamp(int(r["time"]), timezone.utc)
        per[(d.year, d.month)] += p
    eq = DEPOSIT
    out = []
    for k in sorted(per):
        if eq <= 0:
            break
        out.append((k, 100.0 * per[k] / eq))
        eq += per[k]
    return out, eq


def rolling12_negative(rets):
    """12か月の複利リターンがマイナスになる窓の割合。"""
    vals = [r for _, r in rets]
    if len(vals) < 12:
        return None, 0, 0
    neg = 0
    tot = 0
    for i in range(len(vals) - 11):
        g = 1.0
        for v in vals[i:i + 12]:
            g *= (1.0 + v / 100.0)
        tot += 1
        if g < 1.0:
            neg += 1
    return neg / tot, neg, tot


def report(path, label, months):
    rets, final_eq = monthly_returns(path)
    vals = [r for _, r in rets]
    if not vals:
        return
    geo = (math.pow(final_eq / DEPOSIT, 1.0 / months) - 1.0) * 100.0
    pos = sum(1 for v in vals if v > 0)
    over = sum(1 for v in vals if v >= TARGET)
    frac, neg, tot = rolling12_negative(rets)
    worst_k, worst_v = min(rets, key=lambda x: x[1])
    best_k, best_v = max(rets, key=lambda x: x[1])

    print(f"{label}")
    print(f"  幾何平均の月利（これまで報告してきた値） {geo:>8.2f} %")
    print(f"  月利の中央値                             {statistics.median(vals):>8.2f} %")
    print(f"  月利の単純平均                           {statistics.fmean(vals):>8.2f} %")
    print(f"  最悪の月  {worst_v:>7.2f} %  ({worst_k[0]}-{worst_k[1]:02d})")
    print(f"  最良の月  {best_v:>7.2f} %  ({best_k[0]}-{best_k[1]:02d})")
    print(f"  プラスの月                     {pos:>4} / {len(vals)}  ({100 * pos / len(vals):.1f} %)")
    print(f"  {TARGET:.0f}%以上の月                    {over:>4} / {len(vals)}  ({100 * over / len(vals):.1f} %)")
    if frac is not None:
        print(f"  12か月移動リターンがマイナスの窓 {neg:>4} / {tot}  ({100 * frac:.1f} %)")
    # 上位3か月を除いたら幾何平均はどうなるか
    order = sorted(range(len(vals)), key=lambda i: -vals[i])[:3]
    g = 1.0
    for i, v in enumerate(vals):
        if i in order:
            continue
        g *= (1.0 + v / 100.0)
    n = len(vals) - len(order)
    ex3 = (math.pow(g, 1.0 / n) - 1.0) * 100.0 if n > 0 and g > 0 else float("nan")
    print(f"  上位3か月を除いた幾何平均                {ex3:>8.2f} %")
    print()


def main():
    repo = Path(__file__).resolve().parents[2]
    targets = [
        ("ml/fxrisk1/run_deals/fr_oos_R001_*_deals.csv", "R001 本番現行（OOS・55か月）", 55.0),
        ("ml/fxrisk1/run_deals/fr_oos_R004_*_deals.csv", "R004 前回推奨 倍率3（OOS・55か月）", 55.0),
        ("ml/fxrisk1/run_deals/fr_oos_R036_*_deals.csv", "R036 実務上の最良 倍率1（OOS・55か月）", 55.0),
        ("ml/fxrisk1/run_deals/fr_oos_R037_*_deals.csv", "R037 数字上の最良 倍率2（OOS・55か月）", 55.0),
        ("ml/fxrisk1/run_deals/fr_full_R037_*_deals.csv", "R037 同（FULL・115か月）", 115.0),
    ]
    found = False
    print(f"月利の分布（入金 {DEPOSIT:,}円・目標 {TARGET:.0f}%/月）")
    print("equityは決済損益のみ＝含み損を含まない。段階2の簡易検証。\n")
    for pat, label, months in targets:
        hits = sorted(repo.glob(pat))
        if hits:
            found = True
            report(hits[-1], label, months)
    if not found:
        sys.exit("deal ログが見つかりません")
    print("注: 「幾何平均が6%」と「毎月6%」はまったく違う要求である。")
    print("    上位3か月を除いた幾何平均との差が大きいほど、少数の月に依存している。")
    print("    段階2の簡易検証であり、採用の根拠にはしない。")


if __name__ == "__main__":
    main()
