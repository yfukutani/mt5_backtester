"""測定の途中経過を、報告に必要な数値をそろえた形で出す。

`CLAUDE.md`「報告に必ず含める数値」に合わせ、**損益・想定月利・最大DD**を
IS窓（ここではFULL）とOOS窓の両方で出す。さらに 2026-09-15 に追加した
「幾何平均だけを見ると実態を誤る」への対応として、**月利の中央値**と
**上位3か月を除いた幾何平均**も併記する。

DDは決済損益ベースの下限値で、建玉中の含み損を含まない。
"""
from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500000
MONTHS = {"FULL": 115.0, "OOS": 55.0}
TARGET = 6.0


def curve(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0:
            continue
        rows.append((int(r["time"]), p))
    rows.sort()
    eq = peak = min_eq = DEPOSIT
    worst = 0.0
    per_month = defaultdict(float)
    for t, p in rows:
        eq += p
        min_eq = min(min_eq, eq)
        peak = max(peak, eq)
        worst = max(worst, (peak - eq) / peak)
        d = datetime.fromtimestamp(t, timezone.utc)
        per_month[(d.year, d.month)] += p
    return eq, worst * 100, min_eq, per_month


def monthly_stats(per_month):
    eq = DEPOSIT
    rets = []
    for k in sorted(per_month):
        if eq <= 0:
            break
        rets.append(100.0 * per_month[k] / eq)
        eq += per_month[k]
    if not rets:
        return None, None
    med = statistics.median(rets)
    drop = set(sorted(range(len(rets)), key=lambda i: -rets[i])[:3])
    g = 1.0
    n = 0
    for i, v in enumerate(rets):
        if i in drop:
            continue
        g *= (1.0 + v / 100.0)
        n += 1
    ex3 = (math.pow(g, 1.0 / n) - 1.0) * 100.0 if n > 0 and g > 0 else float("nan")
    return med, ex3


def main():
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["status"] == "OK" and r.get("deals")]
    by = defaultdict(dict)
    for r in rows:
        by[r["proposal_id"]][r["window"]] = r

    props = {p["proposal_id"]: p for p in
             csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8"))}
    total = len(props) * 2
    print(f"fxrisk3 進捗: {len(rows)} / {total} run  （入金 {DEPOSIT:,}円・目標 月利{TARGET:.0f}%）")
    print("月利は幾何平均の複利。DDは直近ピーク比かつ決済損益ベース＝含み損を含まない下限値。\n")

    head = (f"{'案':<6}{'群':<3}{'設定':<44}"
            f"{'FULL純益':>12}{'月利':>7}{'DD':>7}"
            f"{'OOS純益':>11}{'月利':>7}{'DD':>7}{'中央値':>8}{'上位3除外':>10}{'最低資産':>10}")
    print(head)
    print("-" * len(head))
    recs = []
    for pid in sorted(by):
        w = by[pid]
        if "FULL" not in w:
            continue
        fe, fd, _, fm = curve(w["FULL"]["deals"])
        fmo = (math.pow(fe / DEPOSIT, 1 / MONTHS["FULL"]) - 1) * 100
        if "OOS" in w:
            oe, od, omin, om = curve(w["OOS"]["deals"])
            omo = (math.pow(oe / DEPOSIT, 1 / MONTHS["OOS"]) - 1) * 100
            med, ex3 = monthly_stats(om)
            onet = float(w["OOS"]["net"])
        else:
            oe = od = omin = onet = omo = med = ex3 = None
        recs.append((omo if omo is not None else -999, pid, w, fe, fd, fmo,
                     onet, omo, od, med, ex3, omin))

    for _, pid, w, fe, fd, fmo, onet, omo, od, med, ex3, omin in sorted(
            recs, key=lambda x: -x[0]):
        d = props[pid]["description"]
        fam = props[pid]["family"]
        fnet = float(w["FULL"]["net"])
        if omo is None:
            print(f"{pid:<6}{fam:<3}{d[:42]:<44}{fnet:>12,.0f}{fmo:>6.2f}%{fd:>6.1f}%"
                  f"{'測定中':>11}")
            continue
        print(f"{pid:<6}{fam:<3}{d[:42]:<44}{fnet:>12,.0f}{fmo:>6.2f}%{fd:>6.1f}%"
              f"{onet:>11,.0f}{omo:>6.2f}%{od:>6.1f}%{med:>7.2f}%{ex3:>9.2f}%{omin:>10,.0f}")

    done = [x for x in recs if x[7] is not None]
    if done:
        best = max(done, key=lambda x: x[7])
        print(f"\n現時点のOOS最良: {best[1]} {best[7]:.2f}%/月 "
              f"（中央値 {best[9]:.2f}% / 上位3除外 {best[10]:.2f}% / 最大DD {best[8]:.1f}%）")
        print(f"目標 {TARGET:.0f}%/月 までの距離: {TARGET / best[7]:.1f}倍")
        reached = [x for x in done if x[7] >= TARGET]
        print(f"月利{TARGET:.0f}%に到達した案: {len(reached)} 件")


if __name__ == "__main__":
    main()
