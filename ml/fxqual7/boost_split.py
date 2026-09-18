"""SCA 2枠の損益を「リバーサル増し玉（RevBoost）の有無」で割る。

【なぜ要るか】
並行セッション（第18報側）が、`ml/fxqual4` の対照 W000 の約定ログを Boost の有無で
割った結果を共有してくれた:

| 枠 | 群 | OOS 件数 | OOS 純益 | IS 件数 | IS 純益 |
|---|---|---:|---:|---:|---:|
| SCA GBPJPY | plain (0.01) | 522 | **−15,585** | 462 | +4,281 |
| SCA GBPJPY | Boost (0.06) | 162 | **+57,804** | 159 | +69,492 |

**SCA GBPJPY の枠純益は、リバーサル群だけから出ている。**
建値ストップ（`ml/fxqual7`）は plain にも Boost にも同じく効くので、
**「Boost 群の伸びを建値で切ってしまう」と枠が壊れる**方向である。
したがって判定では、枠別の純益だけでなく**この2群に割って**見る。

【判別】
`RevBoost` はロットを整数倍にするだけなので、**建玉のロットで判別できる**
（`ScaBaseLot` は `useRisk=false` の固定 0.01 で、Boost は USDJPY 2.0倍・GBPJPY 6.0倍）:

| 枠 | plain | Boost |
|---|---|---|
| SCA USDJPY (20261000) | 0.01 | 0.02 |
| SCA GBPJPY (20261001) | 0.01 | 0.06 |

W000 の OOS で実測すると 0.01/0.02 が 210/56、0.01/0.06 が 462/159 で、
**この2値しか出ない**（cap は MarginCapPct=0 で無効・`GlobalLotMult=1`）。

⚠️ **ロットを動かす構成（`GlobalLotMult`≠1・`Mult_*`≠1・`MarginCapPct`>0・
`FxRiskMask` で SCA を risk%化）では、この判別は使えない。**
`ml/fxqual4`〜`fxqual7` はすべて固定サイジングなので成立する。
使う前に必ず「ロットが2値しか出ないこと」を確かめること（本スクリプトが警告を出す）。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

SLEEVES = {
    "20261000": ("SCA USDJPY", "0.01", "0.02"),
    "20261001": ("SCA GBPJPY", "0.01", "0.06"),
}


def split(path: Path):
    rows = list(csv.DictReader(path.open(encoding="utf-8", errors="ignore")))
    opened: dict[str, tuple[str, str]] = {}
    lots: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["entry"] == "0" and r["magic"] in SLEEVES:
            opened[r["position_id"]] = (r["magic"], r["volume"])
            lots[r["magic"]].add(r["volume"])
    agg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    for r in rows:
        if r["entry"] == "0":
            continue
        got = opened.get(r["position_id"])
        if got is None:
            continue
        magic, vol = got
        name, plain, boost = SLEEVES[magic]
        if vol == plain:
            grp = "plain"
        elif vol == boost:
            grp = "Boost"
        else:
            grp = f"?{vol}"
        cell = agg[(name, grp)]
        cell[0] += float(r["profit"])       # 口座通貨（円）。profit_jpy は別系列
        cell[1] += 1
    return agg, lots


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("usage: boost_split.py <deals.csv> [<deals.csv> ...]")
        return
    for p in paths:
        agg, lots = split(p)
        print(f"=== {p.name} ===")
        for magic, vs in sorted(lots.items()):
            if len(vs) > 2:
                print(f"  ⚠️ {SLEEVES[magic][0]}: ロットが3値以上 {sorted(vs)}"
                      f" — この判別は使えない（サイジングが固定でない）")
        print(f"{'枠':12}{'群':>8}{'純益':>12}{'件数':>7}")
        for key in sorted(agg):
            net, n = agg[key]
            print(f"{key[0]:12}{key[1]:>8}{net:>12,.0f}{n:>7}")


if __name__ == "__main__":
    main()
