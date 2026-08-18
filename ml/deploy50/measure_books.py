# -*- coding: utf-8 -*-
"""総資金50万円の配分最適化のため、2口座の書を倍率別に実測する。

【方針】
基準ロットは0.01固定、リスク建て枠も RefCap=100,000 に対する固定サイズなので、
損益もDDも「入金額に依存しない円額」として出る。したがって
  DD% = DD円 / 入金額 ,  月利% = 純利益円 / 入金額 / 月数
で任意の配分を評価できる。ここでは倍率ごとの円額を実測しておき、
配分探索は別途行う。最終候補だけは実際の入金額で測り直して裏を取る。

【重要】倍率は整数のみ。基準0.01のため 1.5倍などは Clamp() で消える。
"""
import copy
import csv
import subprocess
import sys
import time
from pathlib import Path

import yaml

MT5BT = Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "deploy50"
WORK = ROOT / "configs"
OUT = ROOT / "books.csv"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")

# 評価期間: IS 5年。月数は 60。
FRM, TO, MONTHS = "2021.06.21", "2026.06.20", 60.0
# DD%を歪ませないよう十分大きな名目入金で測る（円額を取り出すのが目的）
NOMINAL = 5000000

MULTS = [1, 2, 3, 4, 5, 6]

# 口座の枠構成。OANDA=FX専用、XM=GOLD+暗号専用（分離運用の方針どおり）
BOOKS = {
    "OANDA_FX": {
        "mt5_path": r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe",
        "expert": "MIX_EA_OANDA",
        "mult_keys": ["Mult_PB_USDJPY", "Mult_PB_GBPJPY", "Mult_RSI_USDJPY",
                      "Mult_RSI_EURUSD", "Mult_RSI_GBPUSD", "Mult_PAIR",
                      "Mult_CARRY", "Mult_VBO", "Mult_SCA_USDJPY", "Mult_SCA_GBPJPY"],
        "params": {
            "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
            "En_PB_GOLD": False, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
            "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
            "En_SCA_GOLD": False, "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
            "En_ETH": False,
            "RefCap_PB_USDJPY": 100000, "RefCap_PB_GBPJPY": 100000, "RefCap_CARRY": 100000,
        },
    },
    "XM_CFD": {
        "mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
        "expert": "MIX_EA",
        "mult_keys": ["Mult_PB_GOLD", "Mult_SCA_GOLD", "Mult_ETH",
                      "Mult_BTC_FUND", "Mult_BFXREV"],
        "params": {
            "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
            "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
            "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
            "En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True,
            "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
            "FundUseWebRequest": False, "BfxUseWebRequest": False,
        },
    },
}


def wait_mt5():
    while True:
        r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True)
        if not any(p in r.stdout for p in ("terminal64.exe", "metatester64.exe")):
            return
        time.sleep(15)


def summary(run):
    f = REPO / "results" / run / "summary.csv"
    if not f.exists():
        return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "ddpct": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    rows = []
    for book, spec in BOOKS.items():
        for m in MULTS:
            run = "d50_%s_x%d" % (book, m)
            r = summary(run)
            if r is None:
                cfg = {
                    "mt5_path": spec["mt5_path"], "expert": spec["expert"],
                    "symbol": "USDJPY", "period": "M15",
                    "from_date": FRM, "to_date": TO,
                    "deposit": NOMINAL, "currency": "JPY", "leverage": 25,
                    "model": "open_prices",
                    "parameters": copy.deepcopy(spec["params"]),
                    "report_dir": "results", "report_name": run,
                }
                for k in spec["mult_keys"]:
                    cfg["parameters"][k] = float(m)
                cfg["parameters"]["ResultFileName"] = run + "_r.csv"
                cfg["parameters"]["EquityLogFile"] = run + "_deals.csv"
                path = WORK / (run + ".yaml")
                yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                wait_mt5()
                subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=5400,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                r = summary(run)
            if r is None:
                print("%-9s x%d FAIL" % (book, m), flush=True)
                rows.append({"book": book, "mult": m, "net": "", "pf": "",
                             "dd_yen": "", "n": ""})
                continue
            dd_yen = r["ddpct"] / 100.0 * NOMINAL
            rows.append({"book": book, "mult": m, "net": r["net"], "pf": r["pf"],
                         "dd_yen": dd_yen, "n": r["n"]})
            print("%-9s x%d net=%+12.0f円 pf=%.4f DD=%+11.0f円 n=%d"
                  % (book, m, r["net"], r["pf"], dd_yen, r["n"]), flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
