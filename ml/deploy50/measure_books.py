# -*- coding: utf-8 -*-
"""総資金50万円の配分最適化のため、2口座の書を倍率別・構成別に実測する。

【口座構成】分離運用の方針どおり
  OANDA_FX : FX枠のみ（GOLD・暗号OFF）。MIX_EA_OANDA。GoldLab機構の影響を受けない。
  XM_CFD   : GOLD+暗号のみ。MIX_EA_SIMVERIFY（GoldLab機構を入力で切替できる）。

【XM側は3構成を比較】組合せ実測でトレードオフが出たため、レバレッジ調整後の
月利で決着させる。
  OFF    : 現行本番相当
  HOLD64 : PB GOLD保有上限64バー（IS利益は最良）
  BOTH   : 上記＋ポートフォリオ損失後12時間クールダウン（DDは最良）

【換算】基準ロット0.01固定、リスク建て枠も RefCap=100,000 基準の固定サイズなので、
損益もDDも入金額に依存しない円額として出る。よって
  DD% = DD円 / 入金額 ,  月利% = 純利益円 / 入金額 / 月数
で任意の配分を評価できる。ただし最終候補は実際の入金額で測り直して裏を取る。

【倍率】整数のみ。基準0.01のため1.5倍などは Clamp() で消える。
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

FRM, TO, MONTHS = "2021.06.21", "2026.06.20", 60.0
NOMINAL = 5000000          # DD%を歪ませない名目入金。円額の取り出しが目的
MULTS = [1, 2, 3, 4, 5]

XM_VARIANTS = {
    "OFF":    {"GoldLabMode": 0,  "GoldLabMode2": 0},
    "HOLD64": {"GoldLabMode": 24, "GoldLabMode2": 0, "GoldLabPBHoldBars": 64},
    "BOTH":   {"GoldLabMode": 24, "GoldLabMode2": 3, "GoldLabPBHoldBars": 64,
               "GoldLabPortfolioCooldownHours": 12},
}

OANDA_MULT_KEYS = ["Mult_PB_USDJPY", "Mult_PB_GBPJPY", "Mult_RSI_USDJPY",
                   "Mult_RSI_EURUSD", "Mult_RSI_GBPUSD", "Mult_PAIR",
                   "Mult_CARRY", "Mult_SCA_USDJPY", "Mult_SCA_GBPJPY"]
XM_MULT_KEYS = ["Mult_PB_GOLD", "Mult_SCA_GOLD", "Mult_ETH",
                "Mult_BTC_FUND", "Mult_BFXREV"]

OANDA_PARAMS = {
    "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
    "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
    "En_SCA_GOLD": False, "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
    "En_ETH": False,
    "RefCap_PB_USDJPY": 100000, "RefCap_PB_GBPJPY": 100000, "RefCap_CARRY": 100000,
}
XM_PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True,
    "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0, "GoldDDMode": 0,
    "GoldHourGateMode": 1,       # 採用済みの時間帯ゲートを有効にする
    "GoldHourPBWeekMask1": 2,  "GoldHourPBStart1": 0,  "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
}

XM_PATH = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"
OANDA_PATH = r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"
WATCH = ("terminal64.exe", "metatester64.exe")


STALE_TESTER_SECONDS = 300


def wait_mt5():
    """MT5の空きを待つ。孤立した metatester64 は回収する。

    terminal64 が終了しても metatester64 だけが残り続けることがあり、
    単純に消滅を待つと無期限にブロックする（実際に12.5時間停止した）。
    terminal64 が不在で metatester64 だけが残っている状態が一定時間続いたら
    孤立と見なして停止する。terminal64 は実運用端末の可能性があるため触らない。
    """
    orphan_since = None
    while True:
        r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True)
        busy = [p for p in WATCH if p in r.stdout]
        if not busy:
            return
        if busy == ["metatester64.exe"]:
            now = time.monotonic()
            if orphan_since is None:
                orphan_since = now
            elif now - orphan_since >= STALE_TESTER_SECONDS:
                subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"],
                               capture_output=True, text=True)
                print("  孤立metatester64を回収しました", flush=True)
                orphan_since = None
                time.sleep(3)
        else:
            orphan_since = None
        time.sleep(10)


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


def build(run, mt5_path, expert, params, mult_keys, mult, extra=None):
    cfg = {
        "mt5_path": mt5_path, "expert": expert, "symbol": "USDJPY", "period": "M15",
        "from_date": FRM, "to_date": TO,
        "deposit": NOMINAL, "currency": "JPY", "leverage": 25,
        # every_tick必須。open_pricesだとEAが参照する下位・上位足の要求が
        # "wrong timeframe request in Open Prices testing mode" で弾かれ、
        # rates base receive error で全runが失敗する。本番configも every_tick。
        "model": "every_tick",
        "parameters": copy.deepcopy(params),
        "report_dir": "results", "report_name": run,
    }
    if extra:
        cfg["parameters"].update(extra)
    for k in mult_keys:
        cfg["parameters"][k] = float(mult)
    cfg["parameters"]["ResultFileName"] = run + "_r.csv"
    cfg["parameters"]["EquityLogFile"] = run + "_deals.csv"
    return cfg


def run_one(run, cfg):
    r = summary(run)
    if r is not None:
        return r
    path = WORK / (run + ".yaml")
    yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                   allow_unicode=True, sort_keys=False)
    wait_mt5()
    subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=5400,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return summary(run)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    rows = []
    jobs = []
    for m in MULTS:
        jobs.append(("OANDA_FX", "-", m,
                     build("d50_oanda_x%d" % m, OANDA_PATH, "MIX_EA_OANDA",
                           OANDA_PARAMS, OANDA_MULT_KEYS, m),
                     "d50_oanda_x%d" % m))
    for name, ov in XM_VARIANTS.items():
        for m in MULTS:
            run = "d50_xm_%s_x%d" % (name.lower(), m)
            jobs.append(("XM_CFD", name, m,
                         build(run, XM_PATH, "MIX_EA_SIMVERIFY",
                               XM_PARAMS, XM_MULT_KEYS, m, extra=ov),
                         run))

    for book, variant, m, cfg, run in jobs:
        r = run_one(run, cfg)
        if r is None:
            print("%-9s %-7s x%d FAIL" % (book, variant, m), flush=True)
            rows.append({"book": book, "variant": variant, "mult": m,
                         "net": "", "pf": "", "dd_yen": "", "dd_pct_nominal": "", "n": ""})
            continue
        dd_yen = r["ddpct"] / 100.0 * NOMINAL
        rows.append({"book": book, "variant": variant, "mult": m,
                     "net": r["net"], "pf": r["pf"], "dd_yen": dd_yen,
                     "dd_pct_nominal": r["ddpct"], "n": r["n"]})
        print("%-9s %-7s x%d net=%+11.0f円 pf=%.4f DD=%10.0f円 n=%d"
              % (book, variant, m, r["net"], r["pf"], dd_yen, r["n"]), flush=True)
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
