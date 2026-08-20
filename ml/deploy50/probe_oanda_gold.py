# -*- coding: utf-8 -*-
"""OANDA端末でGOLD(XAUUSD)の長期バックテストが成立するかを先に確かめる。

【なぜ先に確かめるか】
過去に2度、履歴不足で枠が無音のまま脱落した結果を掴んだ。
  - ETHUSD: 履歴開始2016.11.08より前から走らせて枠ごと欠落
  - XAUJPY: 円建て口座の損益換算に必要な履歴が2025.09.17からしかない
どちらも「結果ファイルは出るが枠が消えている」ため、成績だけ見ると気づけない。
そこでdealに GOLD枠のmagic(PB=20260640 / SCA=20261002)が実際に現れることを
確認してから本測定に進む。
"""
import csv
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import (  # noqa: E402
    MT5BT, REPO, WORK, OANDA_PATH, wait_mt5, summary,
)

COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
PB_GOLD, SCA_GOLD = 20260640, 20261002

# 円建てとUSD建ての両方を試す。円建てが駄目ならUSD建て回避策を使う。
CASES = [
    ("JPY_FULL", "JPY", 500000, "2016.11.09", "2026.06.20"),
    ("USD_FULL", "USD", 3300,   "2016.11.09", "2026.06.20"),
    ("JPY_IS",   "JPY", 500000, "2021.06.21", "2026.06.20"),
]

PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": True,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "Mult_PB_GOLD": 1.0, "Mult_SCA_GOLD": 1.0,
}


def magics(run):
    f = COMMON / (run + "_deals.csv")
    if not f.exists():
        return "dealsファイル不在", 0, 0
    pb = sca = 0
    for row in csv.reader(open(f, encoding="utf-8-sig", errors="replace")):
        for c in row:
            try:
                v = int(float(c))
            except (TypeError, ValueError):
                continue
            if v == PB_GOLD:
                pb += 1
            elif v == SCA_GOLD:
                sca += 1
    if pb == 0 and sca == 0:
        return "両枠とも欠落", pb, sca
    if pb == 0:
        return "PB GOLD欠落", pb, sca
    if sca == 0:
        return "SCA GOLD欠落", pb, sca
    return "両枠あり", pb, sca


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    for label, cur, dep, frm, to in CASES:
        run = "oagold_probe_%s" % label.lower()
        r = summary(run)
        if r is None:
            cfg = {
                "mt5_path": OANDA_PATH, "expert": "MIX_EA_OANDA",
                "symbol": "XAUUSD", "period": "M15",
                "from_date": frm, "to_date": to,
                "deposit": dep, "currency": cur, "leverage": 25,
                "model": "every_tick",
                "parameters": dict(PARAMS, **{
                    "ResultFileName": run + "_r.csv",
                    "EquityLogFile": run + "_deals.csv",
                }),
                "report_dir": "results", "report_name": run,
            }
            path = WORK / (run + ".yaml")
            yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                           allow_unicode=True, sort_keys=False)
            wait_mt5()
            subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=7200,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            r = summary(run)
        note, pb, sca = magics(run)
        if r is None:
            print("%-9s %s 建て %s〜%s  → 実行失敗 | magic: %s"
                  % (label, cur, frm, to, note), flush=True)
        else:
            print("%-9s %s 建て %s〜%s  純利益%+11.0f PF%.4f DD%6.2f%% n=%d "
                  "| magic: %s (PB=%d, SCA=%d)"
                  % (label, cur, frm, to, r["net"], r["pf"], r["ddpct"], r["n"],
                     note, pb, sca), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
