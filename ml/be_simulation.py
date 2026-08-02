# -*- coding: utf-8 -*-
"""フォワード実トレードに対する「利益保護ルール」の経路シミュレーション。

MFE/MAEだけでは「含み益に達した後で建値に戻ったのか、戻る前に伸びたのか」が分からない。
M1バーを時系列順に歩いて、以下を各トレードで判定する:
  - +XR に到達したか / その到達後に建値へ戻ったか（=BEストップが発動するか）
  - BE発動時の損益（0円）と実際の損益の差 = そのルールの損得

ルール:
  BE@X   : MFE>=X*R でSLを建値へ。以後、建値に触れたら0円決済
  TRAIL@K: MFE>=1R 到達後、ピークから K*R 逆行で決済（部分的な利益確定）
出力: ルール別の合計損益（実績比）と、救済/毀損したトレードの明細。

usage: python be_simulation.py <terminal64.exe> <label>
"""
import csv
import os
import sys
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

OUT = r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\fwd"
NAMES = {
    20260605: "RSI_EURUSD", 20260610: "RSI_USDJPY", 20260774: "RSI_GBPUSD",
    20260622: "PB_USDJPY", 20260625: "PB_GBPJPY", 20260640: "PB_GOLD",
    20260629: "PAIR", 20260650: "CARRY", 20260680: "VBO_USDJPY",
    20261000: "SCA_USDJPY", 20261001: "SCA_GBPJPY", 20261002: "SCA_GOLD",
}
path, label = sys.argv[1], sys.argv[2]
mt5.initialize(path=path)
frm = datetime(2026, 7, 1, tzinfo=timezone.utc)
to = datetime(2026, 8, 3, tzinfo=timezone.utc)
deals, stable, prev = None, 0, -1
for _ in range(40):
    deals = mt5.history_deals_get(frm, to)
    n = 0 if deals is None else len(deals)
    stable = stable + 1 if n == prev else 0
    prev = n
    if stable >= 3 and n > 0:
        break
    time.sleep(3)
orders = mt5.history_orders_get(frm, to) or []
sltp = {}
for o in orders:
    if o.position_id and (o.position_id not in sltp or (sltp[o.position_id][0] == 0 and o.sl)):
        sltp[o.position_id] = (o.sl, o.tp)

ins, outs = {}, {}
for d in (deals or []):
    if not (20260000 <= d.magic < 20270000):
        continue
    r = {"t": d.time, "magic": d.magic, "sym": d.symbol, "price": d.price,
         "pnl": d.profit + d.swap + d.commission, "type": d.type}
    if d.entry == 0:
        ins[d.position_id] = r
    else:
        outs.setdefault(d.position_id, []).append(r)

RULES = [("BE@0.5R", 0.5), ("BE@0.75R", 0.75), ("BE@1.0R", 1.0), ("BE@1.5R", 1.5)]
TRAILS = [("TRAIL@0.5R", 0.5), ("TRAIL@1.0R", 1.0)]
rows = []
for pid, e in sorted(ins.items(), key=lambda kv: kv[1]["t"]):
    if pid not in outs:
        continue
    x = outs[pid][-1]
    sl = sltp.get(pid, (0.0, 0.0))[0]
    if not sl:
        continue                      # PairTrade等（SL無し）は対象外
    is_buy = (e["type"] == 0)
    R = abs(e["price"] - sl)
    pnl = e["pnl"] + sum(o["pnl"] for o in outs[pid])
    final_dist = (x["price"] - e["price"]) if is_buy else (e["price"] - x["price"])
    yen_per_dist = pnl / final_dist if abs(final_dist) > 1e-12 else 0.0
    rates = mt5.copy_rates_range(e["sym"], mt5.TIMEFRAME_M1,
                                 datetime.fromtimestamp(e["t"], tz=timezone.utc),
                                 datetime.fromtimestamp(x["t"], tz=timezone.utc))
    if rates is None or len(rates) == 0:
        continue
    rec = {"sleeve": NAMES.get(e["magic"], str(e["magic"])), "sym": e["sym"],
           "entry_dt": datetime.fromtimestamp(e["t"], tz=timezone.utc).strftime("%m-%d %H:%M"),
           "actual": round(pnl)}
    # --- BEルール: 時系列に歩き、X*R到達後に建値タッチで0円決済 ---
    for name, trig in RULES:
        armed, sim = False, None
        for b in rates:
            fav = (b["high"] - e["price"]) if is_buy else (e["price"] - b["low"])
            adv = (b["low"] - e["price"]) if is_buy else (e["price"] - b["high"])
            if armed and adv <= 0:            # 建値に戻った
                sim = 0.0
                break
            if not armed and fav >= trig * R:
                armed = True
                # 同一バー内で建値に戻る可能性は保守的に無視（次バー以降で判定）
        rec[name] = round(sim if sim is not None else pnl)
    # --- トレーリング: 1R到達後、ピークからK*R逆行で決済 ---
    for name, k in TRAILS:
        peak, sim = 0.0, None
        for b in rates:
            fav = (b["high"] - e["price"]) if is_buy else (e["price"] - b["low"])
            adv_fav = (b["low"] - e["price"]) if is_buy else (e["price"] - b["high"])
            if peak >= 1.0 * R and adv_fav <= peak - k * R:
                sim = (peak - k * R) * yen_per_dist
                break
            peak = max(peak, fav)
        rec[name] = round(sim if sim is not None else pnl)
    rows.append(rec)

cols = ["sleeve", "sym", "entry_dt", "actual"] + [n for n, _ in RULES] + [n for n, _ in TRAILS]
with open(os.path.join(OUT, label + "_besim.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print("=== %s: 利益保護ルールの経路シミュレーション（n=%d・SL付き枠のみ）===" % (label, len(rows)))
base = sum(r["actual"] for r in rows)
print("%-11s %9s %9s %s" % ("rule", "合計", "実績差", "内訳（救済/毀損）"))
print("%-11s %9d %9s" % ("実績", base, "-"))
for name in [n for n, _ in RULES] + [n for n, _ in TRAILS]:
    tot = sum(r[name] for r in rows)
    saved = [r for r in rows if r[name] > r["actual"]]
    hurt = [r for r in rows if r[name] < r["actual"]]
    print("%-11s %9d %+9d  救済%d件(+%d) / 毀損%d件(%d)"
          % (name, tot, tot - base, len(saved), sum(r[name] - r["actual"] for r in saved),
             len(hurt), sum(r[name] - r["actual"] for r in hurt)))
print()
print("毀損されたトレード（BE@1.0R基準・利益保護が伸びを切った例）:")
for r in rows:
    if r["BE@1.0R"] < r["actual"]:
        print("  %-11s %s 実績%+6d → BE後%+6d" % (r["sleeve"], r["entry_dt"], r["actual"], r["BE@1.0R"]))
mt5.shutdown()
