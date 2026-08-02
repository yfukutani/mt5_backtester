# -*- coding: utf-8 -*-
"""テスターのmixlog CSV（EnableOpsLog出力）から枠別バックテスト結果を集計。
mixlog列: time,type,magic,symbol,f1=side,f2=lot,f3=price,f4=SL,f5=TP,f6=pnl,note=IN/OUT
IN/OUTを(magic,symbol)ごとFIFOペアリング（テスターは単一インスタンスなので十分）。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

NAMES = {
    20260602: "RSI_USDJPY", 20260605: "RSI_EURUSD", 20260774: "RSI_GBPUSD",
    20260622: "PB_USDJPY", 20260625: "PB_GBPJPY", 20260640: "PB_GOLD",
    20260629: "PAIR", 20260650: "CARRY", 20260680: "VBO_USDJPY",
    20261000: "SCA_USDJPY", 20261001: "SCA_GBPJPY", 20261002: "SCA_GOLD",
    20260710: "ETH", 20260720: "BTC_FUND", 20260724: "BFXREV",
}


def dt(t):
    return datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load(paths):
    q = defaultdict(list)
    rts = []
    rows = []
    for p in paths:
        with open(p, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "DEAL":
                    continue
                rows.append(r)
    rows.sort(key=lambda r: int(r["time"]))
    for r in rows:
        m = int(r["magic"])
        key = (m, r["symbol"])
        d = {"t": int(r["time"]), "magic": m, "sym": r["symbol"],
             "lot": float(r["f2"]), "pnl": float(r["f6"]), "note": r["note"].strip()}
        if d["note"] == "IN":
            q[key].append(d)
        elif q[key]:
            e = q[key].pop(0)
            rts.append({"t": e["t"], "magic": m, "sym": r["symbol"], "lot": e["lot"],
                        "pnl": d["pnl"], "exit_t": d["t"]})
    opens = [e for lst in q.values() for e in lst]
    rts.sort(key=lambda x: x["t"])
    return rts, opens


def report(label, rts, opens):
    print("=" * 96)
    print(label)
    print("%-19s %-11s %-7s %5s %9s %s" % ("entry(srv)", "sleeve", "sym", "lot", "pnl", "exit(srv)"))
    for r in rts:
        print("%-19s %-11s %-7s %5.2f %9.0f %s"
              % (dt(r["t"]), NAMES.get(r["magic"], str(r["magic"])), r["sym"], r["lot"], r["pnl"], dt(r["exit_t"])))
    agg = defaultdict(lambda: [0, 0.0])
    for r in rts:
        nm = NAMES.get(r["magic"], str(r["magic"]))
        agg[nm][0] += 1
        agg[nm][1] += r["pnl"]
    print("-" * 96)
    tn = tp = 0
    for nm in sorted(agg):
        n, p = agg[nm]
        tn += n; tp += p
        print("%-11s %5d /%9.0f" % (nm, n, p))
    print("%-11s %5d /%9.0f" % ("TOTAL", tn, tp))
    for e in opens:
        print("open at end: %s %s entry=%s lot=%.2f"
              % (NAMES.get(e["magic"], e["magic"]), e["sym"], dt(e["t"]), e["lot"]))


if __name__ == "__main__":
    label = sys.argv[1]
    rts, opens = load(sys.argv[2:])
    report(label, rts, opens)
