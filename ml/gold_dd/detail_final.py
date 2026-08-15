# -*- coding: utf-8 -*-
"""主要候補のパラメータ内容とXM5 DD分布を確認する。"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml" / "gold_dd" / "screen_results.csv"
PROP = REPO / "ml" / "gold_dd" / "proposals.csv"

KEY = ["GDD24_13", "GDD07_14", "GDD30_04", "GDD30_08", "GDD30_19", "GDD31_17", "GDD24_17"]

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig")) if r.get("status") == "OK"]

props = {}
for r in csv.DictReader(open(PROP, encoding="utf-8-sig")):
    pid = r.get("id") or r.get("proposal_id")
    if pid:
        props[pid] = r

print("===== 主要候補の中身 =====")
for pid in KEY:
    p = props.get(pid, {})
    par = ""
    for r in rows:
        if r["id"] == pid and r["parameter_json"]:
            par = r["parameter_json"]
            break
    print("\n[%s] family=%s" % (pid, p.get("family", "?")))
    for k in ("summary", "rationale", "variation"):
        if p.get(k):
            print("  %s: %s" % (k, p[k][:160]))
    if par:
        try:
            print("  params: %s" % json.dumps(json.loads(par), ensure_ascii=False))
        except Exception:
            print("  params: %s" % par[:200])

xm5 = []
for r in rows:
    if r["window"] != "XM5":
        continue
    try:
        xm5.append((float(r["dd_jpy"]), float(r["net_jpy"]), r["id"], r["family"]))
    except (TypeError, ValueError):
        pass
xm5.sort()
print("\n===== XM5 DD の低い順 上位10 (基準 35.67178 / 純利益 538,303) =====")
for dd, net, pid, fam in xm5[:10]:
    print("%-10s %-16s DD=%8.4f%%  net=%+10.0f  (DD差 %+7.4fpt / 利益差 %+9.0f)"
          % (pid, fam, dd, net, dd - 35.67178, net - 538302.83))
print("\nXM5実行数: %d / DD30%%以下: %d" % (len(xm5), len([1 for d, *_ in xm5 if d <= 30.0])))
