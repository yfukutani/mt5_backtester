# -*- coding: utf-8 -*-
"""第6次バックログの応答曲面で見つかった「既存採用済みスリーブの改善候補」を、
本番configと同一条件（ロット/サイジング/every_tick）でIS/OOS検証する。

グリッドサーチ自体はfixed lot 0.01・open_pricesで行ったため、本番の実際のサイジング
（risk%やevery_tick）とは条件が異なる。ここでは本番yamlをベースに改善パラメータだけを
上書きし、公正な比較（同一サイジング・同一コスト前提）で真に改善するかを確認する。
"""
import copy
import csv
import subprocess
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "backlog5" / "cfg6_prodcmp"
WORK.mkdir(parents=True, exist_ok=True)
OUT = REPO / "ml" / "backlog5" / "prodcompare_results.csv"
XM = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}

# (候補名, ベースyaml, 上書きパラメータ, model)
CANDIDATES = [
    ("RSI_GBPUSD_BB20", "configs/rsi_robust_gbpusd_h4.yaml",
     {"BB_Deviation": 2.0}, "open_prices"),
    ("RSI_GBPUSD_BB20_Range25", "configs/rsi_robust_gbpusd_h4.yaml",
     {"BB_Deviation": 2.0, "Range_Slope_Max_ATR": 0.25}, "open_prices"),
    ("SCA_GBPJPY_Boost30", "configs/sca_gbpjpy_m15.yaml",
     {"Boost_Mult": 3.0}, "every_tick"),
    ("PB_GBPJPY_Slope08_ATR25", "configs/pullback_gbpjpy_h4.yaml",
     {"MA_Slope_Min_ATR": 0.8, "ATR_SL_Mult": 2.5}, "open_prices"),
    ("PB_GBPJPY_Slope15_RR35", "configs/pullback_gbpjpy_h4.yaml",
     {"MA_Slope_Min_ATR": 1.5, "RR_Ratio": 3.5}, "open_prices"),
    ("SCA_USDJPY_StopOrders", "configs/sca_usdjpy_m15.yaml",
     {"UseStopOrders": True}, "every_tick"),
    ("PB_USDJPY_Slope15_RR35", "configs/pullback_usdjpy_h4.yaml",
     {"MA_Slope_Min_ATR": 1.5, "RR_Ratio": 3.5}, "open_prices"),
    ("PB_GBPJPY_RR40", "configs/pullback_gbpjpy_h4.yaml",
     {"RR_Ratio": 4.0}, "open_prices"),
]

# ベースライン（現行本番パラメータそのまま）も同時に同一条件で回して比較基準にする
BASELINE_SUFFIX = "_BASE"


def load_base(path):
    with open(REPO / path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_cfg(name, base_path, overrides, model, win):
    cfg = copy.deepcopy(load_base(base_path))
    p = cfg["parameters"]
    for k, v in overrides.items():
        p[k] = v
    p["ResultFileName"] = "%s_%s_r.csv" % (name, win)
    cfg["model"] = model
    cfg["from_date"], cfg["to_date"] = WINDOWS[win]
    cfg["report_name"] = "%s_%s" % (name, win)
    path = WORK / ("%s_%s.yaml" % (name, win))
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    return path


def summary(run_name):
    f = REPO / "results" / run_name / "summary.csv"
    if not f.exists():
        return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


def run_one(name, base_path, overrides, model, win):
    run_name = "%s_%s" % (name, win)
    r = summary(run_name)
    if r is not None:
        return r
    path = build_cfg(name, base_path, overrides, model, win)
    try:
        subprocess.run([MT5BT, "run", str(path)], cwd=str(REPO),
                       capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        pass
    r = summary(run_name)
    if r is None:
        subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
        time.sleep(2)
    return r


def main():
    out_rows = []
    t0 = time.time()
    for name, base_path, overrides, model in CANDIDATES:
        # ベースライン（現行本番パラメータ）
        base_i = run_one(name + BASELINE_SUFFIX, base_path, {}, model, "IS")
        base_o = run_one(name + BASELINE_SUFFIX, base_path, {}, model, "OOS")
        # 改善候補
        cand_i = run_one(name, base_path, overrides, model, "IS")
        cand_o = run_one(name, base_path, overrides, model, "OOS")
        row = {"name": name, "base": base_path, "overrides": str(overrides), "model": model}
        for tag, r in (("base_is", base_i), ("base_oos", base_o),
                       ("cand_is", cand_i), ("cand_oos", cand_o)):
            row[tag + "_net"] = r["net"] if r else ""
            row[tag + "_pf"] = r["pf"] if r else ""
            row[tag + "_n"] = r["n"] if r else ""
        out_rows.append(row)
        ok = cand_i and cand_o and cand_i["net"] > 0 and cand_o["net"] > 0
        print("%-28s base IS=%8s OOS=%8s | cand IS=%8s OOS=%8s %s"
              % (name,
                 "%.0f" % base_i["net"] if base_i else "N/A",
                 "%.0f" % base_o["net"] if base_o else "N/A",
                 "%.0f" % cand_i["net"] if cand_i else "N/A",
                 "%.0f" % cand_o["net"] if cand_o else "N/A",
                 "**両+**" if ok else ""), flush=True)
        fieldnames = list(row.keys())
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for rr in out_rows:
                w.writerow(rr)
    print("\nTOTAL %.1f min" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
