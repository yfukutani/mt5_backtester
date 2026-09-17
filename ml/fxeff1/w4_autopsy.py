# -*- coding: utf-8 -*-
"""W4（2019-11〜2021-11）が全構成で負ける理由を枠別・月別に見る。

第7報 §4 が残した宿題。X005・X006 は元本割れ、X001 は W2 もマイナスだった。
「構成を強くしても取れない局面」が何でできているのかを、既測の deal ログから見る。
MT5 は1回も回さない。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from margin_efficiency import NAME, positions, summarise  # noqa: E402

BASE = ROOT.parent / "fxwin1" / "run_deals"


def find(win, pid="X005"):
    hits = sorted(BASE.glob(f"mc_{win}_{pid}_*_deals.csv"))
    return hits[0] if hits else None


def monthly(path):
    """月ごとの決済損益（枠別）。"""
    out = defaultdict(lambda: defaultdict(float))
    for magic, _m, _h, profit, _ti, t_out in positions(path):
        d = datetime.fromtimestamp(t_out, tz=timezone.utc)
        out[f"{d.year}-{d.month:02d}"][magic] += profit
    return out


def main():
    print("# W4（2019-11〜2021-11）の解剖 — X005")
    print("")

    p4 = find("w4")
    if p4 is None:
        print("W4 の deals が見つからない", file=sys.stderr)
        return 1

    print("## 1. 枠別の損益（W4 と、前後の窓の比較）")
    print("")
    wins = ["w1", "w2", "w3", "w4", "w5"]
    aggs = {w: summarise(find(w)) for w in wins if find(w)}
    magics = sorted(NAME, key=lambda m: -aggs["w4"].get(m, {"profit": 0})["profit"])
    print("| 枠 | " + " | ".join(w.upper() for w in wins) + " |")
    print("|---|" + "---:|" * len(wins))
    for m in magics:
        cells = []
        for w in wins:
            a = aggs.get(w, {}).get(m)
            cells.append(f"{a['profit']:,.0f}" if a else "—")
        print(f"| {NAME[m]} | " + " | ".join(cells) + " |")
    tot = []
    for w in wins:
        tot.append(f"{sum(a['profit'] for a in aggs[w].values()):,.0f}" if w in aggs else "—")
    print("| **合計** | " + " | ".join(tot) + " |")

    print("")
    print("## 2. W4 の月別損益（上位の枠だけ）")
    print("")
    mon = monthly(p4)
    keys = sorted(mon)
    top = sorted(NAME, key=lambda m: -abs(sum(mon[k].get(m, 0) for k in keys)))[:5]
    print("| 月 | " + " | ".join(NAME[m] for m in top) + " | その他 | **合計** |")
    print("|---|" + "---:|" * (len(top) + 2))
    for k in keys:
        row = mon[k]
        other = sum(v for m, v in row.items() if m not in top)
        total = sum(row.values())
        cells = [f"{row.get(m, 0):,.0f}" for m in top]
        print(f"| {k} | " + " | ".join(cells) + f" | {other:,.0f} | **{total:,.0f}** |")

    print("")
    print("## 3. W4 の取引件数と平均損益（枠別）")
    print("")
    print("| 枠 | 件数 | 純益 | 平均 | 平均保有(日) | 証拠金日 | 効率 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    a4 = aggs["w4"]
    for m in sorted(a4, key=lambda m: a4[m]["profit"]):
        a = a4[m]
        n = max(a["n"], 1)
        e = a["profit"] / a["mdays"] if a["mdays"] > 0 else 0.0
        print(f"| {NAME[m]} | {a['n']} | {a['profit']:,.0f} | {a['profit']/n:,.0f} | "
              f"{a['hold']/n:.1f} | {a['mdays']:,.0f} | {e:+.4f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
