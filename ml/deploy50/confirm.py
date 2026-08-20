# -*- coding: utf-8 -*-
"""配分の最終候補を、実際の入金額で測り直して裏を取る。

books.csv / books_full.csv は名目500万での円額から換算した推定値。
入金額が変わるとDD%の分母(ピーク時資産)が変わるため、推定と実測はずれる。
採用判断は実測で行う。
"""
import copy
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

OUT = REPO / "ml" / "deploy50" / "confirm.csv"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20", 60.0),
           "FULL": ("2016.11.09", "2026.06.20", 115.0)}

# (ラベル, 口座, 入金, 倍率)
PLANS = [
    ("A_XM単独x5",   "XM",    500000, 5),
    ("B_XM単独x4",   "XM",    500000, 4),
    ("C_分散_OANDA", "OANDA", 150000, 1),
    ("C_分散_XM",    "XM",    350000, 3),
]


def main():
    rows = []
    for label, book, deposit, mult in PLANS:
        for win, (frm, to, months) in WINDOWS.items():
            run = "d50c_%s_%s" % (label.lower().replace("単独", "").replace("分散_", ""), win.lower())
            r = summary(run)
            if r is None:
                if book == "OANDA":
                    cfg = build(run, OANDA_PATH, "MIX_EA_OANDA",
                                OANDA_PARAMS, OANDA_MULT_KEYS, mult)
                else:
                    cfg = build(run, XM_PATH, "MIX_EA_SIMVERIFY",
                                XM_PARAMS, XM_MULT_KEYS, mult,
                                extra=XM_VARIANTS["HOLD64"])
                cfg["deposit"] = deposit
                cfg["from_date"], cfg["to_date"] = frm, to
                path = WORK / (run + ".yaml")
                yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                wait_mt5()
                subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=7200,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                r = summary(run)
            if r is None:
                print("%-14s %-4s FAIL" % (label, win), flush=True)
                continue
            monthly = r["net"] / months / deposit * 100
            rf = r["net"] / (r["ddpct"] / 100.0 * deposit) if r["ddpct"] > 0 else 0
            rows.append({"plan": label, "book": book, "deposit": deposit, "mult": mult,
                         "window": win, "net": r["net"], "pf": r["pf"],
                         "dd_pct": r["ddpct"], "monthly_pct": monthly, "rf": rf,
                         "n": r["n"]})
            print("%-14s %-4s 入金%7d x%d 純利益%+10.0f PF%.4f DD%6.2f%% 月利%5.2f%% RF%5.2f n=%d"
                  % (label, win, deposit, mult, r["net"], r["pf"], r["ddpct"],
                     monthly, rf, r["n"]), flush=True)
            with open(OUT, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
