# -*- coding: utf-8 -*-
"""OANDA 2口座構成（FX + CFD）を倍率別に実測する。

【背景】XMは海外FX業者のため長期運用に法規制上の懸念がある。GOLDをOANDA CFDへ
移した場合の性能を測り、XM構成と比較する。

【重要な差】MIX_EA_OANDAには暗号枠(ETH/BTC funding/BfxRev)が実装されていない。
したがってOANDA構成では暗号3枠の収益が丸ごと失われる。XM構成の高い資本効率は
GOLD2枠+暗号3枠の合計値なので、GOLD単体との比較で初めて優劣が分かる。

【検査】MIX_EA_OANDAのdealログはmagic列を持たないためmagic出現ゲートが使えない。
枠の生存は probe_oanda_split.py で別途確認済み(PB108+SCA522=両方630で一致)。
"""
import csv
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import (  # noqa: E402
    MT5BT, REPO, WORK, OANDA_MULT_KEYS, OANDA_PARAMS, OANDA_PATH,
    build, summary, wait_mt5,
)

OUT = REPO / "ml" / "deploy50" / "oanda_books.csv"
DEPOSIT = 500000
WINDOWS = {"IS": ("2021.06.21", "2026.06.20", 60.0),
           "FULL": ("2016.11.09", "2026.06.20", 115.0)}

# CFD口座(GOLD 2枠のみ)。採用済みの改善をすべて有効にする。
CFD_PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": True,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64,
}
CFD_MULT_KEYS = ["Mult_PB_GOLD", "Mult_SCA_GOLD"]

FX_MULTS = [1, 2, 3, 4]        # x5でIS DD36%と超過済みなのでx4まで
CFD_MULTS = [1, 3, 5, 8, 10, 12, 15]


def one(run, cfg):
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
    for m in CFD_MULTS:
        jobs.append(("OANDA_CFD", m))
    for m in FX_MULTS:
        jobs.append(("OANDA_FX", m))

    for book, m in jobs:
        for win, (frm, to, months) in WINDOWS.items():
            run = "oa2_%s_x%d_%s" % (book.lower().replace("oanda_", ""), m, win.lower())
            if book == "OANDA_CFD":
                cfg = build(run, OANDA_PATH, "MIX_EA_OANDA", CFD_PARAMS,
                            CFD_MULT_KEYS, m)
                cfg["symbol"] = "XAUUSD"
            else:
                cfg = build(run, OANDA_PATH, "MIX_EA_OANDA", OANDA_PARAMS,
                            OANDA_MULT_KEYS, m)
            cfg["deposit"] = DEPOSIT
            cfg["from_date"], cfg["to_date"] = frm, to
            r = one(run, cfg)
            if r is None:
                print("%-10s x%-2d %-4s FAIL" % (book, m, win), flush=True)
                continue
            monthly = r["net"] / months / DEPOSIT * 100
            rf = r["net"] / (r["ddpct"] / 100.0 * DEPOSIT) if r["ddpct"] > 0 else 0
            over = " ←DD30%超" if r["ddpct"] > 30.0 else ""
            rows.append({"book": book, "mult": m, "window": win, "net": r["net"],
                         "pf": r["pf"], "dd_pct": r["ddpct"], "monthly_pct": monthly,
                         "rf": rf, "n": r["n"]})
            print("%-10s x%-2d %-4s 純利益%+11.0f PF%.4f DD%6.2f%% 月利%6.2f%% RF%6.1f n=%d%s"
                  % (book, m, win, r["net"], r["pf"], r["ddpct"], monthly, rf,
                     r["n"], over), flush=True)
            with open(OUT, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
