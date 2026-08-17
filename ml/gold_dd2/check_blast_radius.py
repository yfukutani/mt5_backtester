# -*- coding: utf-8 -*-
"""並列実行が起きた時間帯に走ったrunを特定し、汚染範囲を確定する。

私がロックファイルを削除して2つ目のドライバを起動したため、
2026-08-17 22:44:00〜22:48:19 に重なりが発生した。
この区間に触れたrunの結果は信用できない。
"""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "gold_dd2" / "results.csv"

LO = datetime(2026, 8, 17, 22, 43, 0, tzinfo=timezone.utc)
HI = datetime(2026, 8, 17, 22, 49, 0, tzinfo=timezone.utc)


def parse(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


hits = []
for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
    a, b = parse(r.get("started_at")), parse(r.get("finished_at"))
    if a and b and a < HI and b > LO:
        hits.append(r)

print("並列区間(%s〜%s)に重なったrun: %d件\n" % (LO.time(), HI.time(), len(hits)))
for r in hits:
    print("  %-9s %-24s %-4s status=%-10s decision=%s"
          % (r["proposal_id"], r["family"], r["window"], r["status"], r["decision"]))

ok = [r for r in hits if r["status"] == "OK"]
print("\nうち成功(OK)扱い: %d件" % len(ok))
if ok:
    print("→ これらは並列下の測定なので破棄して測り直す必要がある:")
    for r in ok:
        print("   %s %s" % (r["proposal_id"], r["window"]))
else:
    print("→ すべてFAILEDで破棄済み。採用判断に使った数値への影響はない。")
