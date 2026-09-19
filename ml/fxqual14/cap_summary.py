"""cap（証拠金上限）が各構成でどれだけ効いているかを一覧にする。

【なぜ要るか】
`V012`（倍率3・Carry あり）の OOS は、2点フィットの予測 4.373% を上回る 4.608% だった。
局所指数が 0.746 → 1.055 に上がる＝ **DD に対して収穫逓増**に見える。
並行セッションが cap ログで理由を示した: **倍率を上げるほど cap が左の尾を切る。**
つまり `V012` は「同じブックを倍率で伸ばした点」ではなく**別の系**であり、
**ここから先へ外挿すると、戦略ではなく cap の挙動を外挿することになる。**

この仮説には検証点がある:
**Carry は証拠金を長期に占有するので、Carry 抜きのほうが高い倍率まで cap に触らないはず。**
そうなら **cap が効き始める倍率が系列でずれ、曲率が上がり始める倍率も後ろにずれる。**
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = {20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
        20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "**pair**",
        20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj"}


def main():
    rows = defaultdict(lambda: {"calls": 0, "cut": 0, "deny": 0,
                                "want": 0.0, "got": 0.0, "by": {}})
    for f in sorted((ROOT / "run_deals").glob("*_cap.csv")):
        # mc_<win>_<pid>_<stamp>_<hex>_cap.csv
        parts = f.name.split("_")
        win, pid = parts[1].upper(), parts[2]
        a = rows[(pid, win)]
        for r in csv.DictReader(open(f, encoding="utf-8", errors="replace")):
            if r.get("kind") != "sleeve":
                continue
            a["calls"] += int(r["calls"])
            a["cut"] += int(r["cut"])
            a["deny"] += int(r["deny"])
            a["want"] += float(r["lot_want"])
            a["got"] += float(r["lot_got"])
            n = NAME.get(int(r["magic"]), r["magic"])
            if int(r["cut"]) or int(r["deny"]):
                a["by"][n] = (int(r["cut"]), int(r["deny"]))

    print(f"{'案':6} {'窓':4} {'発注判定':>8} {'cut':>6} {'deny':>6} "
          f"{'通過率':>7}  削られた枠（cut/deny）")
    for (pid, win) in sorted(rows):
        a = rows[(pid, win)]
        pr = 100.0 * a["got"] / a["want"] if a["want"] else 100.0
        by = " ".join(f"{k}:{c}/{d}" for k, (c, d) in
                      sorted(a["by"].items(), key=lambda x: -x[1][0]))
        print(f"{pid:6} {win:4} {a['calls']:8d} {a['cut']:6d} {a['deny']:6d} "
              f"{pr:6.1f}%  {by}")


if __name__ == "__main__":
    main()
