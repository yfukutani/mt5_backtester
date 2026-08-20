# -*- coding: utf-8 -*-
"""全期間(2016.11.09〜2026.06.20)でも2口座を測り、DD制約の根拠を固める。

IS期間のDDだけで倍率を決めると過剰適合になる。IS期間は相対的にDDが小さく
出るため、その上限まで倍率を上げるとOOSのような相場で30%を大きく超える。
倍率は「IS/全期間の悪い方のDD」で決める。

XM側は組合せ実測とIS実測の両方でHOLD64が優位だったため、HOLD64のみ測る。
IS実行で失敗したOANDA x2もここで回収する。
"""
import copy
import csv
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import (  # noqa: E402
    MT5BT, REPO, WORK, NOMINAL, OANDA_MULT_KEYS, XM_MULT_KEYS,
    OANDA_PARAMS, XM_PARAMS, XM_PATH, OANDA_PATH, XM_VARIANTS,
    build, summary, wait_mt5,
)

OUT = REPO / "ml" / "deploy50" / "books_full.csv"
# 暗号枠のETH履歴開始(2016.11.08)以降にする。これより前だと枠が無音で脱落する。
FRM, TO, MONTHS = "2016.11.09", "2026.06.20", 115.0
MULTS = [1, 2, 3, 4, 5]


def run_one(run, cfg):
    r = summary(run)
    if r is not None:
        return r
    path = WORK / (run + ".yaml")
    yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                   allow_unicode=True, sort_keys=False)
    wait_mt5()
    subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=7200,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return summary(run)


def main():
    rows = []
    jobs = []

    # ISで失敗したOANDA x2を回収
    jobs.append(("OANDA_FX", "IS", "-", 2,
                 "d50_oanda_x2",
                 build("d50_oanda_x2", OANDA_PATH, "MIX_EA_OANDA",
                       OANDA_PARAMS, OANDA_MULT_KEYS, 2)))

    for m in MULTS:
        run = "d50f_oanda_x%d" % m
        cfg = build(run, OANDA_PATH, "MIX_EA_OANDA", OANDA_PARAMS, OANDA_MULT_KEYS, m)
        cfg["from_date"], cfg["to_date"] = FRM, TO
        jobs.append(("OANDA_FX", "FULL", "-", m, run, cfg))

    for m in MULTS:
        run = "d50f_xm_hold64_x%d" % m
        cfg = build(run, XM_PATH, "MIX_EA_SIMVERIFY", XM_PARAMS, XM_MULT_KEYS, m,
                    extra=XM_VARIANTS["HOLD64"])
        cfg["from_date"], cfg["to_date"] = FRM, TO
        jobs.append(("XM_CFD", "FULL", "HOLD64", m, run, cfg))

    for book, window, variant, m, run, cfg in jobs:
        r = run_one(run, cfg)
        if r is None:
            print("%-9s %-5s %-7s x%d FAIL" % (book, window, variant, m), flush=True)
            continue
        dd_yen = r["ddpct"] / 100.0 * NOMINAL
        rows.append({"book": book, "window": window, "variant": variant, "mult": m,
                     "net": r["net"], "pf": r["pf"], "dd_yen": dd_yen, "n": r["n"]})
        print("%-9s %-5s %-7s x%d net=%+11.0f円 pf=%.4f DD=%10.0f円 n=%d"
              % (book, window, variant, m, r["net"], r["pf"], dd_yen, r["n"]), flush=True)
        if rows:
            with open(OUT, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
