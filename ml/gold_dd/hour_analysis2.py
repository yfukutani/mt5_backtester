# -*- coding: utf-8 -*-
"""GOLD枠の「エントリー時刻」基準で曜日・セッション別の損益を診断する。

前版(hour_analysis.py)の問題を2点修正した:
  1. 決済時刻で集計していた。エントリーゲートとして実装するなら
     エントリー時刻に損益を帰属させる必要がある。position_idで突合する。
  2. 1時間刻みではPB GOLDが1セル1〜4件しかなく、統計的に無意味だった。
     セッション帯にまとめ、件数を必ず併記する。

これは原因診断であり採否判定ではない。候補はEAに実装して実バックテストで測る。
"""
import csv
import glob
import os
from collections import defaultdict
from datetime import datetime, timezone

COMMON = r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files"
PB_GOLD, SCA_GOLD = 20260640, 20261002
WD = ["月", "火", "水", "木", "金", "土", "日"]

# UTC時刻のセッション区分（XMサーバはGMT+2/+3だがdealのtimeはUTC epoch）
SESSIONS = [("東京 0-6h", range(0, 7)), ("欧州前場 7-11h", range(7, 12)),
            ("欧州後場/NY前 12-15h", range(12, 16)), ("NY 16-19h", range(16, 20)),
            ("NY後場/引け 20-23h", range(20, 24))]


def sess(h):
    for name, rng in SESSIONS:
        if h in rng:
            return name
    return "?"


def load_trades(path):
    """position_idでentry/exitを突合し、(magic, エントリー時刻, 損益)を返す。"""
    opens, closes = {}, defaultdict(float)
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                magic = int(float(row["magic"]))
                if magic not in (PB_GOLD, SCA_GOLD):
                    continue
                pid = row["position_id"]
                ent = int(float(row["entry"]))
                t = datetime.fromtimestamp(int(float(row["time"])), tz=timezone.utc)
                if ent == 0:
                    opens[pid] = (magic, t)
                else:
                    closes[pid] += float(row.get("profit_jpy") or row.get("profit") or 0)
            except (TypeError, ValueError, KeyError):
                continue
    return [(m, t, closes[p]) for p, (m, t) in opens.items() if p in closes]


def table(rows, keyfn, title, order=None):
    g = defaultdict(list)
    for t, p in rows:
        g[keyfn(t)].append(p)
    print("  --- %s ---" % title)
    print("  %-22s %5s %12s %9s %7s %11s" % ("区分", "件数", "合計", "平均", "勝率", "最大損失"))
    keys = order if order else sorted(g)
    for k in keys:
        v = g.get(k)
        if not v:
            continue
        wins = len([x for x in v if x > 0])
        warn = ""
        if len(v) < 20:
            warn = "  ※件数僅少"
        elif sum(v) < 0:
            warn = "  ←損失"
        print("  %-22s %5d %+12.0f %+9.0f %6.1f%% %+11.0f%s"
              % (k, len(v), sum(v), sum(v) / len(v), 100.0 * wins / len(v), min(v), warn))


def main():
    cands = sorted(glob.glob(os.path.join(COMMON, "*_deals.csv")),
                   key=os.path.getsize, reverse=True)
    for p in cands[:40]:
        tr = load_trades(p)
        if len(tr) < 100:
            continue
        print("\n######## %s (往復 %d件) ########" % (os.path.basename(p), len(tr)))
        for magic, name in ((PB_GOLD, "PB GOLD"), (SCA_GOLD, "SCA GOLD")):
            sub = [(t, x) for m, t, x in tr if m == magic]
            if not sub:
                continue
            print("\n=== %s : 往復%d件（エントリー時刻基準） ===" % (name, len(sub)))
            table(sub, lambda t: WD[t.weekday()], "曜日別",
                  order=[WD[i] for i in range(5)])
            table(sub, lambda t: sess(t.hour), "セッション別",
                  order=[n for n, _ in SESSIONS])
            for d in (0, 4):
                s2 = [(t, x) for t, x in sub if t.weekday() == d]
                if len(s2) >= 10:
                    table(s2, lambda t: sess(t.hour), "%s曜のセッション別" % WD[d],
                          order=[n for n, _ in SESSIONS])
        return 0
    print("GOLD枠を含む十分なdealログが見つかりません")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
