# -*- coding: utf-8 -*-
"""results/ 配下の summary.csv を走査して1本のCSVに集約する。

sweep_s1s3.py は各実行ごとに結果CSVを書き直すため、グループを分けて回すと
前の実行分が失われる。判定は常に results/ を正として本スクリプトで再集約する。

出力列: prefix, sleeve, window, variant, net, pf, dd, n, win
usage: python ml/collect_results.py [出力先csv]
"""
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else (REPO / "ml" / "s13_all_results.csv")

# S13[PREFIX]_<SLEEVE>_<WINDOW>_<VARIANT>
PAT = re.compile(r"^(S13[A-Z0-9]*)_([A-Z]+_[A-Z]+)_(IS|OOS)_(.+)$")
rows = []
for d in sorted((REPO / "results").iterdir()):
    if not d.is_dir():
        continue
    m = PAT.match(d.name)
    if not m:
        continue
    f = d / "summary.csv"
    if not f.exists():
        continue
    v = {}
    with open(f, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                v[row[0]] = row[1]
    try:
        rows.append({
            "prefix": m.group(1), "sleeve": m.group(2), "window": m.group(3),
            "variant": m.group(4),
            "net": float(v["純利益"]), "pf": float(v["プロフィットファクター"]),
            "dd": float(v["最大相対DD%"]), "n": int(v["総取引数"]), "win": float(v["勝率%"]),
        })
    except (KeyError, ValueError):
        continue

with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["prefix", "sleeve", "window", "variant",
                                       "net", "pf", "dd", "n", "win"])
    w.writeheader()
    w.writerows(rows)
print("collected %d results -> %s" % (len(rows), OUT))
