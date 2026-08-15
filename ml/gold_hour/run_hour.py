"""Resumable serial driver for the GOLD weekday x entry-hour experiment.

All variants are actual MIX_EA_SIMVERIFY backtests.  Deal logs are only used
for regression/magic verification; trades are never removed after a run.

Typical background run:
    python ml/gold_hour/run_hour.py

Small smoke run (the regression gate always runs first):
    python ml/gold_hour/run_hour.py --limit 3
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
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "gold_hour"
CONFIG_DIR = ROOT / "configs"
LOG_DIR = ROOT / "logs"
DEAL_DIR = ROOT / "deals"
RESULTS = ROOT / "results.csv"
ASSESSMENT = ROOT / "assessment.csv"
PROGRESS = ROOT / "run_hour.log"
LOCK = ROOT / "run_hour.lock"
MT5BT = REPO / "mt5bt.bat"
EA_SOURCE = REPO / "experts" / "MIX_EA_SIMVERIFY.mq5"
MT5_PATH = Path(r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe")
COMMON_FILES = (
    Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    / "MetaQuotes" / "Terminal" / "Common" / "Files"
)

PB_MAGIC = 20260640
SCA_MAGIC = 20261002
XM5_MAGICS = {"PB_GOLD": PB_MAGIC, "SCA_GOLD": SCA_MAGIC,
              "ETH": 20260710, "BTC_FUND": 20260720, "BFXREV": 20260724}
WINDOWS = {
    "IS": ("2021.06.21", "2026.06.20"),
    "OOS": ("2016.06.21", "2021.06.20"),
    "XM5": ("2016.11.09", "2026.06.20"),
}

# Pre-hour-gate reference, measured with the already-compiled SIMVERIFY EA and
# the adopted PB RR=1.8 / SCA RR=1.7 overrides.  A new Mode=0 build must be
# byte-for-byte identical at the deal-log level before any grid run is valid.
REGRESSION_REFERENCE = {
    "IS": {
        "net": 2394.57, "pf": 1.9489, "dd": 15.2162, "trades": 307,
        "deal_sha256": "5B93B3C88151C2EE1555DE70DF899A0EEC83E8D339A9972D684A14347FB15DBC",
    },
    "OOS": {
        "net": 579.46, "pf": 1.4161, "dd": 12.4321, "trades": 318,
        "deal_sha256": "1D4C5CA14C874C2268EEAF4F5A8DF2C6A452B13EA9E376A3496E8E8DE2495FAE",
    },
}

BASE_CONFIG: dict[str, Any] = {
    "mt5_path": str(MT5_PATH),
    "expert": "MIX_EA_SIMVERIFY",
    "symbol": "GOLD",
    "period": "M15",
    "deposit": 900,
    "currency": "USD",
    "leverage": 25,
    "model": "every_tick",
    "parameters": {
        "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
        "En_PB_GOLD": True,
        "En_RSI_USDJPY": False, "En_RSI_EURUSD": False, "En_RSI_GBPUSD": False,
        "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
        "En_ETH": False, "En_BTC_FUND": False, "En_BFXREV": False,
        "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
        "FundUseWebRequest": False, "BfxUseWebRequest": False,
        "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
        # Use the newly adopted GOLD RR values without changing production EAs.
        "GoldDDMode": 2, "GoldDDPBRR": 1.8, "GoldDDSCARR": 1.7,
        "GoldHourGateMode": 0,
    },
    "report_dir": "results",
}

RESULT_FIELDS = [
    "attempt_id", "run_id", "candidate_id", "label", "kind", "window", "scope",
    "status", "decision", "reason", "returncode", "net", "pf", "dd_pct", "trades",
    "deal_rows", "deal_sha256", "pb_rows", "sca_rows", "eth_rows", "funding_rows",
    "bfx_rows", "magic_gate_pass", "regression_pass", "rules_json", "config_file",
    "deal_file", "started_at", "finished_at", "elapsed_seconds", "error",
]

ASSESSMENT_FIELDS = [
    "candidate_id", "label", "kind", "rules_json",
    "is_net", "is_pf", "is_dd_pct", "oos_net", "oos_pf", "oos_dd_pct",
    "is_delta_net", "is_delta_pf", "is_delta_dd", "oos_delta_net",
    "oos_delta_pf", "oos_delta_dd", "net_signs", "pf_signs", "dd_signs",
    "sign_consistent", "strict_both", "xm5_eligible", "xm5_status",
    "xm5_net", "xm5_pf", "xm5_dd_pct", "reason",
]


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    label: str
    kind: str
    pb: tuple[tuple[int, int, int], ...] = ()
    sca: tuple[tuple[int, int, int], ...] = ()

    def rules(self) -> dict[str, list[list[int]]]:
        return {"pb": [list(x) for x in self.pb], "sca": [list(x) for x in self.sca]}


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


def atomic_write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def ensure_results() -> None:
    if not RESULTS.exists() or RESULTS.stat().st_size == 0:
        atomic_write_csv(RESULTS, [], RESULT_FIELDS)
        return
    with RESULTS.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != RESULT_FIELDS:
            raise RuntimeError("results.csv schema mismatch; preserve it and migrate explicitly")


def append_result(row: dict[str, Any]) -> None:
    clean = {field: row.get(field, "") for field in RESULT_FIELDS}
    with RESULTS.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=RESULT_FIELDS).writerow(clean)
        handle.flush()
        os.fsync(handle.fileno())


def process_names() -> set[str]:
    result = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True,
                            text=True, errors="replace")
    return {row[0].lower() for row in csv.reader(result.stdout.splitlines()) if row}


def pid_running(pid: int) -> bool:
    result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                            capture_output=True, text=True, errors="replace")
    return any(len(row) > 1 and row[1].isdigit() and int(row[1]) == pid
               for row in csv.reader(result.stdout.splitlines()))


def wait_for_mt5(timeout: int | None, poll_seconds: int) -> None:
    """Never start while another terminal/tester/mt5bt process is present."""
    started = time.monotonic()
    last_notice = -60.0
    watched = {"terminal64.exe", "metatester64.exe", "mt5bt.exe"}
    while True:
        busy = sorted(process_names() & watched)
        if not busy:
            return
        elapsed = time.monotonic() - started
        if elapsed - last_notice >= 60:
            progress(f"WAIT_MT5 elapsed={elapsed:.0f}s processes={','.join(busy)}")
            last_notice = elapsed
        if timeout is not None and elapsed >= timeout:
            raise TimeoutError(f"MT5 wait timed out: {','.join(busy)}")
        time.sleep(poll_seconds)


@contextmanager
def driver_lock() -> Iterable[None]:
    ROOT.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        detail = LOCK.read_text(encoding="ascii", errors="replace")
        match = re.search(r"pid=(\d+)", detail)
        if match and pid_running(int(match.group(1))):
            raise RuntimeError(f"another run_hour driver is active: {detail.strip()}") from exc
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, f"pid={os.getpid()} started={utc_now()}\n".encode("ascii"))
        os.close(fd)
        yield
    finally:
        LOCK.unlink(missing_ok=True)


def terminal_data_dir() -> Path:
    terminals = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal"
    wanted = str(MT5_PATH.parent).lower()
    for child in terminals.iterdir():
        origin = child / "origin.txt"
        if not origin.exists():
            continue
        for encoding in ("utf-16", "utf-8", "cp932"):
            try:
                value = origin.read_text(encoding=encoding).strip().lower()
                break
            except UnicodeError:
                value = ""
        if value == wanted:
            return child
    raise FileNotFoundError(f"terminal data directory not found for {MT5_PATH.parent}")


def verify_compiled_ea() -> None:
    source = EA_SOURCE.read_text(encoding="utf-8")
    required = {"GoldHourGateMode", "GoldHourPBWeekMask1", "GoldHourSCAWeekMask1"}
    missing = sorted(name for name in required if name not in source)
    if missing:
        raise RuntimeError(f"repository EA inputs missing: {','.join(missing)}")
    experts = terminal_data_dir() / "MQL5" / "Experts"
    installed_source = experts / EA_SOURCE.name
    installed_binary = experts / EA_SOURCE.with_suffix(".ex5").name
    if not installed_source.exists() or not installed_binary.exists():
        raise FileNotFoundError("installed SIMVERIFY source/binary missing; compile it first")
    installed_text = installed_source.read_text(encoding="utf-8")
    if any(name not in installed_text for name in required):
        raise RuntimeError("installed SIMVERIFY source does not contain the hour-gate inputs")
    if installed_binary.stat().st_mtime < installed_source.stat().st_mtime:
        raise RuntimeError("installed SIMVERIFY ex5 is older than mq5; compile it first")


def primary_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    sessions = (("TOKYO", 0, 7), ("EU_AM", 7, 12), ("EU_PM", 12, 16),
                ("NY", 16, 20), ("NY_LATE", 20, 24))
    for day_name, day_mask, day_jp in (("MON", 2, "月"), ("FRI", 32, "金")):
        for session, start, end in sessions:
            rule = ((day_mask, start, end),)
            for sleeve in ("PB", "SCA", "BOTH"):
                candidates.append(Candidate(
                    f"{day_name}_{session}_{sleeve}", f"{day_jp}曜 {start:02d}-{end-1:02d}時台 {sleeve}", "session",
                    rule if sleeve in {"PB", "BOTH"} else (),
                    rule if sleeve in {"SCA", "BOTH"} else (),
                ))
    for day_name, day_mask, day_jp, kind in (
        ("WED", 8, "水", "weekday_candidate"),
        ("MON", 2, "月", "weekday_reference"),
        ("FRI", 32, "金", "weekday_reference"),
    ):
        rule = ((day_mask, 0, 24),)
        for sleeve in ("PB", "SCA", "BOTH"):
            candidates.append(Candidate(
                f"{day_name}_ALL_{sleeve}", f"{day_jp}曜終日 {sleeve}", kind,
                rule if sleeve in {"PB", "BOTH"} else (),
                rule if sleeve in {"SCA", "BOTH"} else (),
            ))
    return candidates


def rule_parameters(candidate: Candidate) -> dict[str, Any]:
    if len(candidate.pb) > 2 or len(candidate.sca) > 2:
        raise ValueError(f"too many EA rule slots: {candidate.candidate_id}")
    params: dict[str, Any] = {"GoldHourGateMode": 1}
    for sleeve, rules in (("PB", candidate.pb), ("SCA", candidate.sca)):
        for slot in (1, 2):
            mask, start, end = rules[slot - 1] if len(rules) >= slot else (0, 0, 0)
            params[f"GoldHour{sleeve}WeekMask{slot}"] = mask
            params[f"GoldHour{sleeve}Start{slot}"] = start
            params[f"GoldHour{sleeve}End{slot}"] = end
    return params


def make_config(candidate: Candidate, window: str, run_id: str) -> tuple[dict[str, Any], str]:
    config = copy.deepcopy(BASE_CONFIG)
    crypto = window == "XM5"
    if candidate.candidate_id == "BASELINE_OFF":
        config["parameters"]["GoldHourGateMode"] = 0
    else:
        config["parameters"].update(rule_parameters(candidate))
    if crypto:
        config["parameters"].update({"En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True})
    from_date, to_date = WINDOWS[window]
    deal_name = run_id + "_deals.csv"
    config.update({"from_date": from_date, "to_date": to_date, "report_name": run_id})
    config["parameters"].update({"ResultFileName": run_id + "_result.csv", "EquityLogFile": deal_name})
    return config, deal_name


def read_summary(run_id: str) -> dict[str, Any]:
    path = REPO / "results" / run_id / "summary.csv"
    values: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2:
                values[row[0]] = row[1]
    return {"net": float(values["純利益"]), "pf": float(values["プロフィットファクター"]),
            "dd_pct": float(values["最大相対DD%"]), "trades": int(values["総取引数"])}


def deal_metrics(path: Path) -> dict[str, Any]:
    rows = read_csv(path)
    counts = {name: 0 for name in XM5_MAGICS}
    for row in rows:
        magic = int(float(row.get("magic", 0) or 0))
        for name, expected in XM5_MAGICS.items():
            if magic == expected:
                counts[name] += 1
    return {
        "deal_rows": len(rows), "deal_sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        "pb_rows": counts["PB_GOLD"], "sca_rows": counts["SCA_GOLD"],
        "eth_rows": counts["ETH"], "funding_rows": counts["BTC_FUND"], "bfx_rows": counts["BFXREV"],
    }


def run_command(command: list[str], log_path: Path, timeout: int) -> int:
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           capture_output=True, text=True, errors="replace")
            raise


def latest_rows() -> dict[tuple[str, str, str], dict[str, str]]:
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in read_csv(RESULTS):
        latest[(row["candidate_id"], row["window"], row["scope"])] = row
    return latest


def regression_ok(rows: dict[tuple[str, str, str], dict[str, str]]) -> bool:
    return all(rows.get(("BASELINE_OFF", window, "GOLD2"), {}).get("regression_pass") == "True"
               for window in ("IS", "OOS"))


def regression_match(window: str, summary: dict[str, Any], deals: dict[str, Any]) -> tuple[bool, str]:
    expected = REGRESSION_REFERENCE[window]
    checks = {
        "net": abs(summary["net"] - expected["net"]) < 0.005,
        "pf": abs(summary["pf"] - expected["pf"]) < 0.00005,
        "dd": abs(summary["dd_pct"] - expected["dd"]) < 0.00005,
        "trades": summary["trades"] == expected["trades"],
        "deal_sha256": deals["deal_sha256"] == expected["deal_sha256"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    return not failed, "exact OFF regression" if not failed else "mismatch: " + ",".join(failed)


def execute_one(candidate: Candidate, window: str, args: argparse.Namespace) -> dict[str, Any]:
    scope = "XM5" if window == "XM5" else "GOLD2"
    attempt = uuid.uuid4().hex
    run_id = f"gh_{window.lower()}_{candidate.candidate_id.lower()}_{datetime.now():%Y%m%d%H%M%S}_{attempt[:6]}"
    rec: dict[str, Any] = {
        "attempt_id": attempt, "run_id": run_id, "candidate_id": candidate.candidate_id,
        "label": candidate.label, "kind": candidate.kind, "window": window, "scope": scope,
        "rules_json": json.dumps(candidate.rules(), ensure_ascii=False, separators=(",", ":")),
        "started_at": utc_now(),
    }
    started = time.monotonic()
    progress(f"RUN_START candidate={candidate.candidate_id} window={window} run={run_id}")
    try:
        config, deal_name = make_config(candidate, window, run_id)
        config_path = CONFIG_DIR / f"{run_id}.yaml"
        config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        common_deal = COMMON_FILES / deal_name
        local_deal = DEAL_DIR / deal_name
        common_deal.unlink(missing_ok=True)
        rec.update({"config_file": str(config_path.relative_to(REPO)),
                    "deal_file": str(local_deal.relative_to(REPO))})
        wait_for_mt5(args.terminal_wait_timeout, args.poll_seconds)
        timeout = args.xm5_timeout if window == "XM5" else args.run_timeout
        command = [str(MT5BT), "run", str(config_path), "--timeout", str(timeout),
                   "--no-charts", "--no-html"]
        rec["returncode"] = run_command(command, LOG_DIR / f"{run_id}.log", timeout + 120)
        if rec["returncode"] != 0:
            raise RuntimeError(f"mt5bt returned {rec['returncode']}")
        if not common_deal.exists() or common_deal.stat().st_size == 0:
            raise FileNotFoundError(f"FILE_COMMON deal log missing: {common_deal}")
        shutil.copyfile(common_deal, local_deal)
        summary = read_summary(run_id)
        deals = deal_metrics(local_deal)
        rec.update(summary)
        rec.update(deals)
        if window == "XM5":
            magic_pass = all(deals[field] > 0 for field in
                             ("pb_rows", "sca_rows", "eth_rows", "funding_rows", "bfx_rows"))
        else:
            magic_pass = deals["pb_rows"] > 0 and deals["sca_rows"] > 0
        rec["magic_gate_pass"] = magic_pass
        if not magic_pass:
            rec.update({"status": "UNVERIFIED", "decision": "MAGIC_GATE_FAILED",
                        "reason": "one or more required sleeve magics are absent"})
        elif candidate.candidate_id == "BASELINE_OFF":
            passed, reason = regression_match(window, summary, deals)
            rec.update({"regression_pass": passed, "status": "OK" if passed else "INVALID",
                        "decision": "REGRESSION_PASS" if passed else "REGRESSION_FAIL", "reason": reason})
        else:
            rec.update({"status": "OK", "decision": "MEASURED", "reason": "actual EA backtest"})
    except Exception as exc:
        rec.update({"status": "FAILED", "decision": "RUN_FAILED", "reason": str(exc),
                    "error": traceback.format_exc(limit=8)})
    rec["finished_at"] = utc_now()
    rec["elapsed_seconds"] = f"{time.monotonic() - started:.3f}"
    append_result(rec)
    rebuild_assessment(primary_candidates())
    progress(f"RUN_END candidate={candidate.candidate_id} window={window} status={rec['status']} decision={rec['decision']}")
    return rec


def as_float(row: dict[str, str], field: str) -> float:
    return float(row[field])


def sign(value: float, tolerance: float = 1e-9) -> int:
    return 1 if value > tolerance else -1 if value < -tolerance else 0


def assessment_rows(candidates: list[Candidate]) -> list[dict[str, Any]]:
    latest = latest_rows()
    baselines = {w: latest.get(("BASELINE_OFF", w, "GOLD2")) for w in ("IS", "OOS")}
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        is_row = latest.get((candidate.candidate_id, "IS", "GOLD2"))
        oos_row = latest.get((candidate.candidate_id, "OOS", "GOLD2"))
        xm_row = latest.get((candidate.candidate_id, "XM5", "XM5"))
        out: dict[str, Any] = {
            "candidate_id": candidate.candidate_id, "label": candidate.label, "kind": candidate.kind,
            "rules_json": json.dumps(candidate.rules(), ensure_ascii=False, separators=(",", ":")),
            "xm5_status": xm_row.get("status", "") if xm_row else "",
            "xm5_net": xm_row.get("net", "") if xm_row else "",
            "xm5_pf": xm_row.get("pf", "") if xm_row else "",
            "xm5_dd_pct": xm_row.get("dd_pct", "") if xm_row else "",
        }
        for prefix, row in (("is", is_row), ("oos", oos_row)):
            if row and row.get("status") == "OK":
                out[f"{prefix}_net"] = row.get("net", "")
                out[f"{prefix}_pf"] = row.get("pf", "")
                out[f"{prefix}_dd_pct"] = row.get("dd_pct", "")
        if not (is_row and oos_row and baselines["IS"] and baselines["OOS"] and
                is_row.get("status") == oos_row.get("status") == "OK"):
            out.update({"sign_consistent": False, "strict_both": False, "xm5_eligible": False,
                        "reason": "IS/OOS measurement incomplete"})
            output.append(out)
            continue
        deltas: dict[str, float] = {}
        for window, row in (("is", is_row), ("oos", oos_row)):
            base = baselines[window.upper()]
            for metric, field in (("net", "net"), ("pf", "pf"), ("dd", "dd_pct")):
                value = as_float(row, field)
                delta = value - as_float(base, field)
                out[f"{window}_{field}"] = value
                out[f"{window}_delta_{metric}"] = delta
                deltas[f"{window}_{metric}"] = delta
        out["net_signs"] = f"{sign(deltas['is_net'])}/{sign(deltas['oos_net'])}"
        out["pf_signs"] = f"{sign(deltas['is_pf'])}/{sign(deltas['oos_pf'])}"
        out["dd_signs"] = f"{sign(deltas['is_dd'])}/{sign(deltas['oos_dd'])}"
        sign_consistent = (
            sign(deltas["is_net"]) == sign(deltas["oos_net"]) != 0 and
            sign(deltas["is_pf"]) == sign(deltas["oos_pf"]) != 0 and
            ((deltas["is_dd"] <= 0 and deltas["oos_dd"] <= 0) or
             (deltas["is_dd"] > 0 and deltas["oos_dd"] > 0))
        )
        # Strict adoption gate: net/PF improve in both periods and DD is no worse
        # in either, after the independent IS/OOS direction gate has passed.
        strict = (deltas["is_net"] > 0 and deltas["oos_net"] > 0 and
                  deltas["is_pf"] > 0 and deltas["oos_pf"] > 0 and
                  deltas["is_dd"] <= 0 and deltas["oos_dd"] <= 0 and sign_consistent)
        out.update({"sign_consistent": sign_consistent, "strict_both": strict, "xm5_eligible": strict,
                    "reason": "strict IS/OOS survivor" if strict else "IS/OOS sign or strict gate failed"})
        output.append(out)
    return output


def rebuild_assessment(candidates: list[Candidate]) -> None:
    known = {c.candidate_id: c for c in candidates}
    for row in read_csv(RESULTS):
        cid = row.get("candidate_id", "")
        if cid in known or cid == "BASELINE_OFF" or not cid.startswith("COMBO_"):
            continue
        rules = json.loads(row["rules_json"])
        known[cid] = Candidate(cid, row["label"], "combo",
                               tuple(tuple(x) for x in rules["pb"]),
                               tuple(tuple(x) for x in rules["sca"]))
    atomic_write_csv(ASSESSMENT, assessment_rows(list(known.values())), ASSESSMENT_FIELDS)


def merge_rules(a: tuple[tuple[int, int, int], ...], b: tuple[tuple[int, int, int], ...]) -> tuple[tuple[int, int, int], ...] | None:
    by_hours: dict[tuple[int, int], int] = {}
    for mask, start, end in a + b:
        by_hours[(start, end)] = by_hours.get((start, end), 0) | mask
    merged = tuple((mask, start, end) for (start, end), mask in sorted(by_hours.items()))
    return merged if len(merged) <= 2 else None


def combo_candidates(primary: list[Candidate], max_combos: int) -> list[Candidate]:
    assessments = {row["candidate_id"]: row for row in read_csv(ASSESSMENT)}
    survivors = [c for c in primary if assessments.get(c.candidate_id, {}).get("strict_both") == "True"]
    combos: dict[str, Candidate] = {}
    for index, left in enumerate(survivors):
        for right in survivors[index + 1:]:
            pb = merge_rules(left.pb, right.pb)
            sca = merge_rules(left.sca, right.sca)
            if pb is None or sca is None:
                continue
            signature = json.dumps({"pb": pb, "sca": sca}, separators=(",", ":"))
            digest = hashlib.sha1(signature.encode("ascii")).hexdigest()[:10].upper()
            cid = f"COMBO_{digest}"
            if (pb, sca) in ((left.pb, left.sca), (right.pb, right.sca)):
                continue
            combos[cid] = Candidate(cid, f"{left.candidate_id} + {right.candidate_id}", "combo", pb, sca)
    return sorted(combos.values(), key=lambda c: c.candidate_id)[:max_combos]


def completed(row: dict[str, str] | None, retry_failed: bool) -> bool:
    if not row:
        return False
    if retry_failed and row.get("status") in {"FAILED", "INVALID", "UNVERIFIED"}:
        return False
    return True


def run_queue(items: list[tuple[Candidate, str]], args: argparse.Namespace,
              started: int) -> tuple[int, str | None]:
    latest = latest_rows()
    for candidate, window in items:
        scope = "XM5" if window == "XM5" else "GOLD2"
        if (candidate.candidate_id != "BASELINE_OFF" and args.candidate_id and
                candidate.candidate_id not in args.candidate_id):
            continue
        key = (candidate.candidate_id, window, scope)
        if completed(latest.get(key), args.retry_failed):
            progress(f"SKIP_EXISTING candidate={candidate.candidate_id} window={window}")
            continue
        if args.dry_run:
            progress(f"DRY_RUN candidate={candidate.candidate_id} window={window} rules={candidate.rules()}")
            continue
        if args.limit is not None and started >= args.limit:
            progress(f"LIMIT_REACHED actual_runs={started}")
            return started, "limit"
        result = execute_one(candidate, window, args)
        started += 1
        latest[key] = {k: str(v) for k, v in result.items()}
        if result.get("status") in {"FAILED", "INVALID", "UNVERIFIED"}:
            return started, "failure"
    return started, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("all", "regression", "grid", "combos", "xm5"), default="all")
    parser.add_argument("--candidate-id", action="append", help="restrict candidate ID; repeatable")
    parser.add_argument("--limit", type=int, help="maximum number of newly started MT5 runs")
    parser.add_argument("--max-combos", type=int, default=50)
    parser.add_argument("--run-timeout", type=int, default=2400)
    parser.add_argument("--xm5-timeout", type=int, default=3600)
    parser.add_argument("--terminal-wait-timeout", type=int, default=None)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args()


def self_check() -> None:
    candidates = primary_candidates()
    if len(candidates) != 39 or len({c.candidate_id for c in candidates}) != 39:
        raise AssertionError("expected 39 unique primary candidates")
    for candidate in candidates:
        params = rule_parameters(candidate)
        if params["GoldHourGateMode"] != 1:
            raise AssertionError(candidate.candidate_id)
        if len(candidate.pb) > 2 or len(candidate.sca) > 2:
            raise AssertionError(candidate.candidate_id)
    expected_inputs = set(re.findall(r"^\s*input\s+\w+\s+(\w+)", EA_SOURCE.read_text(encoding="utf-8"), re.M))
    missing = sorted(set(rule_parameters(candidates[0])) - expected_inputs)
    if missing:
        raise AssertionError(f"EA input mismatch: {missing}")
    print(json.dumps({"self_check": "OK", "primary_candidates": len(candidates),
                      "actual_grid_runs": 2 * len(candidates), "serial": True}, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    for directory in (ROOT, CONFIG_DIR, LOG_DIR, DEAL_DIR, COMMON_FILES):
        directory.mkdir(parents=True, exist_ok=True)
    ensure_results()
    if args.self_check:
        self_check()
        return 0
    if not args.dry_run:
        verify_compiled_ea()
    primary = primary_candidates()
    rebuild_assessment(primary)
    with driver_lock():
        progress(f"DRIVER_START pid={os.getpid()} phase={args.phase} primary={len(primary)}")
        started = 0
        baseline = Candidate("BASELINE_OFF", "GoldHourGateMode=0 回帰", "regression")
        if args.phase in {"all", "regression", "grid", "combos", "xm5"}:
            started, stop_reason = run_queue([(baseline, "IS"), (baseline, "OOS")], args, started)
            if stop_reason:
                return 0 if stop_reason == "limit" else 2
        latest = latest_rows()
        if not args.dry_run and not regression_ok(latest):
            raise RuntimeError("OFF regression gate is incomplete or failed; grid is blocked")
        if args.phase in {"all", "grid"}:
            grid = [(candidate, window) for candidate in primary for window in ("IS", "OOS")]
            started, stop_reason = run_queue(grid, args, started)
            if stop_reason:
                return 0 if stop_reason == "limit" else 2
        rebuild_assessment(primary)
        combos = combo_candidates(primary, args.max_combos)
        if args.phase in {"all", "combos"}:
            pair_grid = [(candidate, window) for candidate in combos for window in ("IS", "OOS")]
            started, stop_reason = run_queue(pair_grid, args, started)
            if stop_reason:
                return 0 if stop_reason == "limit" else 2
        all_candidates = primary + combos
        rebuild_assessment(all_candidates)
        if args.phase in {"all", "xm5"}:
            eligible_ids = {row["candidate_id"] for row in read_csv(ASSESSMENT)
                            if row.get("xm5_eligible") == "True"}
            xm5 = [(candidate, "XM5") for candidate in all_candidates
                   if candidate.candidate_id in eligible_ids]
            started, stop_reason = run_queue(xm5, args, started)
            if stop_reason:
                return 0 if stop_reason == "limit" else 2
        rebuild_assessment(all_candidates)
        progress(f"DRIVER_END status=OK actual_runs={started} combos={len(combos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
