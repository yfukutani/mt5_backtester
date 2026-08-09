# -*- coding: utf-8 -*-
"""Step3(b): 既存EAパラメータの範囲内でテスト可能な応答曲面のみを対象にした検証。
Codexの50提案のうち、新規EA機能開発（アーム有効期限・段階サイジング等）を必要とする項目は
対象外（別途の開発タスクとして切り出す）。IS/OOS両ゲートを最初から適用する。
"""
import copy
import csv
import subprocess
import time
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "step3b" / "cfg"
WORK.mkdir(parents=True, exist_ok=True)
OUT = REPO / "ml" / "step3b" / "results.csv"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}


def load_yaml(relative):
    with (REPO / relative).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


CANDIDATES = []


def add(cid, family, base_yaml, overrides, model=None, note=""):
    CANDIDATES.append({"id": cid, "family": family, "base": base_yaml,
                        "overrides": overrides, "model": model, "note": note})


# 10: PB USDJPY 現行点近傍（Slope x RR、SL=2.0固定）
for slope in (1.0, 1.2, 1.4):
    for rr in (1.8, 2.0, 2.2):
        add(f"P10_{slope}_{rr}", "PB_USDJPY_local", "configs/pullback_usdjpy_h4.yaml",
            {"MA_Slope_Min_ATR": slope, "RR_Ratio": rr})

# 11: PB GBPJPY 採用後パラメータ(1.5,3.5)近傍
for slope in (1.3, 1.5, 1.7):
    for rr in (3.0, 3.5, 4.0):
        add(f"P11_{slope}_{rr}", "PB_GBPJPY_local", "configs/pullback_gbpjpy_h4.yaml",
            {"MA_Slope_Min_ATR": slope, "RR_Ratio": rr})

# 26: SCA GBPJPY Boost倍率3.5の追加点（2.5/3.0は既存tier2で確認済み）
add("P26_boost35", "SCA_GBPJPY_boost", "configs/sca_gbpjpy_m15.yaml",
    {"Boost_Mult": 3.5}, model="every_tick")

# 36: Carry AUDJPY ヒステリシス幅xMA期間 現行(0.75,200)近傍
for hyst in (0.5, 0.75, 1.0):
    for ma in (180, 200, 220):
        add(f"P36_{hyst}_{ma}", "Carry_AUDJPY_local", "configs/carry_audjpy_d1.yaml",
            {"Hyst_ATR_Mult": hyst, "TrendMA_Period": ma})

# 38: VBO USDJPY every_tick再基準化（現行open_prices成績の実費再測定・単一点）
add("P38_baseline", "VBO_USDJPY_everytick", "configs/vbo_usdjpy_h4.yaml",
    {}, model="every_tick")

# 40: VBO USDJPY チャネルxトレール局所面（every_tick）
for ch in (15, 20, 25):
    for tr in (2.5, 3.0, 3.5):
        add(f"P40_{ch}_{tr}", "VBO_USDJPY_local", "configs/vbo_usdjpy_h4.yaml",
            {"Channel_Period": ch, "Trail_Mult": tr}, model="every_tick")

# 43: PairTrade Entry_Z x Exit_Z 現行(4.0,-1.0)近傍（Stop_Z=5固定）
for ez in (3.5, 4.0, 4.5):
    for xz in (-0.5, -1.0, -1.5):
        add(f"P43_{ez}_{xz}", "PairTrade_local", "configs/pairtrade_eurusd_gbpusd.yaml",
            {"Entry_Z": ez, "Exit_Z": xz})


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


def build_cfg(cand, win):
    base = copy.deepcopy(load_yaml(cand["base"]))
    p = base["parameters"]
    p.update(cand["overrides"])
    name = "%s_%s" % (cand["id"], win)
    p["ResultFileName"] = name + "_r.csv"
    base["from_date"], base["to_date"] = WINDOWS[win]
    if cand["model"]:
        base["model"] = cand["model"]
    base["report_dir"] = "results"
    base["report_name"] = name
    path = WORK / (name + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(base, fh, allow_unicode=True, sort_keys=False)
    return path


def run_one(cand, win):
    name = "%s_%s" % (cand["id"], win)
    r = summary(name)
    if r is not None:
        return r
    path = build_cfg(cand, win)
    try:
        subprocess.run([MT5BT, "run", str(path)], cwd=str(REPO),
                       capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        pass
    r = summary(name)
    if r is None:
        subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
        time.sleep(2)
    return r


def main():
    out_rows = []
    if OUT.exists():
        out_rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
    done_ids = {r["id"] for r in out_rows}

    t0 = time.time()
    survivors = []
    for i, cand in enumerate(CANDIDATES, 1):
        if cand["id"] in done_ids:
            continue
        ri = run_one(cand, "IS")
        ro = run_one(cand, "OOS")
        if ri is None or ro is None:
            verdict = "FAIL"
            print("[%3d/%d] %-14s %-24s FAIL" % (i, len(CANDIDATES), cand["id"], cand["family"]), flush=True)
            out_rows.append({**cand, "overrides": str(cand["overrides"]),
                              "is_net": "", "is_pf": "", "oos_net": "", "oos_pf": "", "verdict": verdict})
        else:
            ok = ri["net"] > 0 and ro["net"] > 0
            if ok:
                survivors.append(cand["id"])
            print("[%3d/%d] %-14s %-24s IS=%+8.0f(pf%.2f) OOS=%+8.0f(pf%.2f) %s"
                  % (i, len(CANDIDATES), cand["id"], cand["family"],
                     ri["net"], ri["pf"], ro["net"], ro["pf"], "**両+**" if ok else ""), flush=True)
            out_rows.append({**cand, "overrides": str(cand["overrides"]),
                              "is_net": ri["net"], "is_pf": ri["pf"], "is_n": ri["n"],
                              "oos_net": ro["net"], "oos_pf": ro["pf"], "oos_n": ro["n"],
                              "verdict": "PASS" if ok else "reject"})
        fieldnames = ["id", "family", "base", "overrides", "model", "note",
                      "is_net", "is_pf", "is_n", "oos_net", "oos_pf", "oos_n", "verdict"]
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for rr in out_rows:
                w.writerow({k: rr.get(k, "") for k in fieldnames})

    print("\nTOTAL %.1f min survivors=%d" % ((time.time() - t0) / 60, len(survivors)))
    print("survivors:", survivors)


if __name__ == "__main__":
    main()
