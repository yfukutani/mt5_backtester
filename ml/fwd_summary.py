# -*- coding: utf-8 -*-
"""ライブ約定CSV（pull_live_history.py出力）から枠別フォワード実績を集計。
- position_idでIN/OUTを厳密ペアリング
- --s4 "YYYY-MM-DD HH:MM,YYYY-MM-DD HH:MM"（サーバー時刻）指定時、期間内の重複往復
  （同magic・同symbol・エントリー60秒以内・同ロット）をDUPフラグ（XM二重インスタンス補正用）
- 出力: 往復リスト（時系列）+ 枠別集計（生 / 重複2本目を除いた設計換算）

usage: python ml/fwd_summary.py <deals.csv> [label] [--s4 "start,end"]
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

NAMES = {
    20260605: "RSI_EURUSD", 20260610: "RSI_USDJPY", 20260774: "RSI_GBPUSD",
    20260622: "PB_USDJPY", 20260625: "PB_GBPJPY", 20260640: "PB_GOLD",
    20260629: "PAIR", 20260650: "CARRY", 20260680: "VBO_USDJPY",
    20261000: "SCA_USDJPY", 20261001: "SCA_GBPJPY", 20261002: "SCA_GOLD",
    20260710: "ETH", 20260720: "BTC_FUND", 20260724: "BFXREV",
}


def ep(s):
    return int(datetime.strptime(s.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


def load(path):
    ins, outs = {}, defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = int(r["magic"])
            if not (20260000 <= m < 20270000):
                continue
            d = {"t": int(r["time_srv"]), "dt": r["dt_srv"], "magic": m, "sym": r["symbol"],
                 "lot": float(r["volume"]),
                 "pnl": float(r["profit"]) + float(r["swap"]) + float(r["commission"]),
                 "pid": r["position_id"]}
            if r["entry"] == "0":
                ins[d["pid"]] = d
            else:
                outs[d["pid"]].append(d)
    rts = []
    for pid, e in ins.items():
        os_ = outs.get(pid, [])
        if not os_:
            rts.append({**e, "exit_dt": "OPEN", "open": True})
            continue
        rts.append({"t": e["t"], "dt": e["dt"], "magic": e["magic"], "sym": e["sym"],
                    "lot": e["lot"], "pnl": e["pnl"] + sum(o["pnl"] for o in os_),
                    "exit_dt": os_[-1]["dt"], "open": False})
    rts.sort(key=lambda r: r["t"])
    return rts


def mark_dups(rts, s4):
    for r in rts:
        r["dup"] = False
    if not s4:
        return rts
    s4s, s4e = s4
    for i, r in enumerate(rts):
        if r["dup"]:
            continue
        for j in range(i + 1, len(rts)):
            s = rts[j]
            if (s["magic"] == r["magic"] and s["sym"] == r["sym"] and not s["dup"]
                    and abs(s["t"] - r["t"]) <= 60 and s["lot"] == r["lot"]
                    and s4s <= s["t"] < s4e):
                s["dup"] = True
    return rts


def report(label, rts):
    print("=" * 100)
    print(label)
    print("%-19s %-11s %-7s %5s %9s %6s %s" % ("entry(srv)", "sleeve", "sym", "lot", "pnl", "dup", "exit(srv)"))
    for r in rts:
        nm = NAMES.get(r["magic"], str(r["magic"]))
        print("%-19s %-11s %-7s %5.2f %9.0f %6s %s"
              % (r["dt"], nm, r["sym"], r["lot"], r["pnl"], "DUP" if r["dup"] else "", r["exit_dt"]))
    agg = defaultdict(lambda: [0, 0.0, 0, 0.0])
    for r in rts:
        if r["open"]:
            continue
        nm = NAMES.get(r["magic"], str(r["magic"]))
        agg[nm][0] += 1
        agg[nm][1] += r["pnl"]
        if not r["dup"]:
            agg[nm][2] += 1
            agg[nm][3] += r["pnl"]
    print("-" * 100)
    print("%-11s %14s %20s" % ("sleeve", "raw(n/pnl)", "design-adj(n/pnl)"))
    tr = tp = ta = tap = 0
    for nm in sorted(agg):
        n, p, na, pa = agg[nm]
        tr += n; tp += p; ta += na; tap += pa
        print("%-11s %5d /%8.0f %10d /%8.0f" % (nm, n, p, na, pa))
    print("%-11s %5d /%8.0f %10d /%8.0f" % ("TOTAL", tr, tp, ta, tap))
    for r in rts:
        if r["open"]:
            print("open: %s %s entry=%s lot=%.2f" % (NAMES.get(r["magic"], r["magic"]), r["sym"], r["dt"], r["lot"]))


if __name__ == "__main__":
    args = sys.argv[1:]
    s4 = None
    if "--s4" in args:
        k = args.index("--s4")
        a, b = args[k + 1].split(",")
        s4 = (ep(a), ep(b))
        args = args[:k] + args[k + 2:]
    path = args[0]
    label = args[1] if len(args) > 1 else path
    report(label, mark_dups(load(path), s4))
