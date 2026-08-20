# -*- coding: utf-8 -*-
"""実際の入金額50万で、より高い倍率まで実測してDD30%の上限を見つける。

【前提の訂正】
名目500万でのDD%を円額に直して50万で割る換算は誤りだった。MT5の
「最大相対DD%」はピーク時資産に対する比率であり、50万に対し純利益が
数倍に達すると分母が入金額よりはるかに大きくなる。線形換算は成立しない。
よって実際の入金額で直接測る。
"""
import csv
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import (  # noqa: E402
    MT5BT, REPO, WORK, OANDA_MULT_KEYS, XM_MULT_KEYS,
    OANDA_PARAMS, XM_PARAMS, XM_PATH, OANDA_PATH, XM_VARIANTS,
    build, summary, wait_mt5,
)

OUT = REPO / "ml" / "deploy50" / "confirm_high.csv"
DEPOSIT = 500000
WINDOWS = {"IS": ("2021.06.21", "2026.06.20", 60.0),
           "FULL": ("2016.11.09", "2026.06.20", 115.0)}
XM_MULTS = [6, 8, 10, 12, 15]
OANDA_MULTS = [5, 8, 10]


def one(run, cfg, months):
    r = summary(run)
    if r is None:
        path = WORK / (run + ".yaml")
        yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                       allow_unicode=True, sort_keys=False)
        wait_mt5()
        subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=7200,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        r = summary(run)
    return r


def main():
    rows = []
    jobs = []
    for m in XM_MULTS:
        jobs.append(("XM", m))
    for m in OANDA_MULTS:
        jobs.append(("OANDA", m))

    for book, m in jobs:
        for win, (frm, to, months) in WINDOWS.items():
            run = "d50h_%s_x%d_%s" % (book.lower(), m, win.lower())
            if book == "XM":
                cfg = build(run, XM_PATH, "MIX_EA_SIMVERIFY", XM_PARAMS,
                            XM_MULT_KEYS, m, extra=XM_VARIANTS["HOLD64"])
            else:
                cfg = build(run, OANDA_PATH, "MIX_EA_OANDA", OANDA_PARAMS,
                            OANDA_MULT_KEYS, m)
            cfg["deposit"] = DEPOSIT
            cfg["from_date"], cfg["to_date"] = frm, to
            r = one(run, cfg, months)
            if r is None:
                print("%-6s x%-2d %-4s FAIL" % (book, m, win), flush=True)
                continue
            monthly = r["net"] / months / DEPOSIT * 100
            rf = r["net"] / (r["ddpct"] / 100.0 * DEPOSIT) if r["ddpct"] > 0 else 0
            over = " ←DD30%超" if r["ddpct"] > 30.0 else ""
            rows.append({"book": book, "mult": m, "window": win, "net": r["net"],
                         "pf": r["pf"], "dd_pct": r["ddpct"], "monthly_pct": monthly,
                         "rf": rf, "n": r["n"]})
            print("%-6s x%-2d %-4s 純利益%+11.0f PF%.4f DD%6.2f%% 月利%6.2f%% RF%6.2f n=%d%s"
                  % (book, m, win, r["net"], r["pf"], r["ddpct"], monthly, rf,
                     r["n"], over), flush=True)
            if rows:
                with open(OUT, "w", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
