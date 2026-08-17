# -*- coding: utf-8 -*-
"""並列実行下で測られた行を破棄する。

2026-08-17 22:44〜22:48 にドライバが2つ走った区間があり、GDD44_11/IS と
GDD44_13/IS がその下で測られた。mt5btの並列実行は結果を壊すため（過去に
誤ったFAIL判定を生んだ実績がある）、成功扱いでも信用せず破棄して測り直す。
"""
import csv
import shutil
from pathlib import Path

P = Path(__file__).resolve().parent / "results.csv"
BAD = {("GDD44_11", "IS"), ("GDD44_13", "IS")}

shutil.copy(P, P.with_suffix(".csv.bak"))
rows = list(csv.DictReader(open(P, encoding="utf-8-sig")))
keep = [r for r in rows if (r["proposal_id"], r["window"]) not in BAD]
with open(P, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(keep)
print("破棄 %d 行 / 残り %d 行（バックアップ: %s）"
      % (len(rows) - len(keep), len(keep), P.with_suffix(".csv.bak").name))
