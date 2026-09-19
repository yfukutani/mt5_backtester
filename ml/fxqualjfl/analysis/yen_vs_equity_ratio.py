# -*- coding: utf-8 -*-
"""枠の円建て純益と「残高比の損益（R）」が食い違う理由を、時間順に割って見る。

複利では枠の円建て純益 = Σ(R_i × 残高_i) なので、残高が100倍になる窓では
**後半の取引が桁で支配する**。円建てが赤字でも R の合計が黒字なら、
それは「優位性が無い」ではなく「**負けた時刻が遅かった**」を意味する。
"""
import csv
import datetime
import sys
from collections import defaultdict

MAGIC = {
    20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
    20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
    20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj",
}
DEPOSIT = 500000.0


def trades(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8", errors="replace")):
        rows.append((int(r["time"]), r["entry"], r["position_id"],
                     int(r["magic"]), float(r["profit"])))
    rows.sort()
    bal = DEPOSIT
    owner, bal_at, closed, tclose = {}, {}, defaultdict(float), {}
    for t, e, pid, mg, pr in rows:
        if e == "0":
            owner[pid] = mg
            bal_at[pid] = bal
        else:
            closed[pid] += pr
            tclose[pid] = t
        bal += pr
    out = defaultdict(list)
    for pid, pnl in closed.items():
        name = MAGIC.get(owner.get(pid))
        if name:
            out[name].append((tclose[pid], pnl, bal_at[pid]))
    for v in out.values():
        v.sort()
    return out


def show(path, label, k=5):
    bys = trades(path)
    print(f"\n===== {label} =====")
    print(f"{'枠':8s} {'円建て純益':>14s} {'合計R':>9s} {'複利R(積)':>10s}  五分割の R（時間順）")
    for name, tr in sorted(bys.items()):
        n = len(tr)
        yen = sum(x[1] for x in tr)
        R = sum(x[1] / x[2] for x in tr) * 100
        prod = 1.0
        for _, p, b in tr:
            prod *= (1 + p / b)
        segs = []
        for i in range(k):
            s = tr[n * i // k:n * (i + 1) // k]
            if not s:
                segs.append("  -")
                continue
            segs.append(f"{sum(x[1] / x[2] for x in s) * 100:+6.1f}")
        print(f"{name:8s} {yen:>14,.0f} {R:>+8.1f}% {(prod-1)*100:>+9.1f}%  " + " ".join(segs))


if __name__ == "__main__":
    for a in sys.argv[1:]:
        lbl, p = a.split("=", 1)
        show(p, lbl)
