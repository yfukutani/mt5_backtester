# -*- coding: utf-8 -*-
"""確定版の Boost 判別（近傍中央値比・窓=前後20取引・閾値3.0）で §4 の表を作り直す。"""
import csv, collections, os, statistics

D = r"C:\Users\f\source\repos\mt5_backtester\ml\fxqualexec\run_deals"
FILES = [("mc_oos_E000_20260919084236_6541_deals.csv", "OOS"),
         ("mc_is_E000_20260919084611_dbd2_deals.csv", "IS")]
MG, NM = "20261001", "sca_gj"
HALF, THR = 20, 3.0

for fn, lab in FILES:
    rows = list(csv.DictReader(open(os.path.join(D, fn), encoding="utf-8")))
    rows.sort(key=lambda r: (int(r["time"]), r["entry"]))
    bal, bal_at = 500000.0, {}
    for r in rows:
        if r["entry"] == "0":
            bal_at.setdefault(r["position_id"], bal)
        bal += float(r["profit"])
    byid = collections.defaultdict(list)
    for r in rows:
        byid[r["position_id"]].append(r)
    recs = []
    for pid, g in byid.items():
        ins = [x for x in g if x["magic"] == MG and x["entry"] == "0"]
        outs = [x for x in g if x["magic"] == MG and x["entry"] == "1"]
        if not ins or not outs:
            continue
        e, o = ins[0], outs[0]
        R = abs(float(e["price"]) - float(e["sl"])) * float(e["volume"]) * 100000
        eq = bal_at.get(pid, 0.0)
        if R > 0 and eq > 0:
            recs.append({"t": int(e["time"]), "R": R, "eq": eq,
                         "p": float(o["profit"])})
    recs.sort(key=lambda x: x["t"])
    n = len(recs)
    for i, r in enumerate(recs):
        lo, hi = max(0, i - HALF), min(n, i + HALF + 1)
        nb = [recs[j]["R"] for j in range(lo, hi) if j != i]
        r["w"] = r["R"] / statistics.median(nb)
    bo = [r for r in recs if r["w"] > THR]
    pl = [r for r in recs if r["w"] <= THR]
    print(f"=== {lab} {NM} n={n} ===")
    for tag, s in (("Boost", bo), ("plain", pl), ("全体", recs)):
        mr = statistics.mean([r["p"] / r["R"] for r in s])
        sr = sum(r["p"] / r["R"] for r in s)
        eq = sum(r["p"] / r["eq"] for r in s) * 100
        print(f"  {tag:6s} n={len(s):4d}  平均R={mr:+.3f}  ΣR={sr:+7.1f}  "
              f"円建て={sum(r['p'] for r in s):>12,.0f}  equity比ΣR={eq:+6.1f}%")
