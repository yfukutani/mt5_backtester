# -*- coding: utf-8 -*-
"""採用候補2機構を、現行本番相当条件で逐次実測する。

--regression-only は OFF/HOLD64/COOL12 の IS/OOS を測り、既存dealログの
SHA-256と照合する。既定実行は残りを含む全12条件を再開可能な形で測る。
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from run_all2 import (
    BASE_CONFIG,
    COMMON_FILES,
    EA_SOURCE,
    MT5BT,
    deal_metrics,
    driver_lock,
    kill_orphan_testers,
    process_names,
    read_summary,
    run_command,
    verify_runtime,
)


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "gold_dd2"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "deals"
LOG_DIR = ROOT / "logs"
OUT = ROOT / "combo2_verify_v2.csv"

CASES: dict[str, dict[str, Any]] = {
    "OFF": {"GoldLabMode": 0, "GoldLabMode2": 0},
    "HOLD64": {"GoldLabMode": 24, "GoldLabMode2": 0, "GoldLabPBHoldBars": 64},
    "COOL12": {"GoldLabMode": 3, "GoldLabMode2": 0, "GoldLabPortfolioCooldownHours": 12},
    "BOTH": {"GoldLabMode": 24, "GoldLabMode2": 3, "GoldLabPBHoldBars": 64,
             "GoldLabPortfolioCooldownHours": 12},
}
SCOPES = {
    "GOLD2_IS": {"window": "IS", "crypto": False, "from": "2021.06.21", "to": "2026.06.20"},
    "GOLD2_OOS": {"window": "OOS", "crypto": False, "from": "2016.06.21", "to": "2021.06.20"},
    "XM5_FULL": {"window": "XM5", "crypto": True, "from": "2016.11.09", "to": "2026.06.20"},
}
EXPECTED_SHA256 = {
    ("OFF", "GOLD2_IS"): "EF56DBFF7FED514534ED5228C911125D188928B810FCD8541C5174F45FDC2331",
    ("OFF", "GOLD2_OOS"): "886EC460BB89E27A11DA68DACCB08213B7D871EB7679C350CAA3526C7BDFBE62",
    ("OFF", "XM5_FULL"): "70A67875C852E59FF91E8F7468B45B78D39609E1404DA76562ECB3C605DCC4B0",
    ("HOLD64", "GOLD2_IS"): "E7660A703D91B7FAB60524B65AE0588291B8A1B53C837668F3DDDFD9BD4C6BB3",
    ("HOLD64", "GOLD2_OOS"): "CFD978DC263DD7729F06F6E71004A1A42C41AF18ADB88D02F43E8259B89A3C86",
    ("HOLD64", "XM5_FULL"): "AAE31D2463C75C92425B5DE9485A26B3F751230AC9165E7D654D11A7A2E6E7D9",
    ("COOL12", "GOLD2_IS"): "FD3DA436C4DBCB202B5D46A9EA886C038D28460C4AE36833C93AF9E6382D6931",
    ("COOL12", "GOLD2_OOS"): "651872F342BFF435B24336617F7DECDAF214390E6327354666FF180571BD0FDD",
    ("COOL12", "XM5_FULL"): "C86F8D94B49AC5CE5971CFB6B19EDB2D506811A5BFDAF1DDC635F808533DB1D2",
}
FIELDS = [
    "scope", "case", "run_id", "from_date", "to_date", "net", "pf", "dd_pct", "trades",
    "deal_rows", "deal_sha256", "expected_sha256", "regression_pass", "pb_rows", "sca_rows",
    "eth_rows", "funding_rows", "bfx_rows", "magic_gate_pass", "ea_sha256", "parameters",
    "config_file", "deal_file", "elapsed_seconds",
]
WATCHED = {"terminal64.exe", "metatester64.exe", "mt5bt.exe"}


def read_rows() -> list[dict[str, str]]:
    if not OUT.exists():
        return []
    with OUT.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save_rows(rows: list[dict[str, Any]]) -> None:
    tmp = OUT.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, OUT)


def ensure_idle() -> None:
    busy = sorted(process_names() & WATCHED)
    if busy:
        raise RuntimeError("MT5実行前プロセス不在ゲート失敗: " + ",".join(busy))


def cleanup_after_run(timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while True:
        busy = process_names() & WATCHED
        if not busy:
            return
        if busy == {"metatester64.exe"}:
            if not kill_orphan_testers():
                raise RuntimeError("孤立metatester64.exeを停止できませんでした")
            time.sleep(2)
            continue
        if time.monotonic() >= deadline:
            raise TimeoutError("MT5終了待ちタイムアウト: " + ",".join(sorted(busy)))
        time.sleep(5)


def cached_row(rows: list[dict[str, str]], case: str, scope: str, ea_sha: str) -> dict[str, str] | None:
    for row in reversed(rows):
        if row.get("case") != case or row.get("scope") != scope or row.get("ea_sha256") != ea_sha:
            continue
        deal = REPO / row["deal_file"]
        if deal.is_file() and hashlib.sha256(deal.read_bytes()).hexdigest().upper() == row.get("deal_sha256"):
            return row
    return None


def make_config(case: str, scope: str, run_id: str) -> tuple[dict[str, Any], str]:
    spec = SCOPES[scope]
    config = copy.deepcopy(BASE_CONFIG)
    config["from_date"], config["to_date"] = spec["from"], spec["to"]
    config["report_name"] = run_id
    config["parameters"].update(CASES[case])
    config["parameters"].update({
        "En_ETH": spec["crypto"], "En_BTC_FUND": spec["crypto"], "En_BFXREV": spec["crypto"],
        "ResultFileName": run_id + "_result.csv", "EquityLogFile": run_id + "_deals.csv",
    })
    return config, run_id + "_deals.csv"


def execute(case: str, scope: str, rows: list[dict[str, Any]], ea_sha: str) -> dict[str, Any]:
    cached = cached_row(rows, case, scope, ea_sha)
    if cached:
        print(f"SKIP {scope:10s} {case:7s} SHA={cached['deal_sha256']}", flush=True)
        return cached

    ensure_idle()
    run_id = f"combo2v2_{case.lower()}_{scope.lower()}"
    config, deal_name = make_config(case, scope, run_id)
    config_path = CONFIG_DIR / f"{run_id}.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    common_deal = COMMON_FILES / deal_name
    local_deal = DEAL_DIR / deal_name
    common_deal.unlink(missing_ok=True)
    started = time.monotonic()
    timeout = 4200 if scope == "XM5_FULL" else 2700
    command = [str(MT5BT), "run", str(config_path), "--timeout", str(timeout), "--no-charts", "--no-html"]
    returncode = run_command(command, LOG_DIR / f"{run_id}.log", timeout + 120)
    cleanup_after_run()
    if returncode != 0:
        raise RuntimeError(f"mt5bt returned {returncode}: {run_id}")
    if not common_deal.is_file() or common_deal.stat().st_size == 0:
        raise FileNotFoundError(f"dealログがありません: {common_deal}")
    shutil.copyfile(common_deal, local_deal)
    summary = read_summary(run_id)
    deals = deal_metrics(local_deal)
    required = ("pb_rows", "sca_rows", "eth_rows", "funding_rows", "bfx_rows") if scope == "XM5_FULL" else ("pb_rows", "sca_rows")
    magic_gate = all(int(deals[name]) > 0 for name in required)
    expected = EXPECTED_SHA256.get((case, scope), "")
    regression = deals["deal_sha256"] == expected if expected else ""
    row: dict[str, Any] = {
        "scope": scope, "case": case, "run_id": run_id,
        "from_date": SCOPES[scope]["from"], "to_date": SCOPES[scope]["to"],
        **summary, **deals, "expected_sha256": expected, "regression_pass": regression,
        "magic_gate_pass": magic_gate, "ea_sha256": ea_sha,
        "parameters": json.dumps(CASES[case], ensure_ascii=False, sort_keys=True),
        "config_file": str(config_path.relative_to(REPO)), "deal_file": str(local_deal.relative_to(REPO)),
        "elapsed_seconds": f"{time.monotonic() - started:.3f}",
    }
    rows[:] = [old for old in rows if not (old.get("case") == case and old.get("scope") == scope)]
    rows.append(row)
    save_rows(rows)
    print(f"DONE {scope:10s} {case:7s} net={summary['net']:.2f} PF={summary['pf']:.4f} "
          f"DD={summary['dd_pct']:.4f}% n={summary['trades']} SHA={deals['deal_sha256']} "
          f"reg={regression} magic={magic_gate}", flush=True)
    if not magic_gate:
        raise RuntimeError(f"必須magicゲート失敗: {scope}/{case}")
    if expected and not regression:
        raise RuntimeError(f"deal SHA-256回帰失敗: {scope}/{case}")
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regression-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for directory in (CONFIG_DIR, DEAL_DIR, LOG_DIR, COMMON_FILES):
        directory.mkdir(parents=True, exist_ok=True)
    verify_runtime()
    ensure_idle()
    ea_sha = hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest().upper()
    rows: list[dict[str, Any]] = read_rows()
    cases = ("OFF", "HOLD64", "COOL12") if args.regression_only else tuple(CASES)
    scopes = ("GOLD2_IS", "GOLD2_OOS") if args.regression_only else tuple(SCOPES)
    with driver_lock():
        for case in cases:
            for scope in scopes:
                execute(case, scope, rows, ea_sha)
    print(f"保存: {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
