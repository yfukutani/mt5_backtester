# -*- coding: utf-8 -*-
"""5端末が本番と同一の数値を出すか、そして並列で壊れないかを実測する。

【なぜ厳密にやるか】
デモ口座では本番と純利益が4.5%ずれた。銘柄仕様が違えば数値は揃わない。
基準値(本番端末で測ったIS DD 35.65%)と比較して採否を決める作業なので、
土俵が違う数値を混ぜると判定が壊れる。

【手順】
  段階A: 5端末を1つずつ順に実行 → 本番端末の結果と完全一致するか
  段階B: 5端末を同時に実行 → 単独実行時と完全一致するか
Bでずれたら並列は不可。Aでずれたらその端末は使えない。
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

TERMINALS = {
    "PROD": r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe",
    "BT1": r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe",
    "BT2": r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe",
    "BT3": r"C:\Program Files\OANDA MetaTrader 5_BT3\terminal64.exe",
    "BT4": r"C:\Program Files\OANDA MetaTrader 5_BT4\terminal64.exe",
}

# SCA GBPJPY単独・IS。短くて差が出やすい構成を使う。
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
        "parameters": dict(PARAMS, **{"ResultFileName": run_id + "_r.csv",
                                      "EquityLogFile": run_id + "_deals.csv"}),
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
    import shutil
    tgt = REPO / "results" / run_id
    if tgt.exists():
        shutil.rmtree(tgt, ignore_errors=True)
    p = build(run_id, mt5_path)
    t0 = time.monotonic()
    subprocess.run([str(MT5BT), "run", str(p)], cwd=str(REPO), timeout=3600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out[run_id] = (summary(run_id), time.monotonic() - t0)


def show(label, res):
    s, el = res
    if not s:
        print("  %-6s 失敗" % label)
        return None
    print("  %-6s %6.1f秒  純利益=%9.1f PF=%.4f DD=%8.4f%% 取引=%d"
          % (label, el, s["net"], s["pf"], s["dd"], s["n"]))
    return s


def same(a, b):
    return (abs(a["net"] - b["net"]) < 0.5 and a["n"] == b["n"]
            and abs(a["dd"] - b["dd"]) < 0.001)


def main():
    out = {}
    print("=== 段階A: 各端末を単独で順に実行 ===")
    solo = {}
    for name, exe in TERMINALS.items():
        rid = "v5_solo_" + name.lower()
        launch(rid, exe, out)
        solo[name] = show(name, out[rid])

    ref = solo.get("PROD")
    if not ref:
        print("\n本番端末の基準が取れませんでした。中止します。")
        return 1
    print("\n--- 本番との一致 ---")
    usable = []
    for name in TERMINALS:
        s = solo.get(name)
        if not s:
            print("  %-6s 実行失敗 → 使用不可" % name)
            continue
        if same(ref, s):
            print("  %-6s 完全一致 ✓" % name)
            usable.append(name)
        else:
            print("  %-6s ⚠️不一致（純利益差 %+.1f / 取引差 %+d / DD差 %+.4f）"
                  % (name, s["net"] - ref["net"], s["n"] - ref["n"], s["dd"] - ref["dd"]))
    if len(usable) < 2:
        print("\n一致した端末が2つ未満。並列は行えません。")
        return 1

    print("\n=== 段階B: %d端末を同時実行 ===" % len(usable))
    threads = []
    for name in usable:
        rid = "v5_par_" + name.lower()
        t = threading.Thread(target=launch, args=(rid, TERMINALS[name], out))
        threads.append((name, rid, t))
    t0 = time.monotonic()
    for _, _, t in threads:
        t.start()
    for _, _, t in threads:
        t.join()
    wall = time.monotonic() - t0

    ok = True
    for name, rid, _ in threads:
        s = show(name, out[rid])
        if not s or not same(ref, s):
            ok = False
            if s:
                print("        ⚠️並列時に単独と不一致（純利益差 %+.1f / 取引差 %+d）"
                      % (s["net"] - ref["net"], s["n"] - ref["n"]))
    print("\n同時実行の実時間: %.1f秒" % wall)

    print("\n=== 判定 ===")
    if ok:
        serial = sum(out["v5_solo_" + n.lower()][1] for n in usable)
        print("並列実行でも全端末が本番と完全一致。%d並列は安全 ✓" % len(usable))
        print("直列 %.1f秒 → 並列 %.1f秒（%.2f倍速）" % (serial, wall, serial / wall))
    else:
        print("⚠️並列で数値がずれた。並列は不可。直列を維持すること。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
