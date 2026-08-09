# -*- coding: utf-8 -*-
"""Codex 500案の高優先度5ファミリーを本番同一条件でIS/OOS検証する。"""
from __future__ import annotations

import argparse
import copy
import csv
import shutil
import subprocess
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "ml" / "codex500" / "configs"
OUT = REPO / "ml" / "codex500" / "results.csv"
LOG_DIR = REPO / "ml" / "codex500" / "logs"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
MT5BT_FALLBACK = Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
FIELDS = [
    "id", "family", "base", "overrides", "model",
    "is_net", "is_pf", "is_dd", "is_n",
    "oos_net", "oos_pf", "oos_dd", "oos_n", "verdict",
]


def candidate(cid, family, base, overrides, model="open_prices"):
    return {"id": cid, "family": family, "base": base,
            "overrides": overrides, "model": model}


CANDIDATES = []
for drift in (0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.25):
    CANDIDATES.append(candidate(
        f"A_drift_{drift:g}", "A_SCA_GBPJPY_MinDrift",
        "configs/sca_gbpjpy_m15.yaml", {"Boost_MinDrift_ATRd": drift}, "every_tick"))

for rsi in (10, 12, 14, 18):
    for bb in (16, 20, 24, 30):
        CANDIDATES.append(candidate(
            f"B_rsi_{rsi}_bb_{bb}", "B_RSI_GBPUSD_RSIxBB",
            "configs/rsi_robust_gbpusd_h4.yaml", {"RSI_Period": rsi, "BB_Period": bb}))

for adx in (10, 12, 14, 18):
    for slope_lb in (12, 16, 20, 28):
        CANDIDATES.append(candidate(
            f"C_adx_{adx}_slopeLB_{slope_lb}", "C_PB_GBPJPY_ADXxSlopeLB",
            "configs/pullback_gbpjpy_h4.yaml",
            {"ADX_Period": adx, "MA_Slope_Lookback": slope_lb}))

CARRY_POINTS = (
    (180, 0.5, 10), (180, 0.75, 10), (180, 0.75, 14), (180, 1.0, 20),
    (200, 0.5, 10), (200, 0.5, 14), (200, 0.75, 10), (200, 0.75, 14),
    (200, 0.75, 20), (200, 1.0, 14), (220, 0.5, 14), (220, 0.75, 14),
    (220, 0.75, 20), (240, 0.5, 14), (240, 0.75, 20), (240, 1.0, 20),
)
for ma, hyst, atr in CARRY_POINTS:
    CANDIDATES.append(candidate(
        f"D_ma_{ma}_hyst_{hyst:g}_atr_{atr}", "D_Carry_AUDJPY_MAxHystxATR",
        "configs/carry_audjpy_d1.yaml",
        {"TrendMA_Period": ma, "Hyst_ATR_Mult": hyst, "ATR_Period": atr}))

for lookback in (120, 160, 240, 320):
    for stop_z in (4.5, 5.0, 5.5, 6.0):
        CANDIDATES.append(candidate(
            f"E_lb_{lookback}_stop_{stop_z:g}", "E_PairTrade_LookbackxStopZ",
            "configs/pairtrade_eurusd_gbpusd.yaml",
            {"Lookback": lookback, "Stop_Z": stop_z}))


def mt5bt_command():
    found = shutil.which("mt5bt")
    if found:
        return found
    if MT5BT_FALLBACK.exists():
        return str(MT5BT_FALLBACK)
    raise FileNotFoundError("mt5bt is not on PATH and fallback executable was not found")


def load_yaml(relative):
    with (REPO / relative).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_name(cand, window):
    return f"codex500_{cand['id']}_{window}"


def build_cfg(cand, window):
    cfg = copy.deepcopy(load_yaml(cand["base"]))
    cfg["parameters"].update(cand["overrides"])
    name = run_name(cand, window)
    cfg["parameters"]["ResultFileName"] = name + "_r.csv"
    cfg["from_date"], cfg["to_date"] = WINDOWS[window]
    cfg["model"] = cand["model"]
    cfg["report_dir"] = "results"
    cfg["report_name"] = name
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"{name}.yaml"
    with path.open("w", encoding="utf-8", newline="") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    return path


def summary(name):
    path = REPO / "results" / name / "summary.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8-sig") as fh:
        values = {row[0]: row[1] for row in csv.reader(fh) if len(row) >= 2}
    try:
        return {
            "net": float(values["純利益"]),
            "pf": float(values["プロフィットファクター"]),
            "dd": float(values["最大相対DD%"]),
            "n": int(values["総取引数"]),
        }
    except (KeyError, ValueError):
        return None


def run_one(cand, window):
    name = run_name(cand, window)
    cached = summary(name)
    if cached is not None:
        return cached
    cfg_path = build_cfg(cand, window)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [mt5bt_command(), "run", str(cfg_path)], cwd=str(REPO),
            capture_output=True, text=True, timeout=1800,
        )
        (LOG_DIR / f"{name}.log").write_text(
            f"returncode={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired as exc:
        (LOG_DIR / f"{name}.log").write_text(f"TIMEOUT\n{exc}", encoding="utf-8")
    result = summary(name)
    if result is None:
        # MT5が異常終了時に残った場合だけ解放する。通常時には呼ばれない。
        subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
        time.sleep(2)
    return result


def read_rows():
    if not OUT.exists():
        return []
    with OUT.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_rows(rows):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in FIELDS} for row in rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", action="store_true", help="Aの先頭候補のISだけを試験実行")
    parser.add_argument("--family", choices=list("ABCDE"), help="指定ファミリーだけ実行")
    args = parser.parse_args()

    if args.trial:
        cand = CANDIDATES[0]
        print(f"TRIAL {cand['id']} IS ({cand['model']})", flush=True)
        result = run_one(cand, "IS")
        if result is None:
            raise SystemExit("TRIAL FAILED: summary.csv was not generated or could not be parsed")
        print(f"TRIAL OK: net={result['net']:+.0f} PF={result['pf']:.2f} "
              f"DD={result['dd']:.2f}% trades={result['n']}")
        return

    selected = [c for c in CANDIDATES if not args.family or c["id"].startswith(args.family + "_")]
    rows = read_rows()
    done = {row["id"] for row in rows}
    started = time.time()
    for index, cand in enumerate(selected, 1):
        if cand["id"] in done:
            print(f"[{index:2d}/{len(selected)}] {cand['id']} cached", flush=True)
            continue
        is_result = run_one(cand, "IS")
        oos_result = run_one(cand, "OOS")
        row = {**cand, "overrides": repr(cand["overrides"])}
        for prefix, result in (("is", is_result), ("oos", oos_result)):
            if result:
                for metric in ("net", "pf", "dd", "n"):
                    row[f"{prefix}_{metric}"] = result[metric]
        if is_result is None or oos_result is None:
            row["verdict"] = "UNVERIFIABLE"
        else:
            row["verdict"] = "PASS" if is_result["net"] > 0 and oos_result["net"] > 0 else "reject"
        rows.append(row)
        write_rows(rows)
        is_text = "N/A" if not is_result else f"{is_result['net']:+.0f}(PF{is_result['pf']:.2f})"
        oos_text = "N/A" if not oos_result else f"{oos_result['net']:+.0f}(PF{oos_result['pf']:.2f})"
        print(f"[{index:2d}/{len(selected)}] {cand['id']}: IS={is_text} OOS={oos_text} {row['verdict']}", flush=True)
    print(f"Completed in {(time.time() - started) / 60:.1f} min; output={OUT}")


if __name__ == "__main__":
    main()
