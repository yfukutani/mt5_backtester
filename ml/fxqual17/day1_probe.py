import csv, glob, os, datetime, collections

D = r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual17\run_deals"
g = glob.glob(os.path.join(D, "mc_oos_M003_*_deals.csv"))
rows = list(csv.DictReader(open(g[0], encoding="utf-8")))
rows.sort(key=lambda r: (int(r["time"]), r["entry"]))

ML_T = 1478674423
print("最小維持率の時刻:",
      datetime.datetime.utcfromtimestamp(ML_T).strftime("%Y-%m-%d %H:%M UTC"))

# 最初の建玉（entry=0）を時刻順に
opens = [r for r in rows if r["entry"] == "0"]
print(f"\n--- 最初の10建玉（全 {len(opens)} 件）---")
NAME = {"20260622": "pb_uj", "20260627": "pb_gj", "20260610": "rsi_uj",
        "20260605": "rsi_eu", "20260774": "rsi_gu", "20260629": "PAIR",
        "20260650": "carry", "20261000": "sca_uj", "20261001": "sca_gj"}
for r in opens[:10]:
    t = datetime.datetime.utcfromtimestamp(int(r["time"])).strftime("%Y-%m-%d %H:%M")
    print(f"  {t}  {NAME.get(r['magic'], r['magic']):8s} vol={float(r['volume']):8.2f} "
          f"price={r['price']}")

# 最小維持率の時点で開いていた建玉
openpos = {}
for r in rows:
    if int(r["time"]) > ML_T:
        break
    if r["entry"] == "0":
        openpos[r["position_id"]] = r
    else:
        openpos.pop(r["position_id"], None)
print(f"\n--- 最小維持率の時点で開いていた建玉: {len(openpos)} 件 ---")
agg = collections.Counter()
for r in openpos.values():
    agg[NAME.get(r["magic"], r["magic"])] += float(r["volume"])
for k, v in agg.most_common():
    print(f"  {k:8s} 合計 {v:8.2f} ロット")

# その時点までの確定損益
realized = sum(float(r["profit"]) for r in rows if int(r["time"]) <= ML_T)
print(f"\n確定損益（その時点まで）: {realized:,.0f} 円 → 残高 {500000+realized:,.0f} 円")
print(f"報告された equity: 132,725 円 → **含み損 {500000+realized-132725:,.0f} 円**")
