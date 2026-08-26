# -*- coding: utf-8 -*-
"""起動ずらし間隔を詰めて、実効速度が最大になる設定を探す。

25秒ずらしでは5端末すべてが本番と完全一致したが、ずらし合計100秒が
実時間243秒の4割を占めた。ポート競合を避けられる最小の間隔を見つけたい。

ポート競合は「先に起動した端末がエージェントのポートを確保しきる前に
次が起動する」と起きる。確保に必要な時間だけずらせばよい。

各間隔で5端末を回し、全件一致したかと実時間を記録する。
一致しない間隔が出たらそこが下限。
"""
import csv
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MT5BT = Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
WORK = REPO / "ml" / "oafx_dd" / "configs"

TERMINALS = {
    "PROD": r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe",
    "BT1": r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe",
    "BT2": r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe",
    "BT3": r"C:\Program Files\OANDA MetaTrader 5_BT3\terminal64.exe",
    "BT4": r"C:\Program Files\OANDA MetaTrader 5_BT4\terminal64.exe",
}
REF = {"net": 84921.0, "dd": 19.5314, "n": 685}
CANDIDATES = [8, 15]   # 25秒は検証済み。より短い間隔を試す。

PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": False, "En_SCA_USDJPY": False,
    "En_SCA_GBPJPY": True,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
}


def summary(run_id):
    f = REPO / "results" / run_id / "summary.csv"
    if not f.exists():
        return None
    d = {r[0]: r[1] for r in csv.reader(open(f, encoding="utf-8-sig")) if len(r) >= 2}
    try:
        return {"net": float(d["純利益"]), "dd": float(d["最大相対DD%"]),
                "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


def launch(run_id, mt5_path, delay, out):
    time.sleep(delay)
    tgt = REPO / "results" / run_id
    if tgt.exists():
        shutil.rmtree(tgt, ignore_errors=True)
    cfg = {
        "mt5_path": mt5_path, "expert": "MIX_EA_OANDA_SIMVERIFY",
        "symbol": "USDJPY", "period": "M15",
        "from_date": "2021.06.21", "to_date": "2026.06.20",
        "deposit": 77954, "currency": "JPY", "leverage": 25,
        "model": "every_tick",
        "parameters": dict(PARAMS, **{"ResultFileName": run_id + "_r.csv",
                                      "EquityLogFile": run_id + "_deals.csv"}),
        "report_dir": "results", "report_name": run_id,
    }
    p = WORK / (run_id + ".yaml")
    yaml.safe_dump(cfg, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    subprocess.run([str(MT5BT), "run", str(p)], cwd=str(REPO), timeout=3600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out[run_id] = summary(run_id)


def ok(s):
    return s and abs(s["net"] - REF["net"]) < 0.5 and s["n"] == REF["n"] \
        and abs(s["dd"] - REF["dd"]) < 0.001


def trial(stagger):
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(6)
    out = {}
    threads = []
    for i, (name, exe) in enumerate(TERMINALS.items()):
        rid = "tune%d_%s" % (stagger, name.lower())
        t = threading.Thread(target=launch, args=(rid, exe, i * stagger, out))
        threads.append((name, rid, t))
    t0 = time.monotonic()
    for _, _, t in threads:
        t.start()
    for _, _, t in threads:
        t.join()
    wall = time.monotonic() - t0
    good = sum(1 for _, rid, _ in threads if ok(out.get(rid)))
    bad = [n for n, rid, _ in threads if not ok(out.get(rid))]
    print("  ずらし%2d秒: 一致 %d/5  実時間 %.1f秒%s"
          % (stagger, good, wall, ("  ⚠️不一致=" + ",".join(bad)) if bad else ""), flush=True)
    return good == 5, wall


def main():
    print("=== 起動ずらし間隔の調整（5端末・基準は本番の84921.0/19.5314%/685）===")
    print("  ずらし25秒: 一致 5/5  実時間 243.3秒（検証済み）")
    best = (25, 243.3)
    for s in CANDIDATES:
        good, wall = trial(s)
        if good and wall < best[1]:
            best = (s, wall)
    print("\n=== 結論 ===")
    print("推奨する起動ずらし: %d秒（実時間 %.1f秒）" % best)
    print("1本あたり実効 %.1f秒。直列73秒/本に対し %.2f倍速。"
          % (best[1] / 5, 73 * 5 / best[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
