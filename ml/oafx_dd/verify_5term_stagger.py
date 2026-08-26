# -*- coding: utf-8 -*-
"""起動をずらして5端末並列が安定するかを検証する。

【前回の失敗】5端末同時起動でBT2だけ失敗した。原因はテスターエージェントの
ポート競合:
    Core 01  agent process started on 127.0.0.1:3002
    Core 01  authorization failed (Invalid parameters)
MT5のローカルエージェントは全端末が3000番台を使うため、同時に立ち上げると
他端末のエージェントに接続してしまう。

【対策】起動を数十秒ずらす。先に起動した端末がポートを確保しきってから次を
起動すれば、後続は空きポートへ繰り上がる。agents.datはバイナリのため直接
編集せず、タイミングで回避する。

段階Aで5端末すべてが本番と完全一致することは確認済み(84921.0/1.2184/19.5314/685)。
ここでは並列時に同じ数値が出るかだけを見る。
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
REF = {"net": 84921.0, "pf": 1.2184, "dd": 19.5314, "n": 685}
STAGGER = 25  # 秒

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
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
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
    t0 = time.monotonic()
    subprocess.run([str(MT5BT), "run", str(p)], cwd=str(REPO), timeout=3600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out[run_id] = (summary(run_id), time.monotonic() - t0, delay)


def same(s):
    return (abs(s["net"] - REF["net"]) < 0.5 and s["n"] == REF["n"]
            and abs(s["dd"] - REF["dd"]) < 0.001)


def main():
    out = {}
    print("=== 5端末を%d秒ずつずらして並列実行 ===" % STAGGER)
    threads = []
    for i, (name, exe) in enumerate(TERMINALS.items()):
        rid = "v5s_" + name.lower()
        t = threading.Thread(target=launch, args=(rid, exe, i * STAGGER, out))
        threads.append((name, rid, t))
    t0 = time.monotonic()
    for _, _, t in threads:
        t.start()
    for _, _, t in threads:
        t.join()
    wall = time.monotonic() - t0

    ok, good = True, 0
    for name, rid, _ in threads:
        s, el, delay = out.get(rid, (None, 0, 0))
        if not s:
            print("  %-6s (+%3ds) 失敗" % (name, delay))
            ok = False
            continue
        hit = same(s)
        good += 1 if hit else 0
        print("  %-6s (+%3ds) %6.1f秒  純利益=%9.1f DD=%8.4f%% 取引=%d  %s"
              % (name, delay, el, s["net"], s["dd"], s["n"], "一致 ✓" if hit else "⚠️不一致"))
        if not hit:
            ok = False
    print("\n実時間: %.1f秒（うち起動ずらし %d秒）" % (wall, (len(threads) - 1) * STAGGER))
    print("\n=== 判定 ===")
    if ok:
        print("5端末すべてが本番と完全一致。並列は安全 ✓")
        print("直列なら約%.0f秒 → 並列 %.1f秒（%.2f倍速）" % (73 * 5, wall, 73 * 5 / wall))
    else:
        print("成功 %d/%d。ポート競合が残る場合は端末数を減らすこと。" % (good, len(threads)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
