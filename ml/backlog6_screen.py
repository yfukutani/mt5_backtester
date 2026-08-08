# -*- coding: utf-8 -*-
"""第6次バックログ（応答曲面・第2ラウンド）のスクリーニング。

第1ラウンドの教訓（単発全期間チャンピオンは偽の台地を作る）を反映し、
**最初からIS(2021-2026)/OOS(2016-2021)の2期間ゲートをopen_prices（高速）で適用**する。
両期間プラスの生存案のみtier2（every_tick・スプレッド実費込み）へ昇格する。
"""
import ast
import csv
import subprocess
import sys
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "backlog5" / "cfg6"
WORK.mkdir(parents=True, exist_ok=True)
CAND = REPO / "ml" / "backlog5" / "candidates6.csv"
OUT = REPO / "ml" / "backlog5" / "screen6_results.csv"
XM = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

sys.path.insert(0, str(REPO / "ml"))
from backlog5_screen import BASE_PARAMS  # noqa

WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}


def build_cfg(row, win):
    tmpl = row["template"]
    if tmpl not in BASE_PARAMS:
        return None
    p = dict(BASE_PARAMS[tmpl])
    override = ast.literal_eval(row["params"])
    override.pop("__cot_overlay__", None)   # 新データ項目は別スクリプトで扱う
    p.update(override)
    p["LotSize"] = float(row["lot"])
    name = "%s_%s" % (row["id"], win)
    p["ResultFileName"] = name + "_r.csv"
    cfg = {"mt5_path": XM, "expert": tmpl, "symbol": row["symbol"], "period": row["period"],
           "from_date": WINDOWS[win][0], "to_date": WINDOWS[win][1],
           "deposit": 100000, "currency": "JPY", "leverage": 25,
           "model": "open_prices", "parameters": p,
           "report_dir": "results", "report_name": name}
    path = WORK / (name + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    return path


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


def run_one(row, win):
    name = "%s_%s" % (row["id"], win)
    r = summary(name)
    if r is not None:
        return r
    path = build_cfg(row, win)
    if path is None:
        return None
    try:
        subprocess.run([MT5BT, "run", str(path)], cwd=str(REPO),
                       capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        pass
    r = summary(name)
    if r is None:
        subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
        time.sleep(2)
    return r


def main():
    rows = list(csv.DictReader(open(CAND, encoding="utf-8")))
    rows = [r for r in rows if not r["family"].startswith("新データ")]
    order = {"S": 0, "A": 1, "B": 2}
    rows.sort(key=lambda r: order.get(r["priority"], 9))

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(rows)
    rows = rows[:limit]

    out_rows = []
    if OUT.exists():
        out_rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
    done_ids = {r["id"] for r in out_rows}

    survivors, fails, t0 = [], [], time.time()
    for i, row in enumerate(rows, 1):
        rid = row["id"]
        if rid in done_ids:
            continue
        ri = run_one(row, "IS")
        ro = run_one(row, "OOS")
        if ri is None or ro is None:
            fails.append(rid)
            print("[%3d/%d] %-6s %-28s %-10s %-16s FAIL"
                  % (i, len(rows), rid, row["family"], row["symbol"], row["params"][:16]), flush=True)
            out_rows.append({**row, "is_net": "", "is_pf": "", "oos_net": "", "oos_pf": "",
                              "verdict": "FAIL"})
        else:
            ok = ri["net"] > 0 and ro["net"] > 0
            if ok:
                survivors.append(rid)
            print("[%3d/%d] %-6s %-28s %-10s IS=%+8.0f(pf%.2f) OOS=%+8.0f(pf%.2f) %s"
                  % (i, len(rows), rid, row["family"], row["symbol"],
                     ri["net"], ri["pf"], ro["net"], ro["pf"], "**両+**" if ok else ""), flush=True)
            out_rows.append({**row, "is_net": ri["net"], "is_pf": ri["pf"], "is_n": ri["n"],
                              "oos_net": ro["net"], "oos_pf": ro["pf"], "oos_n": ro["n"],
                              "verdict": "PASS" if ok else "reject"})
        fieldnames = list(row.keys()) + ["is_net", "is_pf", "is_n", "oos_net", "oos_pf", "oos_n", "verdict"]
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for rr in out_rows:
                w.writerow({k: rr.get(k, "") for k in fieldnames})

    print()
    print("TOTAL %.1f min  survivors=%d fails=%d" % ((time.time() - t0) / 60, len(survivors), len(fails)))
    print("survivors:", survivors)


if __name__ == "__main__":
    main()
