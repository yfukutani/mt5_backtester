"""Trade-off 8 combined verification. All MT5 launches are deliberately sequential."""
from __future__ import annotations

import copy
import csv
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "tradeoff8"
CFG = ROOT / "configs"
LOG = ROOT / "logs"
DEALS = ROOT / "deals"
RESULTS = REPO / "results"
EXE = shutil.which("mt5bt") or r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"

PORTFOLIO = [
    "pullback_usdjpy_h4.yaml", "pullback_gbpjpy_h4.yaml", "pullback_audjpy_h4.yaml",
    "rsi_robust_usdjpy_h4.yaml", "rsi_robust_eurusd_h1.yaml", "rsi_robust_gbpusd_h4.yaml",
    "pairtrade_eurusd_gbpusd.yaml", "pullback_gold_h4.yaml", "carry_audjpy_d1.yaml",
    "sca_usdjpy_m15.yaml", "sca_gbpjpy_m15.yaml", "sca_gold_m15.yaml", "eth_ea_d1.yaml",
    "fundingrev_btcusd_d1.yaml", "bfxrev_btcusd_d1.yaml",
]
CHANGES = {
    "sca_gbpjpy_m15.yaml": ("01_sca_gbp", "RangeEndHour", 10),
    "fundingrev_btcusd_d1.yaml": ("02_funding", "Threshold_Pct8h", -0.003),
    "pullback_usdjpy_h4.yaml": ("03_pb_usd", "ADX_Threshold", 27.5),
    "pullback_gbpjpy_h4.yaml": ("04_pb_gbp", "SlowEMA_Period", 35),
    "pullback_audjpy_h4.yaml": ("05_pb_aud", "RR_Ratio", 5.0),
    "rsi_robust_usdjpy_h4.yaml": ("06_rsi_usd", "DP_Tolerance_ATR", 1.5),
    "carry_audjpy_d1.yaml": ("07_carry", "ReentryCooldown", 10),
    "bfxrev_btcusd_d1.yaml": ("08_bfx", "LookbackDays", 10),
}
OLD = {
    "01_sca_gbp": (87562, 41924), "02_funding": (57087, 3081),
    "03_pb_usd": (41850, 3332), "04_pb_gbp": (35946, 20684),
    "05_pb_aud": (6157, 5619), "06_rsi_usd": (7915, 7925),
    "07_carry": (105817, 37325), "08_bfx": (55156, 19376),
}
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}


