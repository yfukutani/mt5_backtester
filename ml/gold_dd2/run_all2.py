"""GOLD DD round-2: serial, resumable actual-MT5 measurement driver.

The driver never post-processes trades into hypothetical variants.  Every
proposal is activated in MIX_EA_SIMVERIFY and measured by a real MT5 run.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "gold_dd2"
SOURCE_PROPOSALS = REPO / "ml" / "gold_dd" / "proposals.csv"
RESULTS = ROOT / "results.csv"
UNVERIFIED = ROOT / "unverified.csv"
CONFIG_DIR = ROOT / "configs"
LOG_DIR = ROOT / "logs"
DEAL_DIR = ROOT / "deals"
PROGRESS = ROOT / "run_all2.log"
LOCK = ROOT / "run_all2.lock"
EA_SOURCE = REPO / "experts" / "MIX_EA_SIMVERIFY.mq5"
MT5BT = REPO / "mt5bt.bat"
MT5_PATH = Path(r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe")
COMMON_FILES = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "MetaQuotes" / "Terminal" / "Common" / "Files"

WINDOWS = {
    "IS": ("2021.06.21", "2026.06.20"),
    "OOS": ("2016.06.21", "2021.06.20"),
    "XM5": ("2016.11.09", "2026.06.20"),
}
OFF_REFERENCE = {
    "IS": {"net": 2394.57, "pf": 1.9489, "dd": 15.2162, "trades": 307,
           "sha256": "5B93B3C88151C2EE1555DE70DF899A0EEC83E8D339A9972D684A14347FB15DBC"},
    "OOS": {"net": 579.46, "pf": 1.4161, "dd": 12.4321, "trades": 318,
            "sha256": "1D4C5CA14C874C2268EEAF4F5A8DF2C6A452B13EA9E376A3496E8E8DE2495FAE"},
}
BASELINE = {
    "IS": {"net": 2429.34, "pf": 1.9860, "dd": 12.3039, "trades": 305,
           "sha256": "EF56DBFF7FED514534ED5228C911125D188928B810FCD8541C5174F45FDC2331"},
    "OOS": {"net": 647.28, "pf": 1.4886, "dd": 12.0079, "trades": 315,
            "sha256": "886EC460BB89E27A11DA68DACCB08213B7D871EB7679C350CAA3526C7BDFBE62"},
}
MAGICS = {"pb": 20260640, "sca": 20261002, "eth": 20260710,
          "funding": 20260720, "bfx": 20260724}
STALE_TESTER_SECONDS = 300
XM5_TIMEOUT = 3600

# The mode number is part of the EA/driver contract.  It also makes a zero-valued
# variation distinguishable from default OFF, which MT5 SET handling cannot do.
FAMILY_ACTIVATION: dict[str, dict[str, Any]] = {
    "sca_one_direction": {"GoldLabMode": 1},
    "sca_failed_break": {"GoldLabMode": 2},
    "portfolio_loss_cooldown": {"GoldLabMode": 3},
    "sca_range_end": {"GoldLabMode": 4},
    "pb_breakeven": {"GoldLabMode": 5},
    "pb_trailing": {"GoldLabMode": 6},
    "sca_range_start": {"GoldLabMode": 7},
    "range_regime": {"GoldLabMode": 8},
    "gap_regime": {"GoldLabMode": 9},
    "spread_gate": {"GoldLabMode": 10},
    "equity_overlap_cap": {"GoldLabMode": 11},
    "sleeve_loss_cooldown": {"GoldLabMode": 12},
    "daily_loss_cap": {"GoldLabMode": 13},
    "weekly_loss_cap": {"GoldLabMode": 14},
    "overlap_opposite": {"GoldLabMode": 15},
    "pb_ema_pair": {"GoldLabMode": 16},
    "pb_trend_ma": {"GoldLabMode": 17},
    "overlap_direction": {"GoldLabMode": 18},
    "overlap_mutex": {"GoldLabMode": 19},
    "overlap_priority_pb": {"GoldLabMode": 20},
    "overlap_priority_sca": {"GoldLabMode": 21},
    "pb_extension_cap": {"GoldLabMode": 22},
    "pb_higher_tf": {"GoldLabMode": 23},
    "pb_hold_limit": {"GoldLabMode": 24},
    "pb_pullback_depth": {"GoldLabMode": 25},
    "pb_adx_period": {"GoldLabMode": 26},
    "pb_candle_body": {"GoldLabMode": 27},
    "pb_close_location": {"GoldLabMode": 28},
}

BASE_CONFIG: dict[str, Any] = {
    "mt5_path": str(MT5_PATH), "expert": "MIX_EA_SIMVERIFY", "symbol": "GOLD",
    "period": "M15", "deposit": 900, "currency": "USD", "leverage": 25,
    "model": "every_tick", "report_dir": "results",
    "parameters": {
        "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
        "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
        "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
        "En_VBO": False, "En_ETH": False, "En_BTC_FUND": False,
        "En_BFXREV": False, "En_SCA_GOLD": True, "En_SCA_USDJPY": False,
        "En_SCA_GBPJPY": False, "FundUseWebRequest": False, "BfxUseWebRequest": False,
        "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
        # Adopted RR values and adopted PB GOLD entry-hour gate.
        "GoldDDMode": 2, "GoldDDPBRR": 1.8, "GoldDDSCARR": 1.7,
        "GoldHourGateMode": 1,
        "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
        "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
        "GoldHourSCAWeekMask1": 0, "GoldHourSCAStart1": 0, "GoldHourSCAEnd1": 0,
        "GoldHourSCAWeekMask2": 0, "GoldHourSCAStart2": 0, "GoldHourSCAEnd2": 0,
        "GoldLabMode": 0, "GoldLabMode2": 0,
    },
}

RESULT_FIELDS = [
    "attempt_id", "run_id", "proposal_id", "family", "window", "scope", "status",
    "decision", "gate_code", "reason", "returncode", "net", "pf", "dd_pct", "trades",
    "deal_rows", "deal_sha256", "effective_lots", "baseline_lots", "lot_step_verified",
    "pb_rows", "sca_rows", "eth_rows", "funding_rows", "bfx_rows", "magic_gate_pass",
    "regression_pass", "ea_sha256", "parameter_json", "config_file", "deal_file", "from_date", "to_date",
    "started_at", "finished_at", "elapsed_seconds", "error",
]
UNVERIFIED_FIELDS = ["proposal_id", "family", "status", "reason", "parameter_json"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def progress(message: str) -> None:
    line = f"{utc_now()} {message}"
    print(line, flush=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    with PROGRESS.open("a", encoding="utf-8", newline="") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def atomic_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def ensure_outputs() -> None:
    for path, fields in ((RESULTS, RESULT_FIELDS), (UNVERIFIED, UNVERIFIED_FIELDS)):
        if not path.exists() or path.stat().st_size == 0:
            atomic_csv(path, [], fields)
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            old_fields = reader.fieldnames or []
            rows = list(reader)
        if old_fields != fields:
            if not set(old_fields).issubset(fields):
                raise RuntimeError(f"schema mismatch: {path}")
            atomic_csv(path, rows, fields)


def append_result(row: dict[str, Any]) -> None:
    clean = {field: row.get(field, "") for field in RESULT_FIELDS}
    with RESULTS.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=RESULT_FIELDS).writerow(clean)
        handle.flush()
        os.fsync(handle.fileno())


def ea_inputs() -> set[str]:
    text = EA_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*input\s+\w+\s+(\w+)", text, re.M))


def terminal_data_dir() -> Path:
    root = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal"
    wanted = str(MT5_PATH.parent).lower()
    for child in root.iterdir():
        origin = child / "origin.txt"
        if not origin.exists():
            continue
        value = ""
        for encoding in ("utf-16", "utf-8", "cp932"):
            try:
                value = origin.read_text(encoding=encoding).strip().lower()
                break
            except UnicodeError:
                pass
        if value == wanted:
            return child
    raise FileNotFoundError(f"terminal data directory not found for {MT5_PATH.parent}")


def verify_runtime() -> None:
    if not MT5_PATH.is_file():
        raise FileNotFoundError(f"terminal64.exe not found: {MT5_PATH}")
    if not MT5BT.is_file():
        raise FileNotFoundError(f"mt5bt launcher not found: {MT5BT}")
    installed = terminal_data_dir() / "MQL5" / "Experts"
    source = installed / EA_SOURCE.name
    binary = installed / EA_SOURCE.with_suffix(".ex5").name
    if not source.is_file() or not binary.is_file():
        raise FileNotFoundError("installed SIMVERIFY source/binary missing")
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(EA_SOURCE.read_bytes()).digest():
        raise RuntimeError("installed SIMVERIFY source differs from repository source; compile/install first")
    if binary.stat().st_mtime < source.stat().st_mtime:
        raise RuntimeError("installed SIMVERIFY ex5 is older than mq5; compile first")
    known = ea_inputs()
    required = {"GoldLabMode", "GoldLabMode2", "GoldDDPBRR", "GoldDDSCARR", "GoldHourGateMode"}
    for activation in FAMILY_ACTIVATION.values():
        required.update(activation)
    missing = sorted(required - known)
    if missing:
        raise RuntimeError("EA inputs missing: " + ",".join(missing))


def command_text(command: list[str]) -> str:
    """Capture short Windows utility output through a file, never a pipe."""
    with tempfile.TemporaryFile(mode="w+b") as output:
        subprocess.run(command, stdout=output, stderr=output, stdin=subprocess.DEVNULL)
        output.seek(0)
        return output.read().decode("utf-8", errors="replace")


def process_names() -> set[str]:
    output = command_text(["tasklist", "/NH", "/FO", "CSV"])
    return {row[0].lower() for row in csv.reader(output.splitlines()) if row}


def pid_running(pid: int) -> bool:
    output = command_text(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"])
    return any(len(row) > 1 and row[1].isdigit() and int(row[1]) == pid
               for row in csv.reader(output.splitlines()))


def kill_orphan_testers() -> bool:
    result = subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL)
    return result.returncode == 0


def wait_for_mt5(timeout: int | None, poll_seconds: int) -> None:
    started = time.monotonic()
    last_notice = -60.0
    watched = {"terminal64.exe", "metatester64.exe", "mt5bt.exe"}
    while True:
        busy = sorted(process_names() & watched)
        if not busy:
            return
        elapsed = time.monotonic() - started
        if busy == ["metatester64.exe"] and elapsed >= STALE_TESTER_SECONDS:
            if kill_orphan_testers():
                progress(f"KILL_ORPHAN_TESTER elapsed={elapsed:.0f}s")
                started = time.monotonic()
                last_notice = -60.0
                time.sleep(poll_seconds)
                continue
        if elapsed - last_notice >= 60:
            progress(f"WAIT_MT5 elapsed={elapsed:.0f}s processes={','.join(busy)}")
            last_notice = elapsed
        if timeout is not None and elapsed >= timeout:
            raise TimeoutError(f"MT5 wait timed out: {','.join(busy)}")
        time.sleep(poll_seconds)


def run_command(command: list[str], log_path: Path, timeout: int) -> int:
    """Redirect to a file: never create a pipe inherited by metatester64."""
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(5)
        if proc.poll() is not None:
            return int(proc.returncode)
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL)
        kill_orphan_testers()
        raise subprocess.TimeoutExpired(command, timeout)


@contextmanager
def driver_lock() -> Iterable[None]:
    ROOT.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        detail = LOCK.read_text(encoding="ascii", errors="replace")
        match = re.search(r"pid=(\d+)", detail)
        if match and pid_running(int(match.group(1))):
            raise RuntimeError(f"another run_all2 is active: {detail.strip()}") from exc
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, f"pid={os.getpid()} started={utc_now()}\n".encode("ascii"))
        os.close(fd)
        yield
    finally:
        LOCK.unlink(missing_ok=True)


def read_summary(run_id: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    path = REPO / "results" / run_id / "summary.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2:
                values[row[0]] = row[1]
    return {"net": float(values["純利益"]), "pf": float(values["プロフィットファクター"]),
            "dd_pct": float(values["最大相対DD%"]), "trades": int(values["総取引数"])}


def deal_metrics(path: Path) -> dict[str, Any]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"empty deal log: {path}")
    counts = {name: 0 for name in MAGICS}
    lots: set[float] = set()
    for row in rows:
        magic = int(float(row.get("magic", 0) or 0))
        volume = float(row.get("volume", 0) or 0)
        if volume > 0:
            lots.add(volume)
        for name, expected in MAGICS.items():
            if magic == expected:
                counts[name] += 1
    return {"deal_rows": len(rows),
            "deal_sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            "effective_lots": "|".join(f"{lot:.2f}" for lot in sorted(lots)),
            **{f"{name}_rows": count for name, count in counts.items()}}


def latest_rows() -> dict[tuple[str, str, str], dict[str, str]]:
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in read_csv(RESULTS):
        latest[(row["proposal_id"], row["window"], row["scope"])] = row
    return latest


def regression_match(window: str, summary: dict[str, Any], deals: dict[str, Any],
                     production_gate: bool) -> tuple[bool, str]:
    base = (BASELINE if production_gate else OFF_REFERENCE)[window]
    checks = {
        "net": abs(summary["net"] - base["net"]) < 0.005,
        "pf": abs(summary["pf"] - base["pf"]) < 0.00005,
        "dd": abs(summary["dd_pct"] - base["dd"]) < 0.00005,
        "trades": summary["trades"] == base["trades"],
        "deal_sha256": deals["deal_sha256"] == base["sha256"],
    }
    failed = [key for key, passed in checks.items() if not passed]
    label = "production-gate ON" if production_gate else "OFF"
    return not failed, f"exact {label} regression" if not failed else "mismatch: " + ",".join(failed)


def numeric_reason(window: str, value: dict[str, Any], base: dict[str, Any]) -> str:
    return (f"{window} net={value['net']:.2f} ({value['net']/base['net']:.4f}x), "
            f"PF={value['pf']:.4f} ({value['pf']/base['pf']:.4f}x), "
            f"DD={value['dd_pct']:.4f}% ({value['dd_pct']/base['dd']:.4f}x); "
            f"baseline net={base['net']:.2f}, PF={base['pf']:.4f}, DD={base['dd']:.4f}%")


def classify_is(value: dict[str, Any]) -> tuple[str, str, str]:
    base = BASELINE["IS"]
    nr, pr, dr = value["net"] / base["net"], value["pf"] / base["pf"], value["dd_pct"] / base["dd"]
    reason = numeric_reason("IS", value, base)
    if abs(nr - 1) < 1e-7 and abs(pr - 1) < 1e-7 and abs(dr - 1) < 1e-7:
        return "IS_REJECT", "BASELINE_EQUIVALENT", reason
    if value["net"] <= base["net"] and value["pf"] <= base["pf"] and value["dd_pct"] >= base["dd"]:
        return "IS_REJECT", "DOMINATED", reason
    if nr < 0.75 and dr > 0.80:
        return "IS_REJECT", "PROFIT_LOSS", reason
    if pr < 0.80:
        return "IS_REJECT", "PF_LOSS", reason
    if value["net"] > base["net"] and value["pf"] > base["pf"] and value["dd_pct"] <= base["dd"]:
        return "IS_SURVIVOR_STRICT", "STRICT", reason
    return "IS_SURVIVOR_TRADEOFF", "NOT_CLEARLY_INFERIOR", reason


def strict_both(is_row: dict[str, str], oos: dict[str, Any]) -> bool:
    return (float(is_row["net"]) > BASELINE["IS"]["net"] and
            float(is_row["pf"]) > BASELINE["IS"]["pf"] and
            float(is_row["dd_pct"]) <= BASELINE["IS"]["dd"] and
            oos["net"] > BASELINE["OOS"]["net"] and
            oos["pf"] > BASELINE["OOS"]["pf"] and
            oos["dd_pct"] <= BASELINE["OOS"]["dd"])


def proposal_changes_lot(parameters: dict[str, Any]) -> bool:
    return any("lot" in key.lower() or "boostmult" in key.lower() for key in parameters)


def make_config(parameters: dict[str, Any], activation: dict[str, Any], window: str,
                run_id: str) -> tuple[dict[str, Any], str]:
    cfg = copy.deepcopy(BASE_CONFIG)
    cfg["parameters"].update(activation)
    cfg["parameters"].update(parameters)
    if window == "XM5":
        cfg["parameters"].update({"En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True})
    from_date, to_date = WINDOWS[window]
    deal_name = run_id + "_deals.csv"
    cfg.update({"from_date": from_date, "to_date": to_date, "report_name": run_id})
    cfg["parameters"].update({"ResultFileName": run_id + "_result.csv", "EquityLogFile": deal_name})
    return cfg, deal_name


def execute(proposal: dict[str, str], window: str, args: argparse.Namespace,
            regression: bool = False, production_gate: bool = False) -> dict[str, Any]:
    pid = ("BASELINE_PRODUCTION" if production_gate else "BASELINE_OFF") if regression else proposal["id"]
    family = "regression" if regression else proposal["family"]
    scope = "XM5" if window == "XM5" else "GOLD2"
    attempt = uuid.uuid4().hex
    generation = "gdd2" if regression else "gdd2p"
    run_id = f"{generation}_{window.lower()}_{pid.lower()}_{datetime.now():%Y%m%d%H%M%S}_{attempt[:6]}"
    rec: dict[str, Any] = {"attempt_id": attempt, "run_id": run_id, "proposal_id": pid,
                           "family": family, "window": window, "scope": scope,
                           "ea_sha256": hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest().upper(),
                           "started_at": utc_now(), "from_date": WINDOWS[window][0],
                           "to_date": WINDOWS[window][1]}
    started = time.monotonic()
    progress(f"RUN_START id={pid} family={family} window={window} run={run_id}")
    try:
        parameters = {} if regression else json.loads(proposal["parameter_json"])
        activation = {"GoldLabMode": 0} if regression else FAMILY_ACTIVATION[family]
        unknown = sorted((set(parameters) | set(activation)) - ea_inputs())
        if unknown:
            raise NotImplementedError("SIMVERIFY input missing: " + ",".join(unknown))
        cfg, deal_name = make_config(parameters, activation, window, run_id)
        if regression and not production_gate:
            cfg["parameters"]["GoldHourGateMode"] = 0
        config_path = CONFIG_DIR / f"{run_id}.yaml"
        config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        common_deal, local_deal = COMMON_FILES / deal_name, DEAL_DIR / deal_name
        common_deal.unlink(missing_ok=True)
        rec.update({"parameter_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                    "config_file": str(config_path.relative_to(REPO)),
                    "deal_file": str(local_deal.relative_to(REPO)),
                    "baseline_lots": "0.01|0.02|0.05" if window == "XM5" else "0.01|0.02"})
        if not MT5_PATH.is_file():
            raise FileNotFoundError(f"terminal64.exe not found before launch: {MT5_PATH}")
        wait_for_mt5(args.terminal_wait_timeout, args.poll_seconds)
        timeout = XM5_TIMEOUT if window == "XM5" else args.run_timeout
        command = [str(MT5BT), "run", str(config_path), "--timeout", str(timeout),
                   "--no-charts", "--no-html"]
        rec["returncode"] = run_command(command, LOG_DIR / f"{run_id}.log", timeout + 120)
        if rec["returncode"] != 0:
            raise RuntimeError(f"mt5bt returned {rec['returncode']}")
        if not common_deal.is_file() or common_deal.stat().st_size == 0:
            raise FileNotFoundError(f"FILE_COMMON deal log missing: {common_deal}")
        shutil.copyfile(common_deal, local_deal)
        summary, deals = read_summary(run_id), deal_metrics(local_deal)
        rec.update(summary)
        rec.update(deals)
        required_magics = ("pb_rows", "sca_rows", "eth_rows", "funding_rows", "bfx_rows") if window == "XM5" else ("pb_rows", "sca_rows")
        rec["magic_gate_pass"] = all(int(rec[name]) > 0 for name in required_magics)
        if not rec["magic_gate_pass"]:
            rec.update({"status": "UNVERIFIED", "decision": "UNVERIFIED_MAGIC_GATE",
                        "gate_code": "MAGIC_MISSING",
                        "reason": "required magic counts: " + ", ".join(f"{name}={rec[name]}" for name in required_magics)})
        elif regression:
            passed, reason = regression_match(window, summary, deals, production_gate)
            rec.update({"regression_pass": passed, "status": "OK" if passed else "INVALID",
                        "decision": "REGRESSION_PASS" if passed else "REGRESSION_FAIL",
                        "gate_code": "SHA256_EXACT" if passed else "REGRESSION_MISMATCH", "reason": reason})
        else:
            lot_sensitive = proposal_changes_lot(parameters)
            rec["lot_step_verified"] = (not lot_sensitive) or rec["effective_lots"] != rec["baseline_lots"]
            if lot_sensitive and not rec["lot_step_verified"]:
                rec.update({"status": "UNVERIFIED", "decision": "UNVERIFIED_LOTSTEP",
                            "gate_code": "EFFECTIVE_LOTS_UNCHANGED",
                            "reason": f"effective lots remained {rec['effective_lots']} (baseline {rec['baseline_lots']})"})
            elif window == "IS":
                decision, code, reason = classify_is(summary)
                rec.update({"status": "OK", "decision": decision, "gate_code": code, "reason": reason})
            elif window == "OOS":
                is_row = latest_rows()[(pid, "IS", "GOLD2")]
                strict = strict_both(is_row, summary)
                rec.update({"status": "OK", "decision": "OOS_STRICT_PASS" if strict else "OOS_REJECT",
                            "gate_code": "STRICT_BOTH" if strict else "ADOPTION_CONDITION_FAILED",
                            "reason": numeric_reason("OOS", summary, BASELINE["OOS"])})
            else:
                rec.update({"status": "OK", "decision": "XM5_MEASURED", "gate_code": "MAGIC_PASS",
                            "reason": "actual XM5 run; all required magics present"})
    except NotImplementedError as exc:
        rec.update({"status": "UNVERIFIED", "decision": "UNVERIFIED_EA_INPUT",
                    "gate_code": "EA_INPUT_MISSING", "reason": str(exc), "error": repr(exc)})
        rows = read_csv(UNVERIFIED)
        rows.append({"proposal_id": pid, "family": family, "status": "UNVERIFIED_EA_INPUT",
                     "reason": str(exc), "parameter_json": proposal.get("parameter_json", "")})
        atomic_csv(UNVERIFIED, rows, UNVERIFIED_FIELDS)
    except subprocess.TimeoutExpired as exc:
        rec.update({"status": "FAILED", "decision": "RUN_FAILED", "gate_code": "TIMEOUT",
                    "reason": str(exc), "error": repr(exc)})
    except Exception as exc:
        rec.update({"status": "FAILED", "decision": "RUN_FAILED", "gate_code": type(exc).__name__,
                    "reason": str(exc), "error": traceback.format_exc(limit=8)})
    rec["finished_at"] = utc_now()
    rec["elapsed_seconds"] = f"{time.monotonic() - started:.3f}"
    append_result(rec)
    progress(f"RUN_END id={pid} window={window} status={rec['status']} decision={rec['decision']} elapsed={rec['elapsed_seconds']}s")
    return rec


def completed(row: dict[str, str] | None, args: argparse.Namespace) -> bool:
    if not row:
        return False
    if row.get("ea_sha256") != hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest().upper():
        return False
    if row.get("proposal_id") not in {"BASELINE_OFF", "BASELINE_PRODUCTION"} and not row.get("run_id", "").startswith("gdd2p_"):
        return False
    if args.retry_failed and row.get("status") in {"FAILED", "INVALID"}:
        return False
    if args.retry_unverified and row.get("status") == "UNVERIFIED":
        return False
    return True


def regression_ready(latest: dict[tuple[str, str, str], dict[str, str]]) -> bool:
    digest = hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest().upper()
    return all(latest.get((pid, window, "GOLD2"), {}).get("regression_pass") == "True" and
               latest.get((pid, window, "GOLD2"), {}).get("ea_sha256") == digest
               for pid in ("BASELINE_OFF", "BASELINE_PRODUCTION") for window in ("IS", "OOS"))


def select_proposals(args: argparse.Namespace) -> list[dict[str, str]]:
    rows = [row for row in read_csv(SOURCE_PROPOSALS) if row.get("family") in FAMILY_ACTIVATION]
    if args.family:
        rows = [row for row in rows if row["family"] in set(args.family)]
    if args.proposal_id:
        rows = [row for row in rows if row["id"] in set(args.proposal_id)]
    return rows


def run_queue(args: argparse.Namespace) -> None:
    latest = latest_rows()
    if not regression_ready(latest):
        digest = hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest().upper()
        for pid, production_gate in (("BASELINE_OFF", False), ("BASELINE_PRODUCTION", True)):
            for window in ("IS", "OOS"):
                key = (pid, window, "GOLD2")
                if (latest.get(key, {}).get("regression_pass") == "True" and
                        latest.get(key, {}).get("ea_sha256") == digest):
                    progress(f"SKIP_REGRESSION id={pid} window={window}")
                    continue
                result = execute({}, window, args, regression=True, production_gate=production_gate)
                latest[key] = {k: str(v) for k, v in result.items()}
                if result.get("decision") != "REGRESSION_PASS":
                    raise RuntimeError(f"regression failed for {pid}/{window}; proposal runs are blocked")
    selected = select_proposals(args)
    stages = {"all": ("IS", "OOS", "XM5"), "is": ("IS",), "oos": ("OOS",), "xm5": ("XM5",)}[args.stage]
    started = skipped = 0
    for ordinal, proposal in enumerate(selected, 1):
        pid = proposal["id"]
        for window in stages:
            scope = "XM5" if window == "XM5" else "GOLD2"
            key = (pid, window, scope)
            if completed(latest.get(key), args):
                skipped += 1
                progress(f"SKIP_EXISTING [{ordinal}/{len(selected)}] id={pid} window={window}")
                continue
            is_row = latest.get((pid, "IS", "GOLD2"))
            oos_row = latest.get((pid, "OOS", "GOLD2"))
            if window == "OOS" and not (is_row and is_row.get("status") == "OK" and is_row.get("decision", "").startswith("IS_SURVIVOR")):
                progress(f"GATE_SKIP id={pid} window=OOS reason=IS_NOT_SURVIVOR")
                continue
            if window == "XM5" and not (oos_row and oos_row.get("status") == "OK" and oos_row.get("decision") == "OOS_STRICT_PASS"):
                progress(f"GATE_SKIP id={pid} window=XM5 reason=OOS_NOT_STRICT")
                continue
            if args.dry_run:
                progress(f"DRY_RUN [{ordinal}/{len(selected)}] id={pid} window={window}")
                continue
            if args.limit is not None and started >= args.limit:
                progress(f"LIMIT_REACHED actual_proposal_runs={started}")
                progress(f"QUEUE_SUMMARY selected={len(selected)} started={started} skipped={skipped}")
                return
            result = execute(proposal, window, args)
            started += 1
            latest[key] = {k: str(v) for k, v in result.items()}
            if result.get("status") in {"FAILED", "UNVERIFIED", "INVALID"}:
                break
    progress(f"QUEUE_SUMMARY selected={len(selected)} started={started} skipped={skipped}")


def self_check() -> None:
    proposals = [row for row in read_csv(SOURCE_PROPOSALS) if row.get("family") in FAMILY_ACTIVATION]
    if len(proposals) != 560 or len({row["family"] for row in proposals}) != 28:
        raise AssertionError(f"target registry mismatch: rows={len(proposals)}, families={len(set(row['family'] for row in proposals))}")
    known = ea_inputs()
    missing: dict[str, list[str]] = {}
    for row in proposals:
        keys = set(json.loads(row["parameter_json"])) | set(FAMILY_ACTIVATION[row["family"]])
        absent = sorted(keys - known)
        if absent:
            missing[row["id"]] = absent
    if missing:
        raise AssertionError(f"proposal inputs missing: {missing}")
    valid = REPO / "ml" / "gold_dd" / "deals" / "gdd_xm5_full_off_ethfix_20260814_x1_deals.csv"
    invalid = REPO / "ml" / "gold_dd" / "deals" / "gdd_xm5_full_mutex_x1_deals.csv"
    good, bad = deal_metrics(valid), deal_metrics(invalid)
    if not all(good[f"{name}_rows"] > 0 for name in ("eth", "funding", "bfx")):
        raise AssertionError("known valid XM5 deal log failed magic gate")
    if bad["eth_rows"] > 0:
        raise AssertionError("known ETH-missing deal log was not rejected")
    print(json.dumps({"self_check": "OK", "target_rows": 560, "families": 28,
                      "valid_magic_counts": {name: good[f"{name}_rows"] for name in ("eth", "funding", "bfx")},
                      "invalid_magic_counts": {name: bad[f"{name}_rows"] for name in ("eth", "funding", "bfx")}},
                     ensure_ascii=False), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "is", "oos", "xm5"), default="all")
    parser.add_argument("--family", action="append")
    parser.add_argument("--proposal-id", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-timeout", type=int, default=2400)
    parser.add_argument("--terminal-wait-timeout", type=int, default=None)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-unverified", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for directory in (ROOT, CONFIG_DIR, LOG_DIR, DEAL_DIR, COMMON_FILES):
        directory.mkdir(parents=True, exist_ok=True)
    ensure_outputs()
    verify_runtime()
    if args.self_check:
        self_check()
        return 0
    with driver_lock():
        progress(f"DRIVER_START pid={os.getpid()} stage={args.stage} targets={len(select_proposals(args))}")
        run_queue(args)
        progress("DRIVER_END status=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
