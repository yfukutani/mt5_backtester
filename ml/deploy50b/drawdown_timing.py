"""最大の落ち込みが「いつ」起きたかを出す。

MT5の最大相対DD%は、その時点の残高（＝入金＋それまでの利益）に対する比率である。
ロットは固定なので円建ての落ち込み額は期間によらずほぼ一定だが、残高は増えていく。
したがって「同じ落ち込みが初年度に起きたら何%か」と「実際に起きた時点で何%だったか」は
大きく違う。両方を出して、入金50万で始める判断の材料にする。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEPOSIT = 500000
MAGIC = {20260640: "PB GOLD", 20261002: "SCA GOLD"}


def trades(path):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        if m not in MAGIC:
            continue
        pid = int(r["position_id"])
        (ins.__setitem__(pid, r) if r["entry"] == "0" else outs[pid].append(r))
    out = []
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        out.append({
            "t": datetime.fromtimestamp(max(int(x["time"]) for x in o), timezone.utc),
            "profit": sum(float(x["profit_jpy"]) for x in o),
        })
    out.sort(key=lambda x: x["t"])
    return out


def main(paths, mults):
    tr = []
    for p in paths:
        tr += trades(p)
    tr.sort(key=lambda x: x["t"])
    print(f"取引 {len(tr)} 件  {tr[0]['t']:%Y-%m-%d} 〜 {tr[-1]['t']:%Y-%m-%d}")

    for n in mults:
        peak = cum = 0.0
        peak_t = tr[0]["t"]
        worst = 0.0
        worst_at = worst_peak = None
        # 初年度（最初の12か月）だけの落ち込みも別に測る
        first_end = tr[0]["t"].replace(year=tr[0]["t"].year + 1)
        p1 = c1 = 0.0
        worst1 = 0.0
        for t in tr:
            v = t["profit"] * n
            cum += v
            if cum > peak:
                peak, peak_t = cum, t["t"]
            dd = peak - cum
            if dd > worst:
                worst, worst_at, worst_peak = dd, t["t"], peak
            if t["t"] < first_end:
                c1 += v
                p1 = max(p1, c1)
                worst1 = max(worst1, p1 - c1)
        bal_at_peak = DEPOSIT + worst_peak
        print(f"\nx{n}")
        print(f"  最大の落ち込み {worst:>12,.0f} 円  発生 {worst_at:%Y-%m}")
        print(f"    その時点の残高 {bal_at_peak:>12,.0f} 円 → 残高比 {100*worst/bal_at_peak:>5.1f}%")
        print(f"    入金50万に対して                    → {100*worst/DEPOSIT:>5.1f}%")
        print(f"  初年度だけの落ち込み {worst1:>10,.0f} 円 → 入金比 {100*worst1/DEPOSIT:>5.1f}%")


if __name__ == "__main__":
    main(sys.argv[1:-1], [int(x) for x in sys.argv[-1].split(",")])
