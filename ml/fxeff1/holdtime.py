# -*- coding: utf-8 -*-
"""保有時間ごとの損益と証拠金占有（A4「保有時間上限」の下準備）。

`occupancy.py` で「占有を削る道はロットを小さくするか保有時間を短くするかの2つだけ」
と分かった。ロット側（A2/A3）は fxeff1 の16案で測っている。ここは**時間側**を見る。

保有時間で建玉を分け、**その帯が証拠金日の何%を食い、いくら稼いだか**を出す。
長く持つ建玉が「稼ぐから長い」のか「負けているから切れない」のかで、
保有時間上限の見込みが逆になる。

**厳密ではない部分**: 上限で早く閉じれば決済価格が変わるので、純益は再現しない。
ここで分かるのは「どの帯に証拠金と損益が乗っているか」までである。
"""
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from margin_efficiency import NAME, positions  # noqa: E402

BASE = ROOT.parent / "fxwin1" / "run_deals"
IS_W = ["w7", "w8", "w9"]
OOS_W = ["w1", "w2", "w3"]

# 帯（日）。上限はその帯に含む。
EDGES = [(0, 0.25, "〜6h"), (0.25, 1, "6h〜1日"), (1, 2, "1〜2日"),
         (2, 5, "2〜5日"), (5, 10, "5〜10日"), (10, 30, "10〜30日"),
         (30, 1e9, "30日〜")]


def find(win, pid="X005"):
    hits = sorted(BASE.glob(f"mc_{win}_{pid}_*_deals.csv"))
    return hits[0] if hits else None


def band(days):
    for lo, hi, name in EDGES:
        if lo < days <= hi or (lo == 0 and days <= hi):
            return name
    return EDGES[-1][2]


def table(paths, magics, title):
    agg = defaultdict(lambda: {"n": 0, "profit": 0.0, "mdays": 0.0, "win": 0})
    for p in paths:
        for magic, margin, hold, profit, _ti, _to in positions(p):
            if magic not in magics:
                continue
            b = band(hold / 86400.0)
            a = agg[b]
            a["n"] += 1
            a["profit"] += profit
            a["mdays"] += margin * hold / 86400.0
            a["win"] += 1 if profit > 0 else 0
    tot_m = sum(a["mdays"] for a in agg.values()) or 1.0
    tot_p = sum(a["profit"] for a in agg.values())
    print("")
    print("### " + title)
    print("| 保有時間 | 件数 | 勝率 | 純益 | 純益の% | 証拠金日 | **証拠金日の%** | 効率 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for _lo, _hi, name in EDGES:
        if name not in agg:
            continue
        a = agg[name]
        e = a["profit"] / a["mdays"] if a["mdays"] > 0 else 0.0
        pp = a["profit"] / tot_p * 100 if tot_p else 0.0
        print("| {} | {} | {:.0f}% | {:,.0f} | {:+.0f}% | {:,.0f} | **{:.1f}%** | {:+.4f} |".format(
            name, a["n"], a["win"] / max(a["n"], 1) * 100, a["profit"], pp,
            a["mdays"], a["mdays"] / tot_m * 100, e))
    print("| **合計** | {} | | {:,.0f} | | {:,.0f} | | {:+.4f} |".format(
        sum(a["n"] for a in agg.values()), tot_p, tot_m, tot_p / tot_m if tot_m else 0))


def main():
    print("# 保有時間ごとの損益と証拠金占有（X005・1:25）")
    print("")
    print("長く持つ建玉は「稼ぐから長い」のか「切れないから長い」のか。")
    groups = [
        ({20260605}, "RSI EURUSD"),
        ({20260610}, "RSI USDJPY"),
        ({20260774}, "RSI GBPUSD"),
        (set(NAME), "全枠"),
    ]
    for wins, label in ((IS_W, "IS窓 W7+W8+W9"), (OOS_W, "OOS窓 W1+W2+W3")):
        paths = [p for p in (find(w) for w in wins) if p]
        print("")
        print("## " + label)
        for magics, name in groups:
            table(paths, magics, name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
