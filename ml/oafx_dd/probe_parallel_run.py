# -*- coding: utf-8 -*-
"""BT1/BT2で実際に並列実行し、単独実行と同じ結果になるかを実測で確かめる。

理屈で「分離しているから大丈夫」と判断しない。過去に並列実行で結果が壊れ、
誤ったFAIL判定を生んだ実績があるため、必ず数値の一致で確認する。

手順:
  1. BT1単独で基準runを実行 → 成績を記録
  2. BT2単独で同じ設定を実行 → BT1と一致するか（端末差が無いことの確認）
  3. BT1とBT2で同時に実行 → 単独時と一致するか（並列で壊れないことの確認）

3で数値がずれたら並列は不可。
"""
import csv
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MT5BT = Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
WORK = REPO / "ml" / "oafx_dd" / "configs"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")

BT1 = r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"
BT2 = r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe"

PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": False, "En_SCA_USDJPY": False,
    "En_SCA_GBPJPY": True,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
}


def build(run_id, mt5_path):
    cfg = {
        "mt5_path": mt5_path, "expert": "MIX_EA_OANDA_SIMVERIFY",
        "symbol": "USDJPY", "period": "M15",
        "from_date": "2021.06.21", "to_date": "2026.06.20",
        "deposit": 77954, "currency": "JPY", "leverage": 25,
        "model": "every_tick",
        "parameters": dict(PARAMS, **{
            "ResultFileName": run_id + "_r.csv",
            "EquityLogFile": run_id + "_deals.csv",
        }),
        "report_dir": "results", "report_name": run_id,
    }
    p = WORK / (run_id + ".yaml")
    p.parent.mkdir(parents=True, exist_ok=True)
    yaml.safe_dump(cfg, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    return p


def summary(run_id):
    f = REPO / "results" / run_id / "summary.csv"
    if not f.exists():
        return None
    d = {r[0]: r[1] for r in csv.reader(open(f, encoding="utf-8-sig")) if len(r) >= 2}
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


def launch(run_id, mt5_path, out):
    p = build(run_id, mt5_path)
    t0 = time.monotonic()
    subprocess.run([str(MT5BT), "run", str(p)], cwd=str(REPO), timeout=3600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out[run_id] = (summary(run_id), time.monotonic() - t0)


def show(label, res):
    s, el = res
    if not s:
        print("%-22s 失敗" % label)
        return None
    print("%-22s %6.1f秒  純利益=%9.1f PF=%.4f DD=%7.4f%% 取引=%d"
          % (label, el, s["net"], s["pf"], s["dd"], s["n"]))
    return s


def main():
    out = {}
    print("=== 1. BT1単独 ===")
    launch("par_bt1_solo", BT1, out)
    a = show("BT1単独", out["par_bt1_solo"])

    print("\n=== 2. BT2単独 ===")
    launch("par_bt2_solo", BT2, out)
    b = show("BT2単独", out["par_bt2_solo"])

    print("\n=== 3. BT1+BT2 同時実行 ===")
    t1 = threading.Thread(target=launch, args=("par_bt1_par", BT1, out))
    t2 = threading.Thread(target=launch, args=("par_bt2_par", BT2, out))
    t0 = time.monotonic()
    t1.start(); t2.start()
    t1.join(); t2.join()
    wall = time.monotonic() - t0
    c = show("BT1並列", out["par_bt1_par"])
    d = show("BT2並列", out["par_bt2_par"])
    print("同時実行の実時間: %.1f秒" % wall)

    print("\n=== 判定 ===")
    if not all([a, b, c, d]):
        print("いずれかが失敗。並列は許可できない。")
        return 1
    ok = True
    if abs(a["net"] - b["net"]) > 0.5 or a["n"] != b["n"]:
        print("⚠️BT1単独とBT2単独で結果が違う。端末設定が揃っていない。")
        ok = False
    for lbl, x in (("BT1", c), ("BT2", d)):
        if abs(x["net"] - a["net"]) > 0.5 or x["n"] != a["n"]:
            print("⚠️%s の並列結果が単独と違う（純利益 %.1f vs %.1f / 取引 %d vs %d）"
                  % (lbl, x["net"], a["net"], x["n"], a["n"]))
            ok = False
    if ok:
        solo_total = out["par_bt1_solo"][1] + out["par_bt2_solo"][1]
        print("並列実行しても結果は単独と完全一致。並列は安全。")
        print("2本を直列 %.1f秒 → 並列 %.1f秒（%.2f倍速）" % (solo_total, wall, solo_total / wall))
    else:
        print("並列は不可。直列を維持すること。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
