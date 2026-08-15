# -*- coding: utf-8 -*-
"""採用後の本番相当ベースラインで曜日別損益を測り直す。

先の診断(ml/gold_dd/hour_analysis2.py)は「最大のdealログ」を自動選択した結果、
GDD06_01(PB ATR SL 2.0→0.5)という*変更後の候補*のログを読んでいた。
ベースラインではないため曜日の傾向がずれていた。ここでは対象を明示指定する。
"""
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

COMMON = r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files"
PB_GOLD, SCA_GOLD = 20260640, 20261002
WD = ["月", "火", "水", "木", "金", "土", "日"]


def load(path):
    opens, closes = {}, defaultdict(float)
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                m = int(float(row["magic"]))
                if m not in (PB_GOLD, SCA_GOLD):
                    continue
                pid, ent = row["position_id"], int(float(row["entry"]))
                t = datetime.fromtimestamp(int(float(row["time"])), tz=timezone.utc)
                if ent == 0:
                    opens[pid] = (m, t)
                else:
                    closes[pid] += float(row.get("profit_jpy") or row.get("profit") or 0)
            except (TypeError, ValueError, KeyError):
                continue
    return [(m, t, closes[p]) for p, (m, t) in opens.items() if p in closes]


def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else "combo_BOTH_*_deals.csv"
    files = sorted(glob.glob(os.path.join(COMMON, pat)))
    if not files:
        print("該当ログなし: %s" % pat)
        return 1
    for path in files:
        tr = load(path)
        if not tr:
            continue
        print("\n######## %s (往復 %d件) ########" % (os.path.basename(path), len(tr)))
        for magic, name in ((PB_GOLD, "PB GOLD"), (SCA_GOLD, "SCA GOLD")):
            sub = [(t, p) for m, t, p in tr if m == magic]
            if not sub:
                continue
            g = defaultdict(list)
            for t, p in sub:
                g[t.weekday()].append(p)
            print("\n=== %s : 往復%d件（エントリー時刻基準） ===" % (name, len(sub)))
            print("曜日  件数        合計      平均    勝率")
            for d in range(7):
                v = g.get(d)
                if not v:
                    continue
                w = len([x for x in v if x > 0])
                print("%s   %4d %+11.0f %+9.0f  %5.1f%%"
                      % (WD[d], len(v), sum(v), sum(v) / len(v), 100.0 * w / len(v)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
