# -*- coding: utf-8 -*-
"""results.csv の整合性を検査する。

稼働中のドライバが追記しているファイルを私が書き換えたため、
ヘッダ重複・行の欠落・重複attempt_idが起きていないかを確認する。
"""
import csv
from collections import Counter
from pathlib import Path

P = Path(__file__).resolve().parent / "results.csv"
BAK = P.with_suffix(".csv.bak")

raw = open(P, encoding="utf-8-sig").read().splitlines()
print("物理行数: %d" % len(raw))
hdr = [i for i, l in enumerate(raw) if l.startswith("attempt_id,")]
print("ヘッダ行の位置: %s" % hdr)

rows = list(csv.DictReader(open(P, encoding="utf-8-sig")))
print("パースできた行: %d" % len(rows))

ids = Counter(r.get("attempt_id") for r in rows)
dup = {k: v for k, v in ids.items() if v > 1 and k}
print("重複attempt_id: %d件 %s" % (len(dup), list(dup.items())[:5]))

blank = [r for r in rows if not r.get("proposal_id")]
print("proposal_id空の行: %d" % len(blank))

if BAK.exists():
    bak = list(csv.DictReader(open(BAK, encoding="utf-8-sig")))
    bids = {r.get("attempt_id") for r in bak}
    cids = {r.get("attempt_id") for r in rows}
    lost = bids - cids
    # 意図的に破棄した2件ぶんは除く
    lost_real = [a for a in lost
                 if not any(r.get("attempt_id") == a and
                            (r.get("proposal_id"), r.get("window")) in
                            {("GDD44_11", "IS"), ("GDD44_13", "IS")} for r in bak)]
    print("バックアップにあって現在無い行: %d（うち意図的破棄以外: %d）"
          % (len(lost), len(lost_real)))
    if lost_real:
        print("  → 失われた行: %s" % lost_real[:10])

# 案×windowごとに成功行があるか
ok = {(r["proposal_id"], r["window"]) for r in rows if r.get("status") == "OK"}
print("\n成功した案×window: %d" % len(ok))
props = {r["proposal_id"] for r in rows if r.get("proposal_id", "").startswith("GDD")}
print("登場した案: %d" % len(props))
noIS = sorted(p for p in props if (p, "IS") not in ok)
print("IS成功が無い案: %d件 %s" % (len(noIS), noIS[:12]))
