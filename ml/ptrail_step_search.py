# -*- coding: utf-8 -*-
"""利益トレール（v1.5）の刻み最適点探索。

対象はFX枠のみ（EA側の PtrailEligible が PairTrade / Carry / GOLD / 暗号 を除外）。
ProfitTrail_Step を 0.4〜1.0 まで 0.1 刻みで振り、IS/OOS 両期間で比較する。
ブックはトレール対象の8枠のみ（Pair/Carryを混ぜると差が薄まるため）。

usage: python ml/ptrail_step_search.py [step ...]
"""
import csv
import subprocess
import sys
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "ptrail_work"
WORK.mkdir(parents=True, exist_ok=True)

ALL_OFF = {k: False for k in [
    "En_PB_USDJPY", "En_PB_GBPJPY", "En_PB_AUDJPY", "En_PB_GOLD",
    "En_RSI_USDJPY", "En_RSI_EURUSD", "En_RSI_GBPUSD", "En_PAIR", "En_CARRY",
    "En_VBO", "En_ETH", "En_BTC_FUND", "En_BFXREV",
    "En_SCA_GOLD", "En_SCA_USDJPY", "En_SCA_GBPJPY"]}

# 利益トレールの対象になるFX枠のみ（EA側の PtrailEligible と一致）
BOOK = ["En_PB_USDJPY", "En_PB_GBPJPY", "En_RSI_USDJPY", "En_RSI_EURUSD",
        "En_RSI_GBPUSD", "En_VBO", "En_SCA_USDJPY", "En_SCA_GBPJPY"]
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
LOCK = 0.1                       # 初回に確保する利益（残高比%）＝ユーザー指定値で固定
# 第1引数を入金額として扱う（%しきい値は残高基準なので、口座規模で発動頻度が大きく変わる）。
# フォワード実口座は6.5万〜12万なので 100000 が実運用に近い。
DEPOSIT = int(sys.argv[1]) if len(sys.argv) > 1 else 500000
STEPS = [float(a) for a in sys.argv[2:]] or [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
TAG = "PTF" if DEPOSIT == 500000 else "PTD%d" % (DEPOSIT // 10000)


def run(win, tag, step):
    name = "%s_%s_%s" % (TAG, win, tag)
    p = dict(ALL_OFF)
    for k in BOOK:
        p[k] = True
    p.update({"RefCap_PB_USDJPY": 100000, "RefCap_PB_GBPJPY": 100000,
              "EnableOpsLog": True, "OpsLogPrefix": name.lower(),
              "ResultFileName": name + "_r.csv"})
    if step is not None:
        p["UseProfitTrail"] = True
        p["ProfitTrail_Step"] = step
        p["ProfitTrail_Lock"] = LOCK
    cfg = {"mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
           "expert": "MIX_EA", "symbol": "USDJPY", "period": "M15",
           "from_date": WINDOWS[win][0], "to_date": WINDOWS[win][1],
           "deposit": DEPOSIT, "currency": "JPY", "leverage": 25,
           "model": "every_tick", "parameters": p,
           "report_dir": "results", "report_name": name}
    path = WORK / (name + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    f = REPO / "results" / name / "summary.csv"
    if not f.exists():
        t0 = time.time()
        try:
            subprocess.run([MT5BT, "run", str(path)], cwd=str(REPO),
                           capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired:
            pass
        if not f.exists():
            subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
            time.sleep(3)
            print("  %-14s FAIL (%.0fs)" % (name, time.time() - t0), flush=True)
            return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"]), "win": float(d["勝率%"])}
    except (KeyError, ValueError):
        return None


variants = [("OFF", None)] + [("S%02d" % round(s * 100), s) for s in STEPS]
res = {}
for win in ("IS", "OOS"):
    for tag, step in variants:
        r = run(win, tag, step)
        res[(win, tag)] = r
        if r:
            print("  %-3s %-4s net=%+9.0f pf=%5.2f dd=%5.1f%% win=%4.1f%% n=%5d"
                  % (win, tag, r["net"], r["pf"], r["dd"], r["win"], r["n"]), flush=True)

print()
print("=" * 104)
print("利益トレール 刻み探索（FX枠8つのみ・Pair/Carry/GOLD/暗号は対象外・Lock=%.1f%%固定・入金%d円）"
      % (LOCK, DEPOSIT))
print("%-6s | %10s %5s %5s %5s %5s | %10s %5s %5s %5s | %9s %s"
      % ("刻み", "IS純益", "PF", "DD%", "勝率", "n", "OOS純益", "PF", "DD%", "n", "合計差", "判定"))
b_is, b_oos = res.get(("IS", "OFF")), res.get(("OOS", "OFF"))
if b_is and b_oos:
    print("%-6s | %+10.0f %5.2f %5.1f %5.1f %5d | %+10.0f %5.2f %5.1f %5d | %9s 基準"
          % ("OFF", b_is["net"], b_is["pf"], b_is["dd"], b_is["win"], b_is["n"],
             b_oos["net"], b_oos["pf"], b_oos["dd"], b_oos["n"], "-"))
    best = None
    for tag, step in variants[1:]:
        gi, go = res.get(("IS", tag)), res.get(("OOS", tag))
        if not (gi and go):
            continue
        d_is, d_oos = gi["net"] - b_is["net"], go["net"] - b_oos["net"]
        both = "**両期間+**" if (d_is >= 0 and d_oos >= 0) else ("片側+" if d_is + d_oos > 0 else "")
        print("%-6s | %+10.0f %5.2f %5.1f %5.1f %5d | %+10.0f %5.2f %5.1f %5d | %+9.0f %s"
              % ("%.1f%%" % step, gi["net"], gi["pf"], gi["dd"], gi["win"], gi["n"],
                 go["net"], go["pf"], go["dd"], go["n"], d_is + d_oos, both))
        if best is None or (d_is + d_oos) > best[1]:
            best = (step, d_is + d_oos, d_is, d_oos)
    if best:
        print()
        print("合計差が最大の刻み: %.1f%%（IS %+.0f / OOS %+.0f / 合計 %+.0f）"
              % (best[0], best[2], best[3], best[1]))
        print("※採用には「IS/OOS両期間で悪化なし」かつ「隣接水準も同傾向（台地）」が必要")
