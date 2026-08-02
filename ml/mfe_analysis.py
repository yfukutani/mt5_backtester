# -*- coding: utf-8 -*-
"""フォワード実トレードのMFE/MAE分析（read-only）。
「一時的に含み益だったのに大きな損で決済した」現象を R倍数（R = 実SL幅）で定量化する。

各ポジションについて:
  - entry/exit は history_deals_get、SL/TP は history_orders_get（建玉時の注文）から取得
  - M1レートで entry〜exit の価格経路を走査し MFE（最大含み益）/ MAE（最大含み損）を算出
  - R = |entry - SL|。MFE_R / 最終R / giveback(=MFE_R - 最終R) を出力

usage: python mfe_analysis.py <terminal64.exe> <out_prefix>
"""
import csv
import os
import sys
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

OUT_DIR = r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\fwd"
os.makedirs(OUT_DIR, exist_ok=True)

NAMES = {
    20260605: "RSI_EURUSD", 20260610: "RSI_USDJPY", 20260774: "RSI_GBPUSD",
    20260622: "PB_USDJPY", 20260625: "PB_GBPJPY", 20260640: "PB_GOLD",
    20260629: "PAIR", 20260650: "CARRY", 20260680: "VBO_USDJPY",
    20261000: "SCA_USDJPY", 20261001: "SCA_GBPJPY", 20261002: "SCA_GOLD",
    20260710: "ETH", 20260720: "BTC_FUND", 20260724: "BFXREV",
}

path, prefix = sys.argv[1], sys.argv[2]
if not mt5.initialize(path=path):
    print("initialize FAILED:", mt5.last_error())
    sys.exit(1)
print("login=%s server=%s" % (mt5.account_info().login, mt5.account_info().server))

frm = datetime(2026, 7, 1, tzinfo=timezone.utc)
to = datetime(2026, 8, 3, tzinfo=timezone.utc)

# 履歴同期待ち
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
print("deals=%d orders=%d" % (len(deals or []), len(orders)))

# position_id -> 建玉時のSL/TP（entry order。SL/TPが0のものは後段でexitから推定）
sltp = {}
for o in orders:
    pid = o.position_id
    if pid == 0:
        continue
    cur = sltp.get(pid)
    if cur is None or (cur[0] == 0.0 and o.sl != 0.0):
        sltp[pid] = (o.sl, o.tp)

ins, outs = {}, {}
for d in (deals or []):
    if not (20260000 <= d.magic < 20270000):
        continue
    rec = {"t": d.time, "magic": d.magic, "sym": d.symbol, "vol": d.volume,
           "price": d.price, "pnl": d.profit + d.swap + d.commission,
           "type": d.type, "comment": d.comment, "pid": d.position_id}
    if d.entry == 0:
        ins[d.position_id] = rec
    else:
        outs.setdefault(d.position_id, []).append(rec)

rows = []
for pid, e in sorted(ins.items(), key=lambda kv: kv[1]["t"]):
    os_ = outs.get(pid)
    if not os_:
        continue
    x = os_[-1]
    is_buy = (e["type"] == 0)
    sl, tp = sltp.get(pid, (0.0, 0.0))
    # SLが無い枠（PairTrade等）は exit がSL決済ならその距離、それも無ければ None
    r_dist = abs(e["price"] - sl) if sl else None

    rates = mt5.copy_rates_range(e["sym"], mt5.TIMEFRAME_M1,
                                 datetime.fromtimestamp(e["t"], tz=timezone.utc),
                                 datetime.fromtimestamp(x["t"], tz=timezone.utc))
    if rates is None or len(rates) == 0:
        mfe_p = mae_p = None
    else:
        hi = max(r["high"] for r in rates)
        lo = min(r["low"] for r in rates)
        mfe_p = (hi - e["price"]) if is_buy else (e["price"] - lo)
        mae_p = (e["price"] - lo) if is_buy else (hi - e["price"])
    final_p = (x["price"] - e["price"]) if is_buy else (e["price"] - x["price"])

    pnl = e["pnl"] + sum(o["pnl"] for o in os_)
    # 含み益の金額換算（最終損益とMFE価格幅の比から線形換算）
    mfe_money = None
    if mfe_p is not None and final_p not in (0.0, None) and abs(final_p) > 1e-9:
        mfe_money = pnl / final_p * mfe_p
    rows.append({
        "sleeve": NAMES.get(e["magic"], str(e["magic"])),
        "sym": e["sym"], "dir": "BUY" if is_buy else "SELL", "lot": e["vol"],
        "entry_dt": datetime.fromtimestamp(e["t"], tz=timezone.utc).strftime("%m-%d %H:%M"),
        "exit_dt": datetime.fromtimestamp(x["t"], tz=timezone.utc).strftime("%m-%d %H:%M"),
        "hold_h": round((x["t"] - e["t"]) / 3600.0, 1),
        "entry": e["price"], "exit": x["price"], "sl": sl, "tp": tp,
        "pnl": round(pnl),
        "mfe_R": (round(mfe_p / r_dist, 2) if (mfe_p is not None and r_dist) else None),
        "mae_R": (round(mae_p / r_dist, 2) if (mae_p is not None and r_dist) else None),
        "final_R": (round(final_p / r_dist, 2) if r_dist else None),
        "mfe_money": (round(mfe_money) if mfe_money is not None else None),
        "exit_kind": ("SL" if "sl" in (x["comment"] or "").lower()
                      else ("TP" if "tp" in (x["comment"] or "").lower() else "OTHER")),
    })

out = os.path.join(OUT_DIR, prefix + "_mfe.csv")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print()
print("%-11s %-7s %-4s %-11s %5s %6s %6s %6s %7s %6s %s"
      % ("sleeve", "sym", "dir", "entry", "hold", "MFE_R", "MAE_R", "endR", "pnl", "MFE円", "exit"))
for r in rows:
    print("%-11s %-7s %-4s %-11s %5.1f %6s %6s %6s %7d %6s %s"
          % (r["sleeve"], r["sym"], r["dir"], r["entry_dt"], r["hold_h"],
             r["mfe_R"], r["mae_R"], r["final_R"], r["pnl"],
             r["mfe_money"] if r["mfe_money"] is not None else "-", r["exit_kind"]))

# 「含み益→損切り」の集計
bad = [r for r in rows if r["pnl"] < 0 and r["mfe_R"] is not None]
print()
for thr in (0.3, 0.5, 1.0):
    hit = [r for r in bad if r["mfe_R"] >= thr]
    lost = sum(r["pnl"] for r in hit)
    gave = sum((r["mfe_money"] or 0) - r["pnl"] for r in hit)
    print("MFE>=%.1fR で最終マイナス: %d件 / 損失計 %+d円 / 吐き出し計 %d円"
          % (thr, len(hit), lost, gave))
print("out:", out)
mt5.shutdown()
