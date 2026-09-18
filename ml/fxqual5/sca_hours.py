"""SCA 2枠の損益を「発注時刻（サーバー時刻）」で切り直す。

`docs/oanda_fx_last_axes_20260915.md` §1 の時間帯内訳は、**第16報の配賦修正より前**に
作られている（窓末の建玉の損益が枠別集計から丸ごと落ちていた時期）。
`ml/fxqual5` の X001 を測る前に、**同じ表が配賦修正後も再現するか**を確かめる。

やること:
  1. `position_id` から建玉時（entry=0）の magic を引いて枠を決める（第16報の修正）
  2. IN の deal の時刻から「発注時刻」を取る
  3. 枠 × 発注時刻 で損益（OUT 側の `profit_jpy` の合計）を積む

⚠️ **これはバックテストではない。** 「その注文が出なかったら何が起きたか」は分からない。
X001/X002 の**事前予想**を作るためだけに使う。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SLEEVES = {20261000: "SCA USDJPY", 20261001: "SCA GBPJPY"}


def load(path: Path):
    rows = list(csv.DictReader(path.open(encoding="utf-8", errors="ignore")))
    # position_id -> 建玉時の magic と時刻
    opened: dict[str, tuple[int, int]] = {}
    for r in rows:
        if r["entry"] == "0":
            opened[r["position_id"]] = (int(r["magic"]), int(r["time"]))
    agg: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0.0, 0])
    for r in rows:
        if r["entry"] == "0":
            continue
        pid = r["position_id"]
        if pid not in opened:
            continue
        magic, t0 = opened[pid]
        name = SLEEVES.get(magic)
        if name is None:
            continue
        hour = datetime.fromtimestamp(t0, tz=timezone.utc).hour
        cell = agg[(name, hour)]
        # 集計は `profit`（口座通貨＝円）で行う。`profit_jpy` は USDJPY を掛けた別系列で、
        # ml/fxmargin3/measure.py の枠別集計（`profit` を積む）と桁が合わない。
        cell[0] += float(r["profit"])
        cell[1] += 1
    return agg


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("usage: sca_hours.py <deals.csv> [<deals.csv> ...]")
        return
    for p in paths:
        agg = load(p)
        print(f"=== {p.name} ===")
        print(f"{'枠':12}{'発注時':>7}{'純益':>12}{'件数':>7}")
        for (name, hour) in sorted(agg):
            net, n = agg[(name, hour)]
            print(f"{name:12}{hour:>7}{net:>12,.0f}{n:>7}")
        for name in sorted({k[0] for k in agg}):
            net = sum(v[0] for k, v in agg.items() if k[0] == name)
            n = sum(v[1] for k, v in agg.items() if k[0] == name)
            print(f"{name:12}{'合計':>7}{net:>12,.0f}{n:>7}")


if __name__ == "__main__":
    main()
