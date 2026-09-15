"""cap を横軸にして応答曲線を出す（1:25）。

判定に使うのは **完全にOOSに収まる W1〜W3 の中央値**。
通期OOS(55か月)も出すが、あれは**立ち上がりの1窓が作る**数字なので判定には使わない
（`docs/oanda_fx_windows_lev25_20260915.md`）。

X005（cap80%）は `ml/fxwin1/results.csv` にあるので、そこから取り込んで同じ表に並べる。
"""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FXWIN1 = ROOT.parent / "fxwin1" / "results.csv"
FXLEV25 = ROOT.parent / "fxlev25" / "results.csv"
DEPOSIT = 500000.0
TARGET = 6.0
MONTHS = {"W1": 24.0, "W2": 24.0, "W3": 24.0, "OOS": 55.0}
OOS_WINS = ("W1", "W2", "W3")


def monthly(net, window):
    final = DEPOSIT + net
    if final <= 0:
        return float("nan")
    return (math.pow(final / DEPOSIT, 1.0 / MONTHS[window]) - 1.0) * 100.0


def collect():
    """cap -> {window: row}"""
    out = {}
    res = ROOT / "results.csv"
    if res.exists():
        for r in csv.DictReader(open(res, encoding="utf-8")):
            if r.get("status") != "OK":
                continue
            out.setdefault(int(float(r["cap"])), {})[r["window"]] = r
    # cap80% は測り直さない。同じEA・同じ重み・同じ窓定義の既測を借りる——
    #   24か月窓(W1〜W3) は fxwin1 の X005
    #   通期OOS(55か月) は fxlev25 の V005
    if FXWIN1.exists():
        for r in csv.DictReader(open(FXWIN1, encoding="utf-8")):
            if r.get("status") == "OK" and r["proposal_id"] == "X005" \
                    and r["window"] in MONTHS:
                out.setdefault(80, {})[r["window"]] = r
    if FXLEV25.exists():
        for r in csv.DictReader(open(FXLEV25, encoding="utf-8")):
            if r.get("status") == "OK" and r["proposal_id"] == "V005" \
                    and r["window"] == "OOS":
                out.setdefault(80, {})["OOS"] = r
    return out


def main():
    data = collect()
    if not data:
        raise SystemExit("results.csv がありません")

    print("cap（使用証拠金/equity の上限%）の応答曲線 — レバレッジ 1:25・入金50万円")
    print("重みは X005 と同一（PB_UJ 0.5 / RSI_UJ 2 / RSI_EU 4 / RSI_GU 4 / "
          "Pair 4 / Carry 0.75 / SCA×2 4）\n")
    hdr = "  %-6s %9s %9s %9s %11s %9s %11s %9s %7s" % (
        "cap", "W1", "W2", "W3", "★OOS中央値", "最悪", "通期OOS", "通期DD", "取引")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    meds = {}
    for cap, w in data.items():
        if all(x in w for x in OOS_WINS):
            meds[cap] = statistics.median(
                [monthly(float(w[x]["net"]), x) for x in OOS_WINS])
    best = max(meds, key=lambda c: meds[c]) if meds else None

    for cap in sorted(data):
        w = data[cap]
        gs = {x: monthly(float(w[x]["net"]), x) for x in OOS_WINS if x in w}
        if len(gs) < 3:
            cells = " ".join(f"{gs.get(x, float('nan')):8.2f}%" for x in OOS_WINS)
            print(f"  {cap:>4}%  {cells}   （測定中 {len(gs)}/3窓）")
            continue
        vals = [gs[x] for x in OOS_WINS]
        med = statistics.median(vals)
        oos = w.get("OOS")
        full = (f"{monthly(float(oos['net']), 'OOS'):9.2f}%" if oos else "        -")
        dd = (f"{float(oos['dd_pct']):8.2f}%" if oos else "       -")
        tr = (oos.get("trades", "") if oos else "")
        star = " ←最良" if cap == best else ""
        print(f"  {cap:>4}%  {vals[0]:8.2f}% {vals[1]:8.2f}% {vals[2]:8.2f}%"
              f"  {med:9.2f}% {min(vals):8.2f}% {full} {dd} {tr:>7}{star}")
    print()
    print(f"  目標 {TARGET:.0f}% に対する判定は ★OOS中央値 の列で行う。")
    print("  通期OOSは立ち上がりの1窓が作る数字なので判定に使わない。")
    print()
    print("注意: cap=100% は「使用証拠金がequityと等しい」＝証拠金維持率100%であり、")
    print("      OANDA証券では**追証ライン**そのもの。バックテストで最良でも、")
    print("      実運用では一度でも逆行すれば追証になる水準である。")


if __name__ == "__main__":
    main()
