# -*- coding: utf-8 -*-
"""runの実行区間が重なっていないかを検査する。

mt5btの並列実行は結果を壊す（過去に誤ったFAIL判定を生んだ）。
再実行を2つ走らせた区間があるため、実測データの健全性を確認する。
"""
import csv
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "gold_dd2" / "results.csv"


def parse(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


spans = []
for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
    a, b = parse(r.get("started_at")), parse(r.get("finished_at"))
    if a and b and b >= a:
        spans.append((a, b, r["run_id"], r.get("proposal_id"), r.get("window")))

spans.sort()
overlaps = []
for i in range(1, len(spans)):
    pa, pb, prun, ppid, pwin = spans[i - 1]
    ca, cb, crun, cpid, cwin = spans[i]
    if ca < pb:   # 前のrunが終わる前に次が始まっている
        overlaps.append((ppid, pwin, pb, cpid, cwin, ca, (pb - ca).total_seconds()))

print("検査した run: %d" % len(spans))
if not overlaps:
    print("重なりなし。全runは直列に実行されている。")
else:
    print("⚠️重なり %d 件:" % len(overlaps))
    for ppid, pwin, pb, cpid, cwin, ca, sec in overlaps[:20]:
        print("  %s/%s の終了 %s と %s/%s の開始 %s が %.0f秒 重複"
              % (ppid, pwin, pb.isoformat(), cpid, cwin, ca.isoformat(), sec))
