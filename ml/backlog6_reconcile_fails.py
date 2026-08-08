# -*- coding: utf-8 -*-
"""backlog6_screen.pyがFAIL判定した行のうち、実は結果ファイルが存在する（判定時の
タイミング競合で見落とされた）ケースを、MT5を再起動せず結果ファイルの再読み込みだけで
救済する。mt5btは一切呼ばない（実行中のbacklog6_screen.pyと衝突しないよう完全read-only）。
"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "ml" / "backlog5" / "screen6_results.csv"


def summary(name):
    f = REPO / "results" / name / "summary.csv"
    if not f.exists():
        return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
fixed = 0
for row in rows:
    if row.get("verdict") != "FAIL":
        continue
    rid = row["id"]
    ri = summary("%s_IS" % rid)
    ro = summary("%s_OOS" % rid)
    if ri is None or ro is None:
        continue
    ok = ri["net"] > 0 and ro["net"] > 0
    row["is_net"], row["is_pf"], row["is_n"] = ri["net"], ri["pf"], ri["n"]
    row["oos_net"], row["oos_pf"], row["oos_n"] = ro["net"], ro["pf"], ro["n"]
    row["verdict"] = "PASS" if ok else "reject"
    fixed += 1
    print("救済: %-6s %-28s %-10s IS=%+8.0f(pf%.2f) OOS=%+8.0f(pf%.2f) %s"
          % (rid, row["family"], row["symbol"], ri["net"], ri["pf"], ro["net"], ro["pf"],
             "**両+**" if ok else ""))

fieldnames = list(rows[0].keys())
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fieldnames})

print()
print("救済件数: %d" % fixed)
