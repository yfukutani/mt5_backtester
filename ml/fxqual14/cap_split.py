"""cap の圧力から Pair を分離する。**Pair の cut/deny は発注ではない。**

🔴 **2026-09-19、こちらが1度まちがえた。記録として残す。**

`cap_summary.py` の生の集計では、倍率3 OOS の cut 2,191 / deny 1,705 のうち
**Pair が 1,959 / 1,678（89% / 98%）**を占める。これを見て
**「OOS 1,984円 / 30取引の枠が 1,678件の発注を吹き飛ばしている」と書いた。誤りである。**

**`ProcPair()` は毎評価バーで無条件に `Clamp()` を2回呼ぶ。**
`LotComplex(i,sym)` / `LotComplex(i,sec)` が EA 2905-2906行、
**発注の判定は 2935行**（`if(st==0 && lot>0.0 && lot2u>0.0 && zone_ok && turning_ok)`）。
**シグナルも保有も関係なく、先に Clamp が走る。**
裏付け: Pair の `calls` は 57,152 で、他の枠は 13〜271。**Pair の OOS 取引数は 30 である。**

**したがって Pair の cut/deny は「評価の回数」であって「潰された発注」ではない。**
（deny が実際に発注を潰すのは、その同じバーにシグナルが出ていた場合だけ。）

**教訓: 件数を読む前に、その件数の分母が何かを書く。**
`calls` は「発注機会」を名乗っていないが、cut/deny と並ぶとそう読めてしまう。
[[metric-invariance-discipline]] の親戚。

【正しい読み方】
**Pair を除いた cut/deny が、実際の発注に対する cap 圧力である。**
そして `V009`（Pair 抜き）で測るべきなのは総件数ではなく
**「Pair 以外の cut/deny が減るか」**である
（総件数は Pair を外せば定義上ほぼゼロになるので、何も検証できない）。
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAIR = 20260629
NAME = {20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
        20260605: "rsi_eu", 20260774: "rsi_gu", PAIR: "pair",
        20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj"}


def main():
    acc = defaultdict(lambda: {"pc": 0, "pd": 0, "oc": 0, "od": 0,
                               "calls_pair": 0, "by": {}})
    for f in sorted((ROOT / "run_deals").glob("*_cap.csv")):
        parts = f.name.split("_")
        win, pid = parts[1].upper(), parts[2]
        a = acc[(pid, win)]
        for r in csv.DictReader(open(f, encoding="utf-8", errors="replace")):
            if r.get("kind") != "sleeve":
                continue
            m, c, d = int(r["magic"]), int(r["cut"]), int(r["deny"])
            if m == PAIR:
                a["pc"] += c
                a["pd"] += d
                a["calls_pair"] += int(r["calls"])
                continue
            a["oc"] += c
            a["od"] += d
            if c or d:
                a["by"][NAME.get(m, str(m))] = (c, d)

    print("⚠️ Pair の cut/deny は『評価の回数』であって『潰された発注』ではない。")
    print("   実際の発注に対する cap 圧力は『Pair 以外』の列で読む。\n")
    print(f"{'案':6} {'窓':4} | {'Pair cut/deny(評価)':>20} | "
          f"{'Pair 以外 cut':>12} {'deny':>6} | 内訳")
    for (pid, win) in sorted(acc):
        a = acc[(pid, win)]
        sh = ""
        if a["oc"]:
            top = max(a["by"].items(), key=lambda x: x[1][0])
            sh = f"（最大 {top[0]} が {100*top[1][0]/a['oc']:.0f}%）"
        by = " ".join(f"{k}:{c}/{d}" for k, (c, d) in
                      sorted(a["by"].items(), key=lambda x: -x[1][0]))
        print(f"{pid:6} {win:4} | {a['pc']:9d}/{a['pd']:<9d} | "
              f"{a['oc']:12d} {a['od']:6d} | {by} {sh}")


if __name__ == "__main__":
    main()
