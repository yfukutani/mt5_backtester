import csv, glob, os, datetime

D = r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual13\run_deals"
for pid in ("T000", "T001", "T004", "T008", "T010"):
    for win in ("is", "oos"):
        g = glob.glob(os.path.join(D, f"mc_{win}_{pid}_*_deals.csv"))
        if not g:
            continue
        rows = list(csv.DictReader(open(g[0], encoding="utf-8")))
        rows.sort(key=lambda r: (int(r["time"]), r["entry"]))
        bal = 500000.0
        peak = bal
        worst = 0.0
        when = None
        wbal = wpeak = 0.0
        for r in rows:
            bal += float(r["profit"])
            if bal > peak:
                peak = bal
            d = (peak - bal) / peak * 100
            if d > worst:
                worst = d
                when = int(r["time"])
                wbal, wpeak = bal, peak
        ts = datetime.datetime.utcfromtimestamp(when).strftime("%Y-%m-%d") if when else "-"
        print(f"{pid} {win.upper():4s} maxBalDD={worst:6.2f}%  at {ts}  "
              f"peak={wpeak:>12,.0f} -> {wbal:>12,.0f}")
