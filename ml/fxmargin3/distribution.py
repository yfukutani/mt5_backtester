"""fxmargin3 の各 run について、月利の分布と上位3か月除外値を出す。

【何に答えるか】
幾何平均の月利1つでは「少数の月が全体を持ち上げている」構成を見抜けない。
fxrisk3 で T036 が OOS 4.90% なのに**上位3か月を除くと −0.10%** だったのが実例。
段階3の run にも同じ物差しを当てる。

【fxrisk3/monthly_distribution.py との違い】
あちらは対象パスが決め打ちなので、fxmargin3 の run_deals を拾えない。
こちらは results.csv を読んで、記録された deal ログをそのまま使う。

【限界】
- equity は決済損益のみ＝**含み損益を含まない**。
  ⚠️ `margin_feasibility.py` の訂正（2026-09-15）と同じ注意が要る——
  このブックは Carry / PB が含み益を抱えたまま持つので、**月の切れ目のズレは片側に偏る**。
  月ごとの損益は「その月に決済された分」であり、「その月に発生した分」ではない。
- 段階3の run そのもの（純益・DD・取引数）は MT5 の実測値。ここで加工するのは月次分解だけ。
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500000
TARGET = 6.0
MONTHS = {"OOS": 55.0, "FULL": 115.0}


def monthly_returns(path):
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


def ex_top(vals, k):
    """上位k か月を除いた幾何平均（%/月）。"""
    drop = set(sorted(range(len(vals)), key=lambda i: -vals[i])[:k])
    g = 1.0
    for i, v in enumerate(vals):
        if i not in drop:
            g *= (1.0 + v / 100.0)
    n = len(vals) - len(drop)
    return (math.pow(g, 1.0 / n) - 1.0) * 100.0 if n > 0 and g > 0 else float("nan")


def main():
    res = ROOT / "results.csv"
    if not res.exists():
        sys.exit("results.csv がありません")
    rows = [r for r in csv.DictReader(open(res, encoding="utf-8"))
            if r["status"] == "OK"]
    want = sys.argv[1:]
    if want:
        rows = [r for r in rows if r["proposal_id"] in want]
    if not rows:
        sys.exit("対象の run がありません")

    print(f"月利の分布（入金 {DEPOSIT:,}円・目標 {TARGET:.0f}%/月）")
    print("純益・DD・取引数は MT5 実測。月次分解は決済損益ベース。\n")
    hdr = (f"{'案':<6}{'窓':<6}{'純益':>14}{'月利':>8}{'中央値':>9}"
           f"{'上位3除外':>11}{'最大DD':>9}{'6%以上':>9}{'取引':>7}")
    print(hdr)
    print("-" * len(hdr.encode("utf-8").decode("utf-8")) )
    for r in rows:
        path = Path(r["deals"])
        if not path.exists():
            path = ROOT / "run_deals" / path.name
        if not path.exists():
            print(f"{r['proposal_id']:<6}{r['window']:<6}  deal ログ無し")
            continue
        months = MONTHS[r["window"]]
        rets, final_eq = monthly_returns(path)
        vals = [v for _, v in rets]
        if not vals:
            continue
        geo = (math.pow(final_eq / DEPOSIT, 1.0 / months) - 1.0) * 100.0
        over = sum(1 for v in vals if v >= TARGET)
        print(f"{r['proposal_id']:<6}{r['window']:<6}"
              f"{float(r['net']):>14,.0f}{geo:>7.2f}%{statistics.median(vals):>8.2f}%"
              f"{ex_top(vals, 3):>10.2f}%{float(r['dd_pct']):>8.2f}%"
              f"{over:>5}/{len(vals):<3}{int(r['trades']):>7}")
    print()
    print("注: 幾何平均と上位3除外の差が大きいほど、少数の月に依存している。")
    print("    「幾何平均が6%」と「毎月6%」はまったく違う要求である。")


if __name__ == "__main__":
    main()
