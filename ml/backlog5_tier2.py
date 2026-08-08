# -*- coding: utf-8 -*-
"""第5次バックログ tier2: 一次生存11案をIS/OOS(every_tick・スプレッド実費込み)で検証する。

ゲート: IS(2021.06.21-2026.06.20)/OOS(2016.06.21-2021.06.20) 両期間プラス。
"""
import csv
import subprocess
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "backlog5" / "tier2"
WORK.mkdir(parents=True, exist_ok=True)
XM = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

from backlog5_screen import BASE_PARAMS, TAG_OVERRIDES  # noqa

WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}

# 一次生存11案（screen_results.csvより）。id, family, template, symbol, period, tag, lot
SURVIVORS = [
    ("N017", "PullbackTrend", "GBPCHF", "H4", "std", "0.01"),
    ("N037", "PullbackTrend", "HK50Cash", "H4", "std", "1.0"),
    ("N040", "PullbackTrend", "JP225Cash", "H4", "std", "1.0"),
    ("N104", "VolBreakout", "HK50Cash", "H4", "std", "1.0"),
    ("N170", "RSI_Reversal", "EURJPY", "H4", "atrstop", "0.01"),
    ("N183", "RSI_Reversal", "EURNZD", "H4", "atrstop", "0.01"),
    ("N285", "PullbackTrend", "CADJPY", "H4", "rr25", "0.01"),
    ("N299", "PullbackTrend", "GBPCHF", "H4", "rr25", "0.01"),
    ("N340", "PullbackTrend", "GBPCHF", "H4", "noadx", "0.01"),
    ("N355", "RSI_Reversal", "EURNZD", "H4", "bb30", "0.01"),
    ("N382", "RSI_Reversal", "CORN-SEP26", "H4", "atrstop", "1.0"),
]


def run(rid, tmpl, symbol, period, tag, lot, win):
    name = "%s_%s" % (rid, win)
    p = dict(BASE_PARAMS[tmpl])
    p.update(TAG_OVERRIDES.get(tag, {}))
    p["LotSize"] = float(lot)
    p["ResultFileName"] = name + "_r.csv"
    cfg = {"mt5_path": XM, "expert": tmpl, "symbol": symbol, "period": period,
           "from_date": WINDOWS[win][0], "to_date": WINDOWS[win][1],
           "deposit": 100000, "currency": "JPY", "leverage": 25,
           "model": "every_tick", "parameters": p,
           "report_dir": "results", "report_name": name}
    path = WORK / (name + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    f = REPO / "results" / name / "summary.csv"
    if not f.exists():
        t0 = time.time()
        try:
            subprocess.run([MT5BT, "run", str(path)], cwd=str(REPO),
                           capture_output=True, text=True, timeout=2400)
        except subprocess.TimeoutExpired:
            pass
        if not f.exists():
            subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
            time.sleep(2)
            print("  %-20s FAIL (%.0fs)" % (name, time.time() - t0), flush=True)
            return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


results = {}
for rid, tmpl, symbol, period, tag, lot in SURVIVORS:
    for win in ("IS", "OOS"):
        r = run(rid, tmpl, symbol, period, tag, lot, win)
        results[(rid, win)] = r
        if r:
            print("%-6s %-18s %-9s %s  net=%+9.0f pf=%5.2f dd=%5.1f%% n=%4d"
                  % (rid, symbol, tag, win, r["net"], r["pf"], r["dd"], r["n"]), flush=True)

print()
print("=" * 90)
print("tier2 判定（IS/OOS every_tick 両期間プラス）")
for rid, tmpl, symbol, period, tag, lot in SURVIVORS:
    ri, ro = results.get((rid, "IS")), results.get((rid, "OOS"))
    if not (ri and ro):
        print("%-6s %-12s %-18s %-9s 実行不可" % (rid, tmpl, symbol, tag))
        continue
    ok = ri["net"] > 0 and ro["net"] > 0
    print("%-6s %-12s %-18s %-9s IS=%+8.0f(n%3d) OOS=%+8.0f(n%3d)  %s"
          % (rid, tmpl, symbol, tag, ri["net"], ri["n"], ro["net"], ro["n"],
             "**両期間+**" if ok else "不合格"))
