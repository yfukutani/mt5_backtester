# -*- coding: utf-8 -*-
"""利益トレール（v1.5）の効果測定。

15枠フルブックはティックデータが約11-14GB必要でRAM上限に当たり不安定なため、
銘柄群ごとに軽量ブックへ分割して測定する（どの枠で効くかも分かる）。
"""
import csv
import subprocess
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(r"C:\Users\f\source\repos\mt5_backtester")
WORK = Path(r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\ptrail")
WORK.mkdir(parents=True, exist_ok=True)

ALL_OFF = {k: False for k in [
    "En_PB_USDJPY", "En_PB_GBPJPY", "En_PB_AUDJPY", "En_PB_GOLD",
    "En_RSI_USDJPY", "En_RSI_EURUSD", "En_RSI_GBPUSD", "En_PAIR", "En_CARRY",
    "En_VBO", "En_ETH", "En_BTC_FUND", "En_BFXREV",
    "En_SCA_GOLD", "En_SCA_USDJPY", "En_SCA_GBPJPY"]}

# ブック定義: 有効枠 / チャート銘柄 / 窓（GOLDは終端固定窓しか実行できない）
BOOKS = {
    "FX": (["En_PB_USDJPY", "En_PB_GBPJPY", "En_RSI_USDJPY", "En_RSI_EURUSD",
            "En_RSI_GBPUSD", "En_PAIR", "En_VBO", "En_SCA_USDJPY", "En_SCA_GBPJPY"],
           "USDJPY", {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}),
    "GOLD": (["En_PB_GOLD", "En_SCA_GOLD"], "GOLD",
             {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2024.01.01", "2026.06.20")}),
    "CRYPTO": (["En_ETH", "En_BTC_FUND", "En_BFXREV"], "BTCUSD",
               {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2019.09.01", "2021.06.20")}),
}
VARIANTS = [("OFF", {}), ("ON", {"step": 0.5, "lock": 0.1}),
            ("S03", {"step": 0.3, "lock": 0.1}), ("S10", {"step": 1.0, "lock": 0.2})]


def run(book, win, tag, spec):
    en, chart, wins = BOOKS[book]
    name = "PT_%s_%s_%s" % (book, win, tag)
    p = dict(ALL_OFF)
    for k in en:
        p[k] = True
    p.update({"RefCap_PB_USDJPY": 100000, "RefCap_PB_GBPJPY": 100000, "RefCap_CARRY": 100000,
              "Mult_BTC_FUND": 2.0, "Mult_BFXREV": 2.0, "Mult_ETH": 2.0,
              "EnableOpsLog": True, "OpsLogPrefix": name.lower(),
              "ResultFileName": name + "_r.csv"})
    if spec:
        p["UseProfitTrail"] = True
        p["ProfitTrail_Step"] = spec["step"]
        p["ProfitTrail_Lock"] = spec["lock"]
    cfg = {"mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
           "expert": "MIX_EA", "symbol": chart, "period": "M15",
           "from_date": wins[win][0], "to_date": wins[win][1],
           "deposit": 500000, "currency": "JPY", "leverage": 25,
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
            print("  %-22s FAIL (%.0fs)" % (name, time.time() - t0), flush=True)
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


res = {}
for book in BOOKS:
    for win in ("IS", "OOS"):
        for tag, spec in VARIANTS:
            r = run(book, win, tag, spec)
            res[(book, win, tag)] = r
            if r:
                print("  %-6s %-3s %-3s net=%+9.0f pf=%5.2f dd=%5.1f%% win=%4.1f%% n=%5d"
                      % (book, win, tag, r["net"], r["pf"], r["dd"], r["win"], r["n"]), flush=True)

print()
print("=" * 92)
print("利益トレール ON/OFF（入金50万・every_tick・XM）")
print("%-7s %-4s %-4s %10s %6s %6s %6s %6s | 対OFF" % ("book", "窓", "設定", "純利益", "PF", "DD%", "勝率", "n"))
for book in BOOKS:
    for win in ("IS", "OOS"):
        b = res.get((book, win, "OFF"))
        if not b:
            continue
        for tag, _ in VARIANTS:
            r = res.get((book, win, tag))
            if not r:
                continue
            diff = "基準" if tag == "OFF" else "%+.0f (%+.1f%%)" % (
                r["net"] - b["net"], (r["net"] / b["net"] - 1) * 100 if b["net"] else 0)
            print("%-7s %-4s %-4s %+10.0f %6.2f %6.1f %6.1f %6d | %s"
                  % (book, win, tag, r["net"], r["pf"], r["dd"], r["win"], r["n"], diff))
