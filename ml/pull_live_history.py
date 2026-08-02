# -*- coding: utf-8 -*-
"""本番口座の約定履歴をread-onlyで取得（フォワード照合用・週次レポートと同一手法）。
発注・決済・変更系APIは一切呼ばない: initialize/account_info/positions_get/history_deals_get のみ。
使用後は terminal64 を必ずkillすること（残るとmt5btが無反応になる既知問題）。

usage: python ml/pull_live_history.py <terminal64.exe path> <out_prefix> [out_dir] [from YYYY-MM-DD] [to YYYY-MM-DD]
"""
import csv
import os
import sys
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

path = sys.argv[1]
prefix = sys.argv[2]
OUT_DIR = sys.argv[3] if len(sys.argv) > 3 else "fwd_out"
frm_s = sys.argv[4] if len(sys.argv) > 4 else "2026-07-01"
to_s = sys.argv[5] if len(sys.argv) > 5 else None
os.makedirs(OUT_DIR, exist_ok=True)


def ts(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def dtfmt(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


if not mt5.initialize(path=path):
    print("initialize FAILED:", mt5.last_error())
    sys.exit(1)

ai = mt5.account_info()
ti = mt5.terminal_info()
print("login=%s server=%s currency=%s" % (ai.login, ai.server, ai.currency))
print("balance=%.0f equity=%.0f credit=%.0f margin=%.0f" % (ai.balance, ai.equity, ai.credit, ai.margin))
print("connected=%s trade_allowed(term)=%s" % (ti.connected, ti.trade_allowed))

# 起動直後はローカルキャッシュしか返らないことがあるため、履歴同期を待つ:
# 件数が3回連続で安定し、かつ最新dealが(現在-7日)以降になる（または約120秒）まで再取得。
frm = ts(frm_s)
to = ts(to_s) if to_s else datetime.now(tz=timezone.utc)
target = to.timestamp() - 7 * 86400
deals, stable, prev = None, 0, -1
for _ in range(40):
    deals = mt5.history_deals_get(frm, to)
    n = 0 if deals is None else len(deals)
    latest = max([d.time for d in deals], default=0) if deals else 0
    stable = stable + 1 if n == prev else 0
    prev = n
    if stable >= 3 and latest >= target:
        break
    time.sleep(3)
print("deals fetched:", 0 if deals is None else len(deals),
      "latest:", dtfmt(max([d.time for d in deals], default=0)) if deals else "-")

dpath = os.path.join(OUT_DIR, prefix + "_deals.csv")
with open(dpath, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["ticket", "order", "position_id", "time_srv", "dt_srv", "type", "entry",
                "magic", "symbol", "volume", "price", "profit", "swap", "commission", "comment"])
    for d in (deals or []):
        w.writerow([d.ticket, d.order, d.position_id, d.time, dtfmt(d.time), d.type, d.entry,
                    d.magic, d.symbol, "%.2f" % d.volume, "%.5f" % d.price,
                    "%.2f" % d.profit, "%.2f" % d.swap, "%.2f" % d.commission, d.comment])
print("deals csv:", dpath)

pos = mt5.positions_get()
ppath = os.path.join(OUT_DIR, prefix + "_positions.csv")
with open(ppath, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["ticket", "time_srv", "dt_srv", "type", "magic", "symbol", "volume",
                "price_open", "price_cur", "sl", "tp", "swap", "profit", "comment"])
    for p in (pos or []):
        w.writerow([p.ticket, p.time, dtfmt(p.time), p.type, p.magic, p.symbol,
                    "%.2f" % p.volume, "%.5f" % p.price_open, "%.5f" % p.price_current,
                    "%.5f" % p.sl, "%.5f" % p.tp, "%.2f" % p.swap, "%.2f" % p.profit, p.comment])
print("positions: %d -> %s" % (0 if pos is None else len(pos), ppath))

mt5.shutdown()
print("done (remember to kill terminal64)")
