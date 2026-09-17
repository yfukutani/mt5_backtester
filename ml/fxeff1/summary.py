# -*- coding: utf-8 -*-
"""ラウンドの results.csv を、判定に使う形（OOS窓の中央値）で並べる。

判定は完全にOOSに収まる W1〜W3 の月利中央値で行う。
通期OOS(55か月)も出すが、第7報のとおり**立ち上がりの1窓が作る数字**なので
判定には使わない。DDは判定に使わないが必ず併記する（ユーザー指示）。

    使い方: python ml/fxeff1/summary.py [results.csv ...]
"""
import csv
import statistics
import sys
from pathlib import Path

DEPOSIT = 500000
MONTHS = {"W1": 24.0, "W2": 24.0, "W3": 24.0, "W4": 24.0, "W5": 24.0,
          "W6": 24.0, "W7": 24.0, "W8": 24.0, "W9": 19.0, "OOS": 55.0,
          "FULL": 115.0}


def monthly(net, months):
    v = (DEPOSIT + net) / DEPOSIT
    if v <= 0:
        return float("nan")
    return (v ** (1.0 / months) - 1.0) * 100.0


def load(paths):
    by = {}
    desc = {}
    for p in paths:
        if not Path(p).exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("status") != "OK":
                continue
            pid = r["proposal_id"]
            desc[pid] = r.get("description", "")
            by.setdefault(pid, {})[r["window"]] = (
                float(r["net"]), float(r["dd_pct"]), int(r["trades"]))
    return by, desc


def main():
    paths = sys.argv[1:] or [str(Path(__file__).resolve().parent / "results.csv")]
    by, desc = load(paths)
    if not by:
        print("結果がまだ無い")
        return 0

    print("| 案 | W1 | W2 | W3 | **中央値** | 平均 | 最悪 | 中央値の窓 | 通期OOS月利 | 通期OOS 純益 | 通期OOS 最大DD | 取引 | 説明 |")
    print("|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|")
    rows = []
    for pid, d in by.items():
        ws = [monthly(d[w][0], 24.0) for w in ("W1", "W2", "W3") if w in d]
        med = statistics.median(ws) if len(ws) == 3 else None
        oos = d.get("OOS")
        rows.append((med if med is not None else -99, pid, d, ws, med, oos))
    rows.sort(reverse=True)
    for _k, pid, d, ws, med, oos in rows:
        cells = ["{:.2f}%".format(monthly(d[w][0], 24.0)) if w in d else "—"
                 for w in ("W1", "W2", "W3")]
        mcell = "**{:.2f}%**".format(med) if med is not None else "—"
        acell = "{:.2f}%".format(statistics.fmean(ws)) if len(ws) == 3 else "—"
        wcell = "{:.2f}%".format(min(ws)) if len(ws) == 3 else "—"
        # 中央値がどの窓のものか。n=3 の中央値は「真ん中の1本」でしかないので、
        # 案によって別の窓が中央値になる。入れ替わっていたら中央値の比較は成立しない。
        if med is not None:
            names = ["W1", "W2", "W3"]
            mw = names[min(range(3), key=lambda k: abs(ws[k] - med))]
        else:
            mw = "—"
        if oos:
            ocell = "{:.2f}%".format(monthly(oos[0], 55.0))
            ncell = "{:,.0f}".format(oos[0])
            dcell = "{:.1f}%".format(oos[1])
            tcell = str(oos[2])
        else:
            ocell = ncell = dcell = tcell = "—"
        print("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            pid, cells[0], cells[1], cells[2], mcell, acell, wcell, mw,
            ocell, ncell, dcell, tcell, desc.get(pid, "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
