# -*- coding: utf-8 -*-
"""SCA GBPJPY の直近の劣化が、どの部分集合に集中しているかを割る。

分け方: comment（発火の種別）/ 売買方向 / レンジ幅分位 × 期間（2024-07 前後）。
損益は残高比 R（%）で見る。複利では円建ては後半が桁で支配するため。
"""
import csv
import datetime
import sys
from collections import defaultdict

DEPOSIT = 500000.0
CUT = datetime.datetime(2024, 7, 1).timestamp()


def load(path, mg):
    rows = sorted((int(r["time"]), r["entry"], r["position_id"], int(r["magic"]),
                   float(r["profit"]), float(r["price"]), float(r["sl"]),
                   r.get("comment", ""), r["type"], float(r["volume"]))
                  for r in csv.DictReader(open(path, encoding="utf-8",
                                               errors="replace")))
    bal = DEPOSIT
    ins, bal_at, closed, tc = {}, {}, defaultdict(float), {}
    for t, e, pid, m, pr, price, sl, cm, ty, vol in rows:
        if e == "0":
            ins[pid] = (m, price, sl, cm, ty, t, vol)
            bal_at[pid] = bal
        else:
            closed[pid] += pr
            tc[pid] = t
        bal += pr
    out = []
    for pid, pnl in closed.items():
        if pid not in ins:
            continue
        m, price, sl, cm, ty, t, vol = ins[pid]
        if m != mg:
            continue
        ratio = abs(price - sl) / price if (sl > 0 and price > 0) else None
        out.append({"t": t, "R": pnl / bal_at[pid], "pnl": pnl, "cm": cm,
                    "dir": "buy" if ty == "0" else "sell", "ratio": ratio,
                    "vol": vol})
    out.sort(key=lambda x: x["t"])
    return out


def tab(tr, keyf, title):
    print(f"\n  [{title}]")
    agg = defaultdict(lambda: [0.0, 0, 0.0, 0])   # R_old, n_old, R_new, n_new
    for x in tr:
        k = keyf(x)
        a = agg[k]
        if x["t"] < CUT:
            a[0] += x["R"]
            a[1] += 1
        else:
            a[2] += x["R"]
            a[3] += 1
    print(f"    {'区分':<14s} {'〜2024-06 R':>12s} {'n':>5s} "
          f"{'2024-07〜 R':>12s} {'n':>5s}")
    for k in sorted(agg, key=lambda z: str(z)):
        ro, no, rn, nn = agg[k]
        print(f"    {str(k):<14s} {ro*100:>+11.1f}% {no:>5d} "
              f"{rn*100:>+11.1f}% {nn:>5d}")


def main(path, mg, label):
    tr = load(path, mg)
    print(f"===== {label} magic={mg} n={len(tr)} =====")
    d = [x for x in tr if x["t"] >= CUT]
    print(f"  2024-07以降: n={len(d)} 合計R {sum(x['R'] for x in d)*100:+.1f}% "
          f"円 {sum(x['pnl'] for x in d):,.0f}")
    tab(tr, lambda x: x["cm"][:18], "comment 別")
    tab(tr, lambda x: x["dir"], "方向別")
    rs = sorted(x["ratio"] for x in tr if x["ratio"] is not None)
    cuts = [rs[len(rs) * k // 5] for k in (1, 2, 3, 4)]

    def qb(x):
        if x["ratio"] is None:
            return "NA"
        for i, c in enumerate(cuts):
            if x["ratio"] < c:
                return f"Q{i+1}"
        return "Q5"
    tab(tr, qb, f"レンジ幅分位別 (境界 {['%.5f' % c for c in cuts]})")


if __name__ == "__main__":
    mg = int(sys.argv[1])
    for a in sys.argv[2:]:
        lbl, p = a.split("=", 1)
        main(p, mg, lbl)
