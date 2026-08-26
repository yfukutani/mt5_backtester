# -*- coding: utf-8 -*-
"""二段階スクリーニングの前提を確かめる: SCA GBPJPY単独runはどれだけ速いか。

9枠フルブックのIS runは平均374秒。1000案では約108時間かかる。
1000案中900案が SCA GBPJPY 狙いなので、まず同枠単独で篩えれば大幅に短縮できる。

ただし単独枠は枠間の重なりを捉えられない（最大DD区間の損失の83%が同時保有中に発生）。
よってスクリーニングにのみ使い、**最終判定は必ず9枠フルブックで行う**。
この前提が成り立つかを、まず速度で確認する。
"""
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MT5BT = Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
WORK = REPO / "ml" / "oafx_dd" / "configs"
OANDA_PATH = r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"

BASE = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": False, "En_SCA_USDJPY": False,
    "En_SCA_GBPJPY": True,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
}
FULLBOOK = dict(BASE, **{
    "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_RSI_USDJPY": True,
    "En_RSI_EURUSD": True, "En_RSI_GBPUSD": True, "En_PAIR": True,
    "En_CARRY": True, "En_SCA_USDJPY": True,
})


def wait_idle():
    while True:
        r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True)
        if not any(p in r.stdout for p in ("terminal64.exe", "metatester64.exe")):
            return
        time.sleep(10)


def run(label, params):
    run_id = "oafx_speed_" + label
    cfg = {
        "mt5_path": OANDA_PATH, "expert": "MIX_EA_OANDA_SIMVERIFY",
        "symbol": "USDJPY", "period": "M15",
        "from_date": "2021.06.21", "to_date": "2026.06.20",
        "deposit": 77954, "currency": "JPY", "leverage": 25,
        "model": "every_tick",
        "parameters": dict(params, **{"ResultFileName": run_id + "_r.csv"}),
        "report_dir": "results", "report_name": run_id,
    }
    p = WORK / (run_id + ".yaml")
    p.parent.mkdir(parents=True, exist_ok=True)
    yaml.safe_dump(cfg, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    wait_idle()
    t0 = time.monotonic()
    subprocess.run([str(MT5BT), "run", str(p)], cwd=str(REPO), timeout=3600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    el = time.monotonic() - t0
    f = REPO / "results" / run_id / "summary.csv"
    net = dd = n = "?"
    if f.exists():
        import csv
        d = {r[0]: r[1] for r in csv.reader(open(f, encoding="utf-8-sig")) if len(r) >= 2}
        net, dd, n = d.get("純利益"), d.get("最大相対DD%"), d.get("総取引数")
    print("%-10s %7.1f秒  純利益=%s DD=%s%% 取引=%s" % (label, el, net, dd, n), flush=True)
    return el


if __name__ == "__main__":
    a = run("gjonly", BASE)
    b = run("fullbook", FULLBOOK)
    print("\n単独枠 %.1f秒 / フルブック %.1f秒 → %.1f倍速" % (a, b, b / a if a else 0))
    print("1000案の見積: 単独 %.1f時間 / フルブック %.1f時間" % (a * 1000 / 3600, b * 1000 / 3600))
    sys.exit(0)
