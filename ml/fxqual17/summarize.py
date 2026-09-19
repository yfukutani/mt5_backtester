# -*- coding: utf-8 -*-
"""`ml/fxqual17` の集計 — 幾何月利・残高DD・equity DD・**最小維持率**を両窓で出す。

⚠️ **単位の規約**（第29報で並行セッションと合意）:
**pt を主・純益% を括弧で併記する。** `results.csv` の `monthly_pct` 列は**単利**なので使わない
（例: `fxqual15` の `W005 OOS` は列 5.6163% / 幾何 2.594%）。

⚠️ **`R ≡ 最小維持率 ÷ 床`（床 = 10000/cap）は、倍率・枠構成・窓・端末に不変ではない。**
同じ構成でも窓をまたぐと 0.488（OOS）→ 0.608（IS）と動く。
**「同じブック・同じ窓で cap だけを振ったとき」にしか使えない。**

⚠️ **`samples == 0` は「安全」ではなく「測れていない」。** `NOT_MEASURED` と表示する。
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sys
import datetime

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
MONTHS = {"OOS": 55.0, "IS": 60.0, "FULL": 115.0}
DEPOSIT = 500000.0


def geo(net, window):
    return ((DEPOSIT + net) / DEPOSIT) ** (1.0 / MONTHS[window]) - 1.0


def cap_rows(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split(",")
        if p and p[0].startswith(("equity_dd_pct", "margin_level_")):
            out[p[0]] = p
    return out


def main():
    res = os.path.join(ROOT, "results.csv")
    if not os.path.exists(res):
        print("results.csv がまだありません")
        return
    rows = list(csv.DictReader(open(res, encoding="utf-8")))

    info = {}
    for f in glob.glob(os.path.join(ROOT, "run_deals", "*_cap.csv")):
        m = re.search(r"mc_(oos|is|full)_([A-Z]\d+)_", os.path.basename(f))
        if m:
            info[(m.group(2), m.group(1).upper())] = cap_rows(f)

    print("%-5s %-4s %4s %12s %9s %8s %8s %9s %7s %6s %s" %
          ("id", "win", "cap", "net", "幾何月利", "残高DD", "eqDD",
           "最小維持率", "<100%", "R", "谷の日"))
    for r in rows:
        w, pid = r["window"], r["proposal_id"]
        cap = int(r["cap"]) if r["cap"] else 0
        g = geo(float(r["net"]), w) * 100
        c = info.get((pid, w), {})
        eq = c.get("equity_dd_pct", [None] * 6)[5]
        ml = c.get("margin_level_min")
        src = c.get("margin_level_src")
        hist = c.get("margin_level_hist")
        samples = int(src[5]) if src and src[5].isdigit() else 0
        if samples == 0:
            mls, lt100, R, when = "NOT_MEAS", "-", "-", "-"
        else:
            v = float(ml[2])
            mls = "%.2f%%" % v
            lt100 = hist[5] if hist else "-"
            R = "%.3f" % (v / (10000.0 / cap)) if cap else "—"
            when = datetime.datetime.fromtimestamp(
                int(ml[3]), datetime.timezone.utc).strftime("%Y-%m-%d")
        print("%-5s %-4s %4d %12s %8.3f%% %7s%% %7s%% %9s %7s %6s %s" %
              (pid, w, cap, format(int(float(r["net"])), ","), g,
               r["dd_pct"], eq or "-", mls, lt100, R, when))

    print("\n⚠️ 幾何月利は自前計算（results.csv の monthly_pct は単利なので使わない）")
    print("⚠️ R = 最小維持率 ÷ 床（床 = 10000/cap）。**倍率・枠構成・窓・端末に不変ではない。**")
    print("⚠️ 最小維持率 < 100% の run は、OANDA なら切られている。")
    print("   **切られた時刻以降の損益・DD・月利は反実仮想として無効。**")


if __name__ == "__main__":
    main()
