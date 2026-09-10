"""X2_HIGH_RISK の要件定義に載せる、枠ごとの実測値を出す。

deal ログから枠別に 純益 / 取引数 / 1取引あたりの平均・標準偏差 / t値 を出す。
t値は「優位がゼロである可能性を否定できるか」の目安（2.0以上が目安）。
magic=0（期間終了時の強制決済）は EA 由来でないため除外する。
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}

NAMES = {
    20260622: ("PB USDJPY", "H4 押し目トレンド"),
    20260627: ("PB GBPJPY", "H4 押し目トレンド"),
    20260610: ("RSI USDJPY", "H4 逆張り"),
    20260605: ("RSI EURUSD", "H1 逆張り"),
    20260774: ("RSI GBPUSD", "H4 逆張り"),
    20260629: ("Pair EU/GU", "H1 サヤ取り"),
    20260650: ("Carry AUDJPY", "D1 スワップ"),
    20261000: ("SCA USDJPY", "M15 レンジブレイク"),
    20261001: ("SCA GBPJPY", "M15 レンジブレイク"),
    20260640: ("PB GOLD", "H4 押し目トレンド"),
    20261002: ("SCA GOLD 第1", "M15 レンジブレイク 1-9時"),
    20261003: ("SCA GOLD 第2", "M15 レンジブレイク 13-15時"),
    20260710: ("ETH キャリー", "D1"),
    20260720: ("BTC funding", "D1 逆張り"),
    20260724: ("BfxRev", "D1 リバウンド"),
}


def by_sleeve(path):
    out = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0 or int(r["magic"]) == 0:
            continue
        out[int(r["magic"])].append(p)
    return out


def load():
    src = {}
    runs = {}
    for f in ("results.csv", "results_grid.csv"):
        p = FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                runs[r["window"]] = FX / "run_deals" / r["deals"]
    for w, p in runs.items():
        src[("fx", w)] = by_sleeve(p)
    for r in csv.DictReader(open(GOLD / "results.csv", encoding="utf-8")):
        if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
            src[("gold", r["window"])] = by_sleeve(GOLD / "run_deals" / r["deals"])
    return src


def stat(t):
    n = len(t)
    if n < 2:
        return n, sum(t), 0.0, 0.0, 0.0
    m = sum(t) / n
    v = sum((x - m) ** 2 for x in t) / (n - 1)
    sd = math.sqrt(v)
    se = sd / math.sqrt(n)
    return n, sum(t), m, sd, (m / se if se else 0.0)


def main():
    src = load()
    # 枠 -> 窓 -> 統計
    table = defaultdict(dict)
    for (book, win), d in src.items():
        for magic, t in d.items():
            table[magic][win] = stat(t)

    print("| 枠 | 種別 | 窓 | 取引数 | 純益(円) | 平均/取引 | 標準偏差 | t値 |")
    print("|---|---|---|---:|---:|---:|---:|---:|")
    for magic in NAMES:
        if magic not in table:
            continue
        name, kind = NAMES[magic]
        for win in ("IS", "OOS", "FULL"):
            if win not in table[magic]:
                continue
            n, s, m, sd, tv = table[magic][win]
            flag = "" if tv >= 2.0 else " ⚠"
            print(f"| {name} | {kind} | {win} | {n} | {s:,.0f} | {m:,.1f} | "
                  f"{sd:,.0f} | {tv:.2f}{flag} |")
    print()
    print("⚠ は t値 2.0 未満＝優位がゼロである可能性を否定できない。")


if __name__ == "__main__":
    main()
