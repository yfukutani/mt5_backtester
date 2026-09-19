# -*- coding: utf-8 -*-
"""近傍中央値比の細部（窓の取り方・自分を含めるか）で件数がどう動くかを見る。
目標: OOS sca_gj = 159件 / +594,203、IS sca_gj = 161件 / -566,155 を再現する規則を特定する。
"""
import csv, collections, os, statistics

D = r"C:\Users\f\source\repos\mt5_backtester\ml\fxqualexec\run_deals"
FILES = [("mc_oos_E000_20260919084236_6541_deals.csv", "OOS"),
         ("mc_is_E000_20260919084611_dbd2_deals.csv", "IS")]
MG = "20261001"


def recs_for(fn):
    rows = list(csv.DictReader(open(os.path.join(D, fn), encoding="utf-8")))
    rows.sort(key=lambda r: (int(r["time"]), r["entry"]))
    byid = collections.defaultdict(list)
    for r in rows:
        byid[r["position_id"]].append(r)
    out = []
    for pid, g in byid.items():
        ins = [x for x in g if x["magic"] == MG and x["entry"] == "0"]
        outs = [x for x in g if x["magic"] == MG and x["entry"] == "1"]
        if not ins or not outs:
            continue
        e, o = ins[0], outs[0]
        R = abs(float(e["price"]) - float(e["sl"])) * float(e["volume"]) * 100000
        if R > 0:
            out.append({"t": int(e["time"]), "R": R, "p": float(o["profit"])})
    out.sort(key=lambda x: x["t"])
    return out


for fn, lab in FILES:
    rs = recs_for(fn)
    n = len(rs)
    print(f"=== {lab} sca_gj n={n} ===")
    for nb in (10, 20, 40):
        for inc_self in (False, True):
            for thr in (2.5, 3.0, 3.5):
                cnt, yen = 0, 0.0
                for i, r in enumerate(rs):
                    lo, hi = max(0, i - nb // 2), min(n, i + nb // 2 + 1)
                    win = [rs[j]["R"] for j in range(lo, hi)
                           if inc_self or j != i]
                    if not win:
                        continue
                    if r["R"] / statistics.median(win) > thr:
                        cnt += 1
                        yen += r["p"]
                mark = ""
                if lab == "OOS" and cnt == 159:
                    mark = "  <== 159"
                if lab == "IS" and cnt == 161:
                    mark = "  <== 161"
                print(f"  nb={nb:2d} self={str(inc_self):5s} thr={thr} : "
                      f"{cnt:4d}件 {yen:>12,.0f}{mark}")
