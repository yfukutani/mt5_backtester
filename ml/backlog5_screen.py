# -*- coding: utf-8 -*-
"""第5次バックログ候補の一次スクリーニング（チャンピオンテスト・open_prices・全期間）。

ml/backlog5/candidates.csv を優先度順(S>A>B>C)に読み込み、各候補を1回だけ
open_prices・全期間(2016.06.21-2026.06.20)で実行し、生存基準を満たしたものだけ
tier2（IS/OOS every_tick）へ昇格する。resume安全（results/配下を正として再実行しない）。

生存基準（一次）: 純利益>0 かつ PF>=1.05 かつ 取引数>=15 かつ 最大DD%<60
"""
import csv
import subprocess
import sys
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "backlog5" / "cfg"
WORK.mkdir(parents=True, exist_ok=True)
CAND = REPO / "ml" / "backlog5" / "candidates.csv"
OUT = REPO / "ml" / "backlog5" / "screen_results.csv"

XM = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

BASE_PARAMS = {
    "PullbackTrend": dict(
        TrendMA_Period=200, FastEMA_Period=20, SlowEMA_Period=50,
        RequireBullishCandle=True, UsePullbackQuality=True, UseMomentumConfirm=True,
        UseADXFilter=True, ADX_Period=14, ADX_Threshold=22.5,
        UseTrendStrength=True, MA_Slope_Lookback=20, MA_Slope_Min_ATR=1.2,
        UseATRStops=True, ATR_Period=14, ATR_SL_Mult=2.0, RR_Ratio=2.0,
        UseRiskSizing=False, MagicNumber=99000001,
    ),
    "RSI_Reversal": dict(
        MA_Period=200, BB_Period=20, BB_Deviation=2.5, RSI_Period=14,
        RSI_OverboughtExtreme=75.0, RSI_Overbought=72.5,
        RSI_OversoldExtreme=27.5, RSI_Oversold=30.0,
        UseDoublePattern=False, UseTrailingStop=False, UseBreakeven=False,
        UseVolatilityFilter=False, UseTimeFilter=False, UseATRStopLoss=False,
        UseADXFilter=False, UseRangeFilter=True, Range_Slope_Lookback=20,
        Range_Slope_Max_ATR=0.2, StopLoss_Pips=45, TakeProfit_Pips=105,
        UseRiskSizing=False, MagicNumber=99000002,
    ),
    "VolBreakout": dict(
        Channel_Period=20, AllowLong=True, AllowShort=True,
        UseSqueezeFilter=True, Squeeze_Lookback=50, Squeeze_Factor=1.0,
        ATR_Period=14, ATR_SL_Mult=2.0, Trail_Mult=3.0,
        UseRiskSizing=False, MagicNumber=99000003,
    ),
    "SCA_EA": dict(
        RangeStartHour=0, RangeEndHour=9, TradeEndHour=12, ForceCloseHour=22,
        MinRange_ATRd=0.30, MaxRange_ATRd=1.00, Break_Buffer_ATRd=0.0,
        SL_Mode=0, SL_ATRd_Mult=0.5, RR_Ratio=2.0, OneShotPerDir=True,
        UseD1TrendFilter=False, UseReversalBoost=True, Boost_Mult=2.0,
        MagicNumber=99000004,
    ),
    "Carry": dict(
        TrendMA_Period=200, RequirePositiveSwap=True, UseHysteresis=True,
        ATR_Period=14, Hyst_ATR_Mult=0.75, ExitMA_Period=0, ReentryCooldown=0,
        UseRiskSizing=False, MagicNumber=99000005,
    ),
}

TAG_OVERRIDES = {
    "std": {},
    "noadx": {"UseADXFilter": False},
    "rr25": {"RR_Ratio": 2.5},
    "range035": {"Range_Slope_Max_ATR": 0.35},
    "atrstop": {"UseATRStopLoss": True, "ATR_SL_Multiplier": 1.5, "ATR_RR_Ratio": 2.0},
    "bb30": {"BB_Deviation": 3.0},
    "nosqueeze": {"UseSqueezeFilter": False},
    "trail20": {"Trail_Mult": 2.0},
    "ch10": {"Channel_Period": 10},
    "range_wide": {"MinRange_ATRd": 0.15, "MaxRange_ATRd": 1.5},
    "noboost": {"UseReversalBoost": False},
    "hyst15": {"Hyst_ATR_Mult": 1.5},
    "negswap": {"RequirePositiveSwap": False},
}

