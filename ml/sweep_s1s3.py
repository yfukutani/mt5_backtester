# -*- coding: utf-8 -*-
"""S1（枠別ブレークイーブン）/ S3（ATR連動トレーリング）の直列スイープ。

- 本番リファレンスconfigを読み込み、窓・model・利益保護パラメータだけを上書きして実行する
  （戦略パラメータは production のまま＝比較の土台を固定）
- mt5bt optimize は並列12エージェントでティックキャッシュを食い尽くすため使わない（直列run）
- resume安全: results/<NAME>/summary.csv があれば再実行しない

usage:
  python sweep_s1s3.py regression   # 既定値のみ（改修前後の同一性確認用）
  python sweep_s1s3.py all          # 全点
"""
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(r"C:\Users\f\source\repos\mt5_backtester")
WORK = Path(r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\s1s3")
WORK.mkdir(parents=True, exist_ok=True)

WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
# XM GOLD はテスターが「終端(2026.06.20)で終わる窓」しか実行できない。
# 実測: 2021.06.21-2026.06.20 ✓ / 2024.01.01-2026.06.20 ✓ /
#       2016.06.21-2021.06.20 ✗ / 2019.06.21-2021.06.20 ✗ / 2016.06.21-2018.06.20 ✗ /
#       2020.06.21-2021.06.20 ✗ / 2021.06.21-2024.01.01 ✗（every_tick / open_prices とも同じ）
# 他5枠は同じ窓指定で正常に走るためGOLD固有のデータ制約。独立したOOS窓が取れないので
# GOLDは「全期間(2021.06-2026.06)」と「直近(2024.01-2026.06)」の入れ子2窓で評価し、
# IS/OOSゲートは適用しない（＝参考値扱い。判定は他5枠で行う）。
WINDOWS_GOLD = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2024.01.01", "2026.06.20")}

# sleeve -> (基準config, EA種別, 固定SL pips（RSIのpips版BE換算用。ATR系はNone）)
SLEEVES = {
    "PB_GOLD":    ("configs/pullback_gold_h4.yaml",       "PB",  None),
    "PB_USDJPY":  ("configs/pullback_usdjpy_h4.yaml",     "PB",  None),
    "PB_GBPJPY":  ("configs/pullback_gbpjpy_h4.yaml",     "PB",  None),
    "RSI_EURUSD": ("configs/rsi_robust_eurusd_h1.yaml",   "RSI", 45),
    "RSI_USDJPY": ("configs/rsi_robust_usdjpy_h4.yaml",   "RSI", 50),
    "RSI_GBPUSD": ("configs/rsi_robust_gbpusd_h4.yaml",   "RSI", 50),
}
BE_TRIGGERS = [0.4, 0.5, 0.75, 1.0]        # S1
TRAIL_MULTS = [1.5, 2.0, 2.5, 3.0]         # S3（PullbackTrendのみ）


def variants(kind):
    v = [("BASE", {})]
    for t in BE_TRIGGERS:
        tag = "BE%02d" % round(t * 100)
        v.append((tag, {"be": t}))
    if kind == "PB":
        for m in TRAIL_MULTS:
            v.append(("TR%02d" % round(m * 10), {"trail": m}))
    return v


def build(sleeve, base_cfg, kind, sl_pips, win, tag, spec, prefix="S13"):
    with open(REPO / base_cfg, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    frm, to = (WINDOWS_GOLD if sleeve == "PB_GOLD" else WINDOWS)[win]
    name = "%s_%s_%s_%s" % (prefix, sleeve, win, tag)
    cfg["from_date"], cfg["to_date"] = frm, to
    cfg["model"] = "every_tick"          # ゲート要件
    cfg["report_dir"], cfg["report_name"] = "results", name
    p = cfg.setdefault("parameters", {})
    p["ResultFileName"] = name + "_r.csv"
    if "be" in spec:
        if kind == "PB":
            p["UseBreakevenR"] = True
            p["BE_Trigger_R"] = spec["be"]
            p["BE_Offset_R"] = 0.0
        else:                             # RSIは既存のpips版BEを使う（SL固定pipsのためR換算は厳密）
            p["UseBreakeven"] = True
            p["BE_Trigger_Pips"] = int(round(spec["be"] * sl_pips))
    if "trail" in spec:
        p["UseATRTrail"] = True
        p["Trail_Mult_ATR"] = spec["trail"]
    path = WORK / (name + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    return name, path


def summary(name):
    f = REPO / "results" / name / "summary.csv"
    if not f.exists():
        return None
    d = {}
    with open(f, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"]),
                "win": float(d["勝率%"])}
    except (KeyError, ValueError):
        return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    prefix = sys.argv[2] if len(sys.argv) > 2 else "S13"
    jobs = []
    for sleeve, (base_cfg, kind, sl_pips) in SLEEVES.items():
        for win in ("IS", "OOS"):
            for tag, spec in variants(kind):
                if mode == "regression" and tag != "BASE":
                    continue
                jobs.append((sleeve, base_cfg, kind, sl_pips, win, tag, spec))

    out, fails, t0 = [], [], time.time()
    for i, (sleeve, base_cfg, kind, sl_pips, win, tag, spec) in enumerate(jobs, 1):
        name, path = build(sleeve, base_cfg, kind, sl_pips, win, tag, spec, prefix)
        r = summary(name)
        if r is None:
            t1 = time.time()
            try:
                subprocess.run([MT5BT, "run", str(path)], cwd=str(REPO),
                               capture_output=True, text=True, timeout=2400)
            except subprocess.TimeoutExpired:
                pass
            r = summary(name)
            if r is None:
                fails.append(name)
                print("[%2d/%d] %-22s FAIL (%.0fs)" % (i, len(jobs), name, time.time() - t1), flush=True)
                subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
                time.sleep(3)
                continue
            print("[%2d/%d] %-22s net=%+9.0f pf=%.2f dd=%5.1f%% n=%4d (%.0fs)"
                  % (i, len(jobs), name, r["net"], r["pf"], r["dd"], r["n"], time.time() - t1), flush=True)
        else:
            print("[%2d/%d] %-22s cached net=%+9.0f" % (i, len(jobs), name, r["net"]), flush=True)
        out.append({"sleeve": sleeve, "window": win, "variant": tag, **r})
        with open(WORK / "s1s3_results.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
    print("TOTAL %.1f min  done=%d fail=%d %s"
          % ((time.time() - t0) / 60, len(out), len(fails), ",".join(fails)), flush=True)


if __name__ == "__main__":
    main()
