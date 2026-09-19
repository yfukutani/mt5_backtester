# -*- coding: utf-8 -*-
"""表3 — 最小維持率だけを横断で並べる（**月利は載せない**）。

【なぜ月利を載せないか】
月利は**端末をまたいで比較できない**（XM と OANDA でフィード差が約 27%）し、
**窓をまたいでも比較できない**（同じブックで OOS と IS が 1.8倍違う）。
**同じ表に並べた時点で、読む人は引き算する。** だから構造で防ぐ。

**維持率は端末のロスカット水準に依存しない量**なので、**ここだけは横断して並べてよい。**
この表が答えるのは **「どの道なら維持率 100% を超えるか」**の一点である。
**「どの道が安いか」は各端末の表（表1＝XM / 表2＝OANDA）の中でしか言えない。**

⚠️ **100% を割った構成は、月利を論じる前に候補から落ちる。**
   切られた時刻 T 以降の損益・DD・月利は、すべて反実仮想として無効である。
⚠️ **`samples == 0` は「安全」ではなく「測れていない」。**

使い方:
    python ml/fxqual17/table3_margin.py ml/fxqual17 [ml/fxoanda4 ...]
"""
from __future__ import annotations

import csv
import datetime
import glob
import json
import os
import re
import sys

TERMINAL = {"fxqual": "XM", "fxoanda": "OANDA", "fxmargin": "XM", "fxrisk": "XM"}


def terminal_of(root):
    b = os.path.basename(os.path.normpath(root))
    for k, v in TERMINAL.items():
        if b.startswith(k):
            return v
    return "?"


def collect(root):
    out = []
    res = os.path.join(root, "results.csv")
    if not os.path.exists(res):
        return out
    params = {}
    for r in csv.DictReader(open(res, encoding="utf-8")):
        try:
            params[(r["proposal_id"], r["window"])] = json.loads(r["parameter_json"])
        except Exception:
            params[(r["proposal_id"], r["window"])] = {}
    for f in glob.glob(os.path.join(root, "run_deals", "*_cap.csv")):
        m = re.search(r"mc_(oos|is|full)_([A-Za-z0-9]+)_", os.path.basename(f))
        if not m:
            continue
        win, pid = m.group(1).upper(), m.group(2)
        rows = {}
        for line in open(f, encoding="utf-8"):
            p = line.rstrip("\n").split(",")
            if p and p[0].startswith("margin_level_"):
                rows[p[0]] = p
        src, mn, hist = (rows.get("margin_level_src"),
                         rows.get("margin_level_min"),
                         rows.get("margin_level_hist"))
        pr = params.get((pid, win), {})
        cap = pr.get("MarginCapPct", 0)
        mult = pr.get("GlobalLotMult", "?")
        carry = "無" if pr.get("En_CARRY") is False else "有"
        samples = int(src[5]) if src and len(src) > 5 and src[5].isdigit() else 0
        if samples == 0:
            out.append((terminal_of(root), os.path.basename(os.path.normpath(root)),
                        pid, win, mult, carry, cap, "-", "NOT_MEASURED", "-", "-", "-"))
            continue
        v = float(mn[2])
        floor = (10000.0 / cap) if cap else None
        out.append((
            terminal_of(root), os.path.basename(os.path.normpath(root)), pid, win,
            mult, carry, cap,
            ("%.0f%%" % floor) if floor else "—",
            "%.2f%%" % v,
            ("%.3f" % (v / floor)) if floor else "—",
            hist[5] if hist else "-",
            datetime.datetime.fromtimestamp(
                int(mn[3]), datetime.timezone.utc).strftime("%Y-%m-%d"),
        ))
    return out


def main():
    roots = sys.argv[1:] or [os.path.dirname(os.path.abspath(__file__))]
    rows = []
    for r in roots:
        rows += collect(r)
    rows.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    hdr = ("端末", "ラウンド", "run", "窓", "倍率", "Carry", "cap",
           "床", "最小維持率", "R", "<100%", "谷の日")
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for r in rows:
        alive = ("✅" if (r[8] != "NOT_MEASURED" and float(r[8].rstrip("%")) >= 100)
                 else ("❓" if r[8] == "NOT_MEASURED" else "❌"))
        print("| " + " | ".join(str(x) for x in r) + f" | {alive} |")
    print("\n⚠️ **月利は載せない。**端末で約27%・窓で1.8倍違うので、この表では比較できない。")
    print("⚠️ **❌ は OANDA なら切られている。**切られた時刻以降の損益・DD・月利は反実仮想。")
    print("⚠️ **❓（NOT_MEASURED）は「安全」ではなく「測れていない」。**")


if __name__ == "__main__":
    main()