PASS = dict(min_net=0.0, min_pf=1.05, min_n=15, max_dd=60.0)


def build_cfg(row):
    tmpl = row["template"]
    p = dict(BASE_PARAMS[tmpl])
    p.update(TAG_OVERRIDES.get(row["tag"], {}))
    p["LotSize"] = float(row["lot"])
    p["ResultFileName"] = row["id"] + "_r.csv"
    cfg = {
        "mt5_path": XM, "expert": tmpl, "symbol": row["symbol"], "period": row["period"],
        "from_date": "2016.06.21", "to_date": "2026.06.20",
        "deposit": 100000, "currency": "JPY", "leverage": 25,
        "model": "open_prices", "parameters": p,
        "report_dir": "results", "report_name": row["id"],
    }
    path = WORK / (row["id"] + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    return path


def summary(rid):
    f = REPO / "results" / rid / "summary.csv"
    if not f.exists():
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


def passed(r):
    return (r["net"] > PASS["min_net"] and r["pf"] >= PASS["min_pf"]
            and r["n"] >= PASS["min_n"] and r["dd"] < PASS["max_dd"])


def main():
    rows = list(csv.DictReader(open(CAND, encoding="utf-8")))
    order = {"S": 0, "A": 1, "B": 2, "C": 3}
    rows.sort(key=lambda r: order.get(r["priority"], 9))

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(rows)
    rows = rows[:limit]

    out_rows = []
    if OUT.exists():
        out_rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
    done_ids = {r["id"] for r in out_rows}

    survivors, fails, t0 = [], [], time.time()
    for i, row in enumerate(rows, 1):
        rid = row["id"]
        if rid in done_ids:
            continue
        cfg_path = build_cfg(row)
        r = summary(rid)
        if r is None:
            t1 = time.time()
            try:
                subprocess.run([MT5BT, "run", str(cfg_path)], cwd=str(REPO),
                               capture_output=True, text=True, timeout=1800)
            except subprocess.TimeoutExpired:
                pass
            r = summary(rid)
            el = time.time() - t1
            if r is None:
                fails.append(rid)
                print("[%3d/%d] %-6s %-24s %-16s %-6s FAIL (%.0fs)"
                      % (i, len(rows), rid, row["family"], row["symbol"], row["tag"], el), flush=True)
                subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
                time.sleep(2)
                out_rows.append({**row, "net": "", "pf": "", "dd": "", "n": "", "win": "",
                                  "verdict": "FAIL"})
                with open(OUT, "w", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(row.keys()) + ["net", "pf", "dd", "n", "win", "verdict"])
                    w.writeheader()
                    w.writerows(out_rows)
                continue
        ok = passed(r)
        if ok:
            survivors.append(rid)
        print("[%3d/%d] %-6s %-24s %-16s %-9s net=%+9.0f pf=%5.2f dd=%5.1f%% n=%4d %s"
              % (i, len(rows), rid, row["family"], row["symbol"], row["tag"],
                 r["net"], r["pf"], r["dd"], r["n"], "**PASS**" if ok else ""), flush=True)
        out_rows.append({**row, "net": r["net"], "pf": r["pf"], "dd": r["dd"],
                          "n": r["n"], "win": r["win"], "verdict": "PASS" if ok else "reject"})
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row.keys()) + ["net", "pf", "dd", "n", "win", "verdict"])
            w.writeheader()
            w.writerows(out_rows)

    print()
    print("TOTAL %.1f min  processed=%d survivors=%d fails=%d"
          % ((time.time() - t0) / 60, len(rows) - len(done_ids) + len(done_ids), len(survivors), len(fails)))
    print("survivors:", survivors)


if __name__ == "__main__":
    main()
