"""time,profit だけの deal ログから、入金額に対する円建ての落ち込みを出す。

本番XM版 MIX_EA の deal ログは magic 列を持たないため枠別には割れないが、
「入金50万で始めた人がいくら減らしうるか」を出すには time と profit で足りる。

MT5の最大相対DD%は残高（＝入金＋それまでの利益）に対する比率なので、
ロット固定のブックでは後半の落ち込みほど%が小さく出る。ここでは
  ・円建ての最大落ち込み（＝倍率に比例）
  ・それが起きた時点の残高比（MT5が示す値に近い）
  ・入金額に対する比（新規開始時の危険度）
を並べて出す。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

DEPOSIT = 500000


def main(path, label, mults):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r.get("profit_jpy") or r["profit"])
        if p == 0.0:
            continue          # IN約定は損益0で記録される
        rows.append((datetime.fromtimestamp(int(r["time"]), timezone.utc), p))
    rows.sort()
    print(f"\n{'='*76}\n{label}\n{'='*76}")
    print(f"決済 {len(rows)} 件  {rows[0][0]:%Y-%m-%d} 〜 {rows[-1][0]:%Y-%m-%d}")

    worst_trade = min(rows, key=lambda x: x[1])
    months = defaultdict(float)
    for t, p in rows:
        months[(t.year, t.month)] += p
    worst_month = min(months.items(), key=lambda kv: kv[1])

    print(f"最悪の1取引: {worst_trade[1]:>10,.0f} 円  ({worst_trade[0]:%Y-%m-%d})")
    print(f"最悪の月    : {worst_month[1]:>10,.0f} 円  ({worst_month[0][0]}-{worst_month[0][1]:02d})")
    print()
    print(f"{'倍率':>5}{'最大落ち込み':>14}{'発生':>9}{'発生時残高':>13}{'残高比':>8}"
          f"{'入金50万比':>11}{'最悪1取引の入金比':>18}")
    for n in mults:
        peak = cum = 0.0
        worst = 0.0
        worst_at = None
        worst_peak = 0.0
        for t, p in rows:
            cum += p * n
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > worst:
                worst, worst_at, worst_peak = dd, t, peak
        bal = DEPOSIT + worst_peak
        print(f"x{n:<4}{worst:>14,.0f}{worst_at:%Y-%m}{bal:>13,.0f}"
              f"{100*worst/bal:>7.1f}%{100*worst/DEPOSIT:>10.1f}%"
              f"{100*abs(worst_trade[1]*n)/DEPOSIT:>17.1f}%")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(",")])