def load(name: str) -> dict:
    with (REPO / "configs" / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump(data: dict, name: str) -> Path:
    CFG.mkdir(parents=True, exist_ok=True)
    path = CFG / f"{name}.yaml"
    with path.open("w", encoding="utf-8", newline="") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return path


def summary(name: str) -> dict | None:
    p = RESULTS / name / "summary.csv"
    if not p.exists():
        return None
    with p.open(encoding="utf-8-sig", newline="") as f:
        d = {r[0]: r[1] for r in csv.reader(f) if len(r) > 1}
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd_pct": float(d["最大相対DD%"]), "trades": int(float(d["総取引数"]))}
    except (KeyError, ValueError):
        return None


def launch(data: dict, name: str, need_deals: bool = False) -> dict:
    old = summary(name)
    deal_out = DEALS / f"{name}.csv"
    if old is not None and (not need_deals or deal_out.exists()):
        return old
    data = copy.deepcopy(data)
    data["report_dir"] = "results"
    data["report_name"] = name
    data.setdefault("parameters", {})["ResultFileName"] = f"{name}_result.csv"
    if need_deals:
        data["parameters"]["EquityLogFile"] = f"{name}_equity.csv"
    path = dump(data, name)
    LOG.mkdir(parents=True, exist_ok=True)
    q = subprocess.run([EXE, "run", str(path), "--no-charts", "--no-html"], cwd=REPO,
                       capture_output=True, text=True, timeout=3600)
    (LOG / f"{name}.log").write_text(
        f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}", encoding="utf-8")
    out = summary(name)
    if q.returncode or out is None:
        raise RuntimeError(f"MT5 run failed: {name}; see {LOG / (name + '.log')}")
    if need_deals:
        # Runner searches these same tester/common Files locations. Find the unique log by name.
        candidates = list(Path.home().glob(f"AppData/Roaming/MetaQuotes/Terminal/**/MQL5/Files/{name}_equity.csv"))
        candidates += list(Path.home().glob(f"AppData/Roaming/MetaQuotes/Terminal/**/tester/files/{name}_equity.csv"))
        candidates += list(Path.home().glob(f"AppData/Roaming/MetaQuotes/Tester/**/MQL5/Files/{name}_equity.csv"))
        candidates = [p for p in candidates if p.is_file() and p.stat().st_size > 0]
        if not candidates:
            raise RuntimeError(f"equity log missing: {name}")
        DEALS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(max(candidates, key=lambda p: p.stat().st_mtime), deal_out)
    return out


def candidate_config(name: str) -> dict:
    x = load(name)
    if name in CHANGES:
        _, key, value = CHANGES[name]
        x["parameters"][key] = value
    return x


def portfolio(label: str, variants: dict[str, str]) -> dict:
    frames, single_dd, leg_rows = [], [], []
    for name in PORTFOLIO:
        variant = variants.get(name, "baseline")
        run = f"t8_pf_{variant}_{Path(name).stem}"
        p = DEALS / f"{run}.csv"
        df = pd.read_csv(p)
        df.columns = [c.strip().lower() for c in df.columns]
        df["time"] = pd.to_numeric(df["time"], errors="coerce")
        df["profit"] = pd.to_numeric(df["profit"], errors="coerce")
        df = df.dropna(subset=["time", "profit"])[["time", "profit"]]
        eq = pd.concat([pd.Series([100000.0]), 100000.0 + df.sort_values("time")["profit"].cumsum()], ignore_index=True)
        dd = float((eq.cummax() - eq).max())
        frames.append(df); single_dd.append(dd)
        leg_rows.append({"portfolio": label, "config": name, "variant": variant,
                         "deals": len(df), "net": float(df.profit.sum()), "single_dd_abs": dd})
    all_deals = pd.concat(frames, ignore_index=True).sort_values("time", kind="stable")
    initial = 100000.0 * len(PORTFOLIO)
    eq = pd.concat([pd.Series([initial]), initial + all_deals.profit.cumsum()], ignore_index=True)
    peak = eq.cummax(); dd = peak - eq
    max_abs = float(dd.max()); max_pct = float((dd / peak).max() * 100)
    net = float(all_deals.profit.sum()); dd_sum = sum(single_dd)
    ROOT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(leg_rows).to_csv(ROOT / "portfolio_legs.csv", mode="a", index=False,
                                  header=not (ROOT / "portfolio_legs.csv").exists())
    return {"label": label, "net": net, "max_dd_abs": max_abs, "max_dd_pct": max_pct,
            "return_dd_pct": net / max_pct if max_pct else None,
            "return_dd_abs": net / max_abs if max_abs else None,
            "sum_single_dd_abs": dd_sum, "diversification_abs": dd_sum - max_abs,
            "diversification_pct": (1 - max_abs / dd_sum) * 100 if dd_sum else None}


def main() -> None:
    missing = [n for n in PORTFOLIO if not (REPO / "configs" / n).exists()]
    if missing:
        raise FileNotFoundError(missing)
    individual = []
    for filename, (sid, key, value) in CHANGES.items():
        for window, (start, end) in WINDOWS.items():
            x = candidate_config(filename)
            x["from_date"], x["to_date"] = start, end
            if filename == "bfxrev_btcusd_d1.yaml" and window == "OOS": x["from_date"] = "2016.12.01"
            if filename == "fundingrev_btcusd_d1.yaml" and window == "OOS": x["from_date"] = "2019.09.01"
            if filename.startswith("sca_"): x["model"] = "every_tick"
            name = f"t8_ind_{sid}_{window.lower()}"
            r = launch(x, name)
            individual.append({"id": sid, "config": filename, "parameter": key, "value": value,
                               "window": window, "from_date": x["from_date"], "to_date": x["to_date"],
                               "old_net": OLD[sid][0 if window == "IS" else 1], **r})
    pd.DataFrame(individual).to_csv(ROOT / "individual_results.csv", index=False)

    # Only 23 unique full-period legs are required: 15 baseline + 8 changed variants.
    for filename in PORTFOLIO:
        x = load(filename); x["from_date"], x["to_date"], x["deposit"] = "2016.06.21", "2026.06.20", 100000
        if filename == "bfxrev_btcusd_d1.yaml": x["from_date"] = "2016.12.01"
        if filename == "fundingrev_btcusd_d1.yaml": x["from_date"] = "2019.09.01"
        if filename == "eth_ea_d1.yaml": x["from_date"] = "2016.11.01"
        if filename.startswith("sca_"): x["model"] = "every_tick"
        launch(x, f"t8_pf_baseline_{Path(filename).stem}", need_deals=True)
        if filename in CHANGES:
            y = copy.deepcopy(x); _, key, value = CHANGES[filename]; y["parameters"][key] = value
            launch(y, f"t8_pf_candidate_{Path(filename).stem}", need_deals=True)

    legs_path = ROOT / "portfolio_legs.csv"
    if legs_path.exists(): legs_path.unlink()
    base_variants = {}
    cand_variants = {n: "candidate" for n in CHANGES}
    rows = [portfolio("baseline", base_variants), portfolio("candidate_all8", cand_variants)]
    # Exact leave-one-out recombination from the already measured all-deal streams.
    for filename, (sid, _, _) in CHANGES.items():
        v = dict(cand_variants); v.pop(filename)
        rows.append(portfolio(f"loo_without_{sid}", v))
    pd.DataFrame(rows).to_csv(ROOT / "portfolio_results.csv", index=False)
    (ROOT / "run_manifest.json").write_text(json.dumps({"portfolio": PORTFOLIO, "changes": CHANGES},
                                                        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
