import csv, glob, os, datetime, collections, statistics

D = r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual17\run_deals"
NAME = {"20260622": "pb_uj", "20260627": "pb_gj", "20260610": "rsi_uj",
        "20260605": "rsi_eu", "20260774": "rsi_gu", "20260629": "PAIR",
        "20260650": "carry", "20261000": "sca_uj", "20261001": "sca_gj"}


def load(pid, win="oos"):
    f = glob.glob(os.path.join(D, f"mc_{win}_{pid}_*_deals.csv"))[0]
    rows = list(csv.DictReader(open(f, encoding="utf-8")))
    rows.sort(key=lambda r: (int(r["time"]), r["entry"]))
    return rows


def concurrency(rows):
    """同時保有建玉数の推移と、保有時間の合計（枠別）"""
    openp, cur, peak = {}, 0, 0
    hold = collections.defaultdict(float)
    series = []
    for r in rows:
        if r["entry"] == "0":
            openp[r["position_id"]] = r
            cur += 1
            peak = max(peak, cur)
        else:
            o = openp.pop(r["position_id"], None)
            if o:
                cur -= 1
                hold[NAME.get(o["magic"], o["magic"])] += (
                    int(r["time"]) - int(o["time"])) / 86400.0
        series.append((int(r["time"]), cur))
    return peak, hold, series


for pid, lab in (("M007", "対照 W000"), ("M008", "合成 W005")):
    rows = load(pid)
    peak, hold, series = concurrency(rows)
    n_open = sum(1 for r in rows if r["entry"] == "0")
    print(f"=== {lab} ({pid}) OOS ===")
    print(f"  建玉 {n_open} 件 / 同時保有の最大 {peak} 件")
    print(f"  保有日数の合計: " +
          "  ".join(f"{k} {v:.0f}" for k, v in
                   sorted(hold.items(), key=lambda x: -x[1])[:5]))
    tot = sum(hold.values())
    print(f"  全枠の保有日数合計 {tot:.0f} 日")
