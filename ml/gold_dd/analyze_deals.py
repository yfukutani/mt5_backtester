from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "round6_phase3" / "deals"
OUT = REPO / "ml" / "gold_dd"


def load(name: str):
    rows = []
    with (SRC / name).open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            p = float(r["profit_jpy"])
            rows.append({**r, "time_i": int(r["time"]), "p": p})
    return sorted(rows, key=lambda x: x["time_i"])


def dd_stats(rows, deposit=100000.0):
    bal = peak = deposit
    peak_t = rows[0]["time_i"] if rows else 0
    worst = {"amount": 0.0, "pct": 0.0, "peak_time": 0, "trough_time": 0,
             "peak_balance": deposit, "trough_balance": deposit}
    for r in rows:
        bal += r["p"]
        if bal > peak:
            peak, peak_t = bal, r["time_i"]
        amount = peak - bal
        pct = amount / peak * 100 if peak else 0
        if amount > worst["amount"]:
            worst = {"amount": amount, "pct": pct, "peak_time": peak_t,
                     "trough_time": r["time_i"], "peak_balance": peak,
                     "trough_balance": bal}
    for k in ("peak_time", "trough_time"):
        worst[k + "_iso"] = datetime.fromtimestamp(worst[k], timezone.utc).isoformat() if worst[k] else ""
    return worst


def period_breakdown(rows, start, end):
    chosen = [r for r in rows if start <= r["time_i"] <= end]
    by_magic = defaultdict(lambda: {"net": 0.0, "wins": 0.0, "losses": 0.0, "deals": 0})
    by_month = defaultdict(float)
    by_weekday = defaultdict(float)
    by_hour = defaultdict(float)
    for r in chosen:
        d = datetime.fromtimestamp(r["time_i"], timezone.utc)
        x = by_magic[r["magic"]]
        x["net"] += r["p"]; x["deals"] += 1
        x["wins" if r["p"] > 0 else "losses"] += r["p"]
        by_month[d.strftime("%Y-%m")] += r["p"]
        by_weekday[d.strftime("%a")] += r["p"]
        by_hour[str(d.hour)] += r["p"]
    losers = sorted(chosen, key=lambda r: r["p"])[:25]
    return {"deals": len(chosen), "net": sum(r["p"] for r in chosen),
            "by_magic": dict(by_magic), "by_month": dict(sorted(by_month.items())),
            "by_weekday": dict(by_weekday), "by_hour": dict(sorted(by_hour.items(), key=lambda x: int(x[0]))),
            "worst_deals": losers}


def overlap_stats(rows):
    """Reconstruct position intervals and count PB/SCA simultaneous exposure/loss days."""
    opened = {}
    intervals = defaultdict(list)
    exits = defaultdict(list)
    for r in rows:
        key = (r["magic"], r["position_id"])
        if int(r["entry"]) == 0:
            opened[key] = r["time_i"]
        elif int(r["entry"]) == 1:
            st = opened.pop(key, r["time_i"])
            intervals[r["magic"]].append((st, r["time_i"], r["p"], r["position_id"]))
            exits[datetime.fromtimestamp(r["time_i"], timezone.utc).strftime("%Y-%m-%d")].append(r)
    pb, sca = intervals["20260640"], intervals["20261002"]
    pairs=[]
    for a in pb:
        for b in sca:
            seconds=max(0, min(a[1],b[1])-max(a[0],b[0]))
            if seconds: pairs.append({"pb_position":a[3],"sca_position":b[3],"seconds":seconds,
                                      "pb_pnl":a[2],"sca_pnl":b[2]})
    both_loss_days=[]
    for day, rs in exits.items():
        pm=sum(r["p"] for r in rs if r["magic"]=="20260640")
        sm=sum(r["p"] for r in rs if r["magic"]=="20261002")
        if pm<0 and sm<0: both_loss_days.append({"day":day,"pb":pm,"sca":sm,"total":pm+sm})
    return {"overlap_pairs":len(pairs),"overlap_hours":sum(x["seconds"] for x in pairs)/3600,
            "both_loss_days":sorted(both_loss_days,key=lambda x:x["total"]),
            "worst_overlap_pairs":sorted(pairs,key=lambda x:x["pb_pnl"]+x["sca_pnl"])[:20]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = {}
    for key, fn in {
        "gold2_full": "r6p3_decomp_full_gold2_deals.csv",
        "pb_full": "r6p3_decomp_full_pb_gold_deals.csv",
        "sca_full": "r6p3_decomp_full_sca_gold_deals.csv",
        "gold2_is": "r6p3_decomp_is_gold2_deals.csv",
        "gold2_oos": "r6p3_decomp_oos_gold2_deals.csv",
        "xm5_full": "r6p3_xm5_full_off_x1_deals.csv",
    }.items():
        rows = load(fn)
        dd = dd_stats(rows)
        result[key] = {"dd": dd, "max_dd_interval": period_breakdown(rows, dd["peak_time"], dd["trough_time"])}
        if key.startswith("gold2_"):
            result[key]["overlap"] = overlap_stats(rows)
    (OUT / "dd_source_analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v["dd"] for k, v in result.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
