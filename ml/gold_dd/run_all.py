"""Unattended, resumable GOLD DD proposal driver.

Every accepted result comes from an actual MT5 run with the proposal parameter
active.  Deal logs are used for measurement and verification only; they are
never filtered to manufacture proposal variants.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "gold_dd"
CONFIG_DIR = ROOT / "configs"
RUN_LOG_DIR = ROOT / "logs"
DEAL_DIR = ROOT / "deals"
PROPOSALS = ROOT / "proposals.csv"
SCREEN = ROOT / "screen_results.csv"
UNVERIFIED = ROOT / "unverified.csv"
PROGRESS_LOG = ROOT / "run_all.log"
LOCK_FILE = ROOT / "run_all.lock"
COMMON_FILES = (
    Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    / "MetaQuotes" / "Terminal" / "Common" / "Files"
)
MT5BT = REPO / "mt5bt.bat"
VERIFY_EA = REPO / "experts" / "MIX_EA_SIMVERIFY.mq5"

IS_BASE = {"net": 331176.79, "pf": 1.8718825447675405, "dd": 32052.72}
OOS_BASE = {"net": 60050.52, "pf": 1.3961922853288133, "dd": 13806.08}
# Corrected 2016-11-09 start; ETH/BTC-funding/BfxRev magic gate passed.
XM5_BASE = {"net": 538302.83, "pf": 1.85304667671607, "dd": 35671.78}

MAGICS = {"eth": 20260710, "funding": 20260720, "bfx": 20260724}
# metatester64 だけがこの秒数以上残っていたら、前の run の残骸とみなして回収する。
STALE_TESTER_SECONDS = 300
# XM5は5枠×約10年で重い（実測平均855秒）。GOLD2より長い期限を与える。
XM5_RUN_TIMEOUT = 3600
GOLD_BASE_LOTS = "0.01|0.02"
XM5_BASE_LOTS = "0.01|0.02|0.05"

BASE_CONFIG: dict[str, Any] = {
    "mt5_path": r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
    "expert": "MIX_EA_SIMVERIFY",
    "symbol": "GOLD",
    "period": "M15",
    "deposit": 900,
    "currency": "USD",
    "leverage": 25,
    "model": "every_tick",
    "parameters": {
        "En_PB_USDJPY": False,
        "En_PB_GBPJPY": False,
        "En_PB_AUDJPY": False,
        "En_PB_GOLD": True,
        "En_RSI_USDJPY": False,
        "En_RSI_EURUSD": False,
        "En_RSI_GBPUSD": False,
        "En_PAIR": False,
        "En_CARRY": False,
        "En_VBO": False,
        "En_ETH": False,
        "En_BTC_FUND": False,
        "En_BFXREV": False,
        "En_SCA_GOLD": True,
        "En_SCA_USDJPY": False,
        "En_SCA_GBPJPY": False,
        "FundUseWebRequest": False,
        "BfxUseWebRequest": False,
        "SimVerifyMode": 0,
        "R6GoldMode": 0,
        "R6CryptoMode": 0,
    },
    "report_dir": "results",
}

# These families have a real default-OFF implementation in SIMVERIFY today.
# Unknown GoldLab* SET entries must never be sent to MT5: MT5 can ignore them
# silently, which would make many different proposals look baseline-equivalent.
FAMILY_ACTIVATION: dict[str, dict[str, Any]] = {
    "pb_atr_sl": {"GoldDDMode": 2},
    "pb_rr": {"GoldDDMode": 2},
    "pb_adx": {"GoldDDMode": 2},
    "pb_slope": {"GoldDDMode": 2},
    "sca_min_range": {"GoldDDMode": 2},
    "sca_max_range": {"GoldDDMode": 2},
    "sca_buffer": {"GoldDDMode": 2},
    "sca_rr": {"GoldDDMode": 2},
    "sca_boost": {"GoldDDMode": 2, "GoldDDSCAUseBoost": True},
    "sca_trade_end": {"GoldDDMode": 2},
    "sca_force_close": {"GoldDDMode": 2},
    "sca_weekday": {"GoldDDMode": 4},
    "pb_weekday": {"GoldDDMode": 4},
}
LOT_SENSITIVE_FAMILIES = {"sca_boost"}

SCREEN_FIELDS = [
    "attempt_id", "run_id", "proposal_id", "id", "family", "classification",
    "window", "scope", "from_date", "to_date", "crypto_included", "status",
    "decision", "gate_code", "reason", "returncode", "net_jpy", "pf_jpy",
    "dd_amount_jpy", "dd_jpy", "deal_rows", "effective_lots", "baseline_lots",
    "lot_step_verified", "eth_present", "eth_rows", "funding_present",
    "funding_rows", "bfx_present", "bfx_rows", "magic_gate_pass",
    "parameter_json", "equity_log_file", "config_file", "started_at",
    "finished_at", "elapsed_seconds", "error",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_text(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"{utc_now()} {message}\n")
        handle.flush()
        os.fsync(handle.fileno())


def progress(message: str) -> None:
    print(message, flush=True)
    append_text(PROGRESS_LOG, message)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def atomic_write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def ensure_screen_schema() -> None:
    """One-time migration, then all runtime writes are append-only + fsync."""
    if not SCREEN.exists() or SCREEN.stat().st_size == 0:
        atomic_write_csv(SCREEN, [], SCREEN_FIELDS)
        return
    with SCREEN.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        old_fields = reader.fieldnames or []
        rows = list(reader)
    if old_fields == SCREEN_FIELDS:
        return
    migrated: list[dict[str, Any]] = []
    for row in rows:
        r = {field: row.get(field, "") for field in SCREEN_FIELDS}
        r["proposal_id"] = r["proposal_id"] or row.get("id", "")
        r["id"] = r["id"] or r["proposal_id"]
        if r["proposal_id"].startswith("GDD") and not r["scope"]:
            r["scope"] = "GOLD2"
        if not r["decision"]:
            r["decision"] = row.get("decision", "")
        migrated.append(r)
    atomic_write_csv(SCREEN, migrated, SCREEN_FIELDS)
    progress(f"SCREEN_SCHEMA_MIGRATED rows={len(migrated)}")


def append_screen(row: dict[str, Any]) -> None:
    clean = {field: row.get(field, "") for field in SCREEN_FIELDS}
    with SCREEN.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCREEN_FIELDS, extrasaction="ignore")
        writer.writerow(clean)
        handle.flush()
        os.fsync(handle.fileno())


def completed_keys(retry_failed: bool, retry_unverified: bool) -> set[tuple[str, str, str]]:
    done: set[tuple[str, str, str]] = set()
    for row in read_csv(SCREEN):
        pid = row.get("proposal_id") or row.get("id") or ""
        window = row.get("window", "")
        scope = row.get("scope", "") or ("GOLD2" if pid.startswith("GDD") else "")
        if not pid.startswith("GDD") or not window or not scope:
            continue
        status = row.get("status", "")
        decision = row.get("decision", "")
        if retry_failed and status == "FAILED":
            continue
        if retry_unverified and decision.startswith("UNVERIFIED"):
            continue
        done.add((pid, window, scope))
    return done


def proposal_result(pid: str, window: str, scope: str) -> dict[str, str] | None:
    matches = []
    for row in read_csv(SCREEN):
        rid = row.get("proposal_id") or row.get("id") or ""
        rscope = row.get("scope", "") or ("GOLD2" if rid.startswith("GDD") else "")
        if rid == pid and row.get("window") == window and rscope == scope:
            matches.append(row)
    return matches[-1] if matches else None


def write_unverified(proposals: list[dict[str, str]]) -> None:
    rows = []
    for row in proposals:
        if not row.get("classification", "").startswith("(3)"):
            continue
        rows.append({
            "id": row["id"],
            "family": row["family"],
            "classification": row["classification"],
            "status": "UNVERIFIED_MAJOR_DEVELOPMENT",
            "reason": row.get("reason") or "大規模開発が必要なため今回の実装対象外",
            "parameter_json": row.get("parameter_json", ""),
        })
    atomic_write_csv(
        UNVERIFIED,
        rows,
        ["id", "family", "classification", "status", "reason", "parameter_json"],
    )
    if len(rows) != 180:
        raise RuntimeError(f"classification (3) count mismatch: {len(rows)} != 180")


def ea_input_names() -> set[str]:
    source = VERIFY_EA.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*input\s+(?:group\s+\"[^\"]*\"|\w+\s+(\w+))", source, re.M)) - {""}


def process_names() -> set[str]:
    query = subprocess.run(
        ["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True, errors="replace"
    )
    names: set[str] = set()
    for row in csv.reader(query.stdout.splitlines()):
        if row:
            names.add(row[0].lower())
    return names


def pid_is_running(pid: int) -> bool:
    query = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True, text=True, errors="replace",
    )
    for row in csv.reader(query.stdout.splitlines()):
        if len(row) >= 2 and row[1].isdigit() and int(row[1]) == pid:
            return True
    return False


def kill_tree(pid: int) -> None:
    """プロセスツリーごと強制終了する。孫の metatester64.exe を残さないため。"""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                   capture_output=True, text=True, errors="replace")


def kill_orphan_testers() -> bool:
    """孤立した metatester64.exe を回収する。

    run が timeout した後、テスターだけが残って次の wait_for_terminal を
    永久にブロックすることがある。ドライバは直列実行が前提なので、
    この時点で生きている metatester64 は前の run の残骸である。

    terminal64.exe は殺さない。ユーザーがフォワード運用中の実端末である
    可能性があり、落とすとライブ取引が止まる。metatester64 はバックテスト
    専用エージェントなのでライブには影響しない。
    """
    proc = subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"],
                          capture_output=True, text=True, errors="replace")
    return proc.returncode == 0


def run_with_hard_timeout(command: list[str], log_path: Path, timeout: int) -> int:
    """stdout/stderr をファイルへ流し、timeout でツリーごと殺す。

    subprocess.run(capture_output=True, timeout=...) はパイプを孫が握ると
    timeout 後に無限ブロックする。ここではパイプを一切作らない。
    """
    with open(log_path, "w", encoding="utf-8", errors="replace") as fh:
        fh.write("command=%r\n--- output ---\n" % (command,))
        fh.flush()
        proc = subprocess.Popen(command, cwd=REPO, stdout=fh,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        # proc.wait(timeout=) に頼らず、自前の締切をポーリングで見る。
        # 実測で wait(timeout=2520) が発火せず 11226 秒走った run があったため、
        # wait() の挙動に依存しない形にする。
        deadline = time.monotonic() + timeout
        while True:
            rc = proc.poll()
            if rc is not None:
                return rc
            if time.monotonic() >= deadline:
                break
            time.sleep(5)
        kill_tree(proc.pid)
        for _ in range(6):
            if proc.poll() is not None:
                break
            time.sleep(5)
        kill_orphan_testers()
        raise subprocess.TimeoutExpired(command, timeout)


def wait_for_terminal(timeout: int | None, poll_seconds: int) -> None:
    started = time.monotonic()
    last_notice = 0.0
    while True:
        names = process_names()
        busy = sorted(names & {"terminal64.exe", "metatester64.exe"})
        if not busy:
            return
        elapsed = time.monotonic() - started
        # metatester64 だけが居座っている場合、それは前の run の残骸なので回収する。
        # 直列実行が前提なので、この時点で正当に動いている metatester は存在しない。
        # terminal64 が居る間は殺さずに待つ（実運用端末の可能性がある）。
        if busy == ["metatester64.exe"] and elapsed >= STALE_TESTER_SECONDS:
            if kill_orphan_testers():
                progress(f"KILL_ORPHAN_TESTER elapsed={elapsed:.0f}s metatester64.exe")
                time.sleep(poll_seconds)
                started = time.monotonic()
                last_notice = 0.0
                continue
        if timeout is not None and elapsed >= timeout:
            raise TimeoutError(f"terminal wait timeout after {elapsed:.0f}s: {','.join(busy)}")
        if elapsed - last_notice >= 60 or last_notice == 0:
            progress(f"WAIT_TERMINAL elapsed={elapsed:.0f}s processes={','.join(busy)}")
            last_notice = elapsed
        time.sleep(poll_seconds)


@contextmanager
def single_driver_lock() -> Iterable[None]:
    ROOT.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    for _ in range(2):
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            detail = LOCK_FILE.read_text(encoding="ascii", errors="replace") if LOCK_FILE.exists() else ""
            match = re.search(r"\bpid=(\d+)\b", detail)
            owner_pid = int(match.group(1)) if match else -1
            if owner_pid > 0 and pid_is_running(owner_pid):
                raise RuntimeError(f"another run_all driver is active: {detail.strip()}") from exc
            # A hard kill cannot run finally.  Only the exact lock file is
            # recovered, and a still-running MT5 process is handled by the
            # separate terminal wait before the next run.
            try:
                LOCK_FILE.unlink()
                progress(f"STALE_LOCK_RECOVERED detail={detail.strip()!r}")
            except FileNotFoundError:
                pass
    if fd is None:
        raise RuntimeError("could not acquire run_all lock")
    try:
        os.write(fd, f"pid={os.getpid()} started={utc_now()}\n".encode("ascii"))
        os.close(fd)
        yield
    finally:
        try:
            LOCK_FILE.unlink()
        except FileNotFoundError:
            pass


def metrics_and_gates(path: Path, crypto_included: bool) -> dict[str, Any]:
    rows = read_csv(path)
    profits: list[float] = []
    lots: set[float] = set()
    counts = {name: 0 for name in MAGICS}
    for row in rows:
        try:
            profits.append(float(row["profit_jpy"]))
            volume = float(row.get("volume", 0) or 0)
            if volume > 0:
                lots.add(volume)
            magic = int(float(row.get("magic", 0) or 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid deal row in {path.name}: {row}") from exc
        for name, expected in MAGICS.items():
            if magic == expected:
                counts[name] += 1
    if not rows:
        raise ValueError(f"empty deal log: {path}")
    wins = sum(value for value in profits if value > 0)
    losses = -sum(value for value in profits if value < 0)
    balance = peak = 100000.0
    dd = 0.0
    for value in profits:
        balance += value
        peak = max(peak, balance)
        dd = max(dd, peak - balance)
    magic_pass = all(counts[name] > 0 for name in MAGICS) if crypto_included else True
    return {
        "net_jpy": sum(profits),
        "pf_jpy": wins / losses if losses else math.inf,
        "dd_amount_jpy": dd,
        "dd_jpy": dd / 1000.0,
        "deal_rows": len(rows),
        "effective_lots": "|".join(f"{value:.2f}" for value in sorted(lots)),
        "eth_present": counts["eth"] > 0,
        "eth_rows": counts["eth"],
        "funding_present": counts["funding"] > 0,
        "funding_rows": counts["funding"],
        "bfx_present": counts["bfx"] > 0,
        "bfx_rows": counts["bfx"],
        "magic_gate_pass": magic_pass,
    }


def ratio_reason(label: str, m: dict[str, Any], base: dict[str, float]) -> str:
    return (
        f"{label} net={m['net_jpy']:.2f} ({m['net_jpy']/base['net']:.3f}x), "
        f"PF={m['pf_jpy']:.6f} ({m['pf_jpy']/base['pf']:.3f}x), "
        f"DD={m['dd_amount_jpy']:.2f}円/{m['dd_jpy']:.5f}pt "
        f"({m['dd_amount_jpy']/base['dd']:.3f}x); baseline "
        f"net={base['net']:.2f}, PF={base['pf']:.6f}, DD={base['dd']:.2f}円"
    )


def classify(window: str, m: dict[str, Any]) -> tuple[str, str, str]:
    if window == "IS":
        base = IS_BASE
        nr, pr, dr = m["net_jpy"] / base["net"], m["pf_jpy"] / base["pf"], m["dd_amount_jpy"] / base["dd"]
        if abs(nr - 1) < 1e-7 and abs(pr - 1) < 1e-7 and abs(dr - 1) < 1e-7:
            return "IS_REJECT", "BASELINE_EQUIVALENT", ratio_reason("IS", m, base)
        if m["net_jpy"] > base["net"] and m["pf_jpy"] > base["pf"] and dr <= 1:
            return "IS_SURVIVOR_STRICT", "STRICT", ratio_reason("IS", m, base)
        if dr < 1 and nr >= 0.80 and pr >= 0.90:
            return "IS_SURVIVOR_DD", "DD_TRADEOFF", ratio_reason("IS", m, base)
        if m["net_jpy"] <= base["net"] and m["pf_jpy"] <= base["pf"] and dr >= 1:
            return "IS_REJECT", "DOMINATED", ratio_reason("IS", m, base)
        if nr < 0.75 and dr > 0.80:
            return "IS_REJECT", "PROFIT_LOSS", ratio_reason("IS", m, base)
        if pr < 0.80:
            return "IS_REJECT", "PF_LOSS", ratio_reason("IS", m, base)
        return "IS_SURVIVOR_TRADEOFF", "TRADEOFF", ratio_reason("IS", m, base)
    base = OOS_BASE if window == "OOS" else XM5_BASE
    nr, pr, dr = m["net_jpy"] / base["net"], m["pf_jpy"] / base["pf"], m["dd_amount_jpy"] / base["dd"]
    passed = (dr < 1 and nr >= 0.80 and pr >= 0.90) or (nr > 1 and pr > 1 and dr <= 1)
    prefix = "OOS" if window == "OOS" else "XM5"
    return (
        f"{prefix}_{'PASS' if passed else 'REJECT'}",
        "DD_OR_STRICT" if passed else "OUT_OF_GATE",
        ratio_reason(prefix, m, base),
    )


def dates_for(window: str, crypto_included: bool) -> tuple[str, str]:
    if window == "IS":
        return "2021.06.21", "2026.06.20"
    if window == "OOS":
        return ("2016.11.09" if crypto_included else "2016.06.21"), "2021.06.20"
    if window == "XM5":
        return "2016.11.09", "2026.06.20"
    raise ValueError(window)


def make_run_config(proposal: dict[str, str], window: str, run_id: str) -> tuple[dict[str, Any], bool]:
    family = proposal["family"]
    if family not in FAMILY_ACTIVATION:
        raise NotImplementedError(f"family has no verified SIMVERIFY activation: {family}")
    parameters = json.loads(proposal["parameter_json"])
    known = ea_input_names()
    missing = sorted((set(parameters) | set(FAMILY_ACTIVATION[family])) - known)
    if missing:
        raise NotImplementedError(f"SIMVERIFY input missing: {','.join(missing)}")
    crypto = window == "XM5"
    cfg = copy.deepcopy(BASE_CONFIG)
    cfg["parameters"].update(FAMILY_ACTIVATION[family])
    cfg["parameters"].update(parameters)
    if crypto:
        cfg["parameters"].update({"En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True})
    from_date, to_date = dates_for(window, crypto)
    equity_name = run_id + "_deals.csv"
    cfg.update({"from_date": from_date, "to_date": to_date, "report_name": run_id})
    cfg["parameters"].update({"ResultFileName": run_id + "_result.csv", "EquityLogFile": equity_name})
    return cfg, crypto


def result_stub(proposal: dict[str, str], window: str, scope: str) -> dict[str, Any]:
    return {
        "attempt_id": uuid.uuid4().hex,
        "proposal_id": proposal["id"],
        "id": proposal["id"],
        "family": proposal["family"],
        "classification": proposal["classification"],
        "window": window,
        "scope": scope,
        "parameter_json": proposal["parameter_json"],
    }


def persist_proposal(proposals: list[dict[str, str]], proposal: dict[str, str], result: dict[str, Any]) -> None:
    window = result["window"]
    if window == "IS":
        proposal.update({
            "status": str(result["decision"]), "reason": str(result["reason"]),
            "is_net_jpy": str(result.get("net_jpy", "")), "is_pf": str(result.get("pf_jpy", "")),
            "is_dd_jpy": str(result.get("dd_amount_jpy", "")),
        })
    elif window == "OOS":
        proposal.update({
            "status": str(result["decision"]), "reason": str(result["reason"]),
            "oos_net_jpy": str(result.get("net_jpy", "")), "oos_pf": str(result.get("pf_jpy", "")),
            "oos_dd_jpy": str(result.get("dd_amount_jpy", "")),
        })
    proposal.update({
        "effective_lots": str(result.get("effective_lots", proposal.get("effective_lots", ""))),
        "run_id": str(result.get("run_id", proposal.get("run_id", ""))),
        "updated_at": str(result.get("finished_at", utc_now())),
    })
    atomic_write_csv(PROPOSALS, proposals, list(proposals[0]))


def record_non_run(
    proposals: list[dict[str, str]], proposal: dict[str, str], window: str,
    decision: str, gate_code: str, reason: str,
) -> None:
    scope = "XM5" if window == "XM5" else "GOLD2"
    rec = result_stub(proposal, window, scope)
    rec.update({
        "status": "UNVERIFIED", "decision": decision, "gate_code": gate_code,
        "reason": reason, "started_at": utc_now(), "finished_at": utc_now(),
    })
    append_screen(rec)
    persist_proposal(proposals, proposal, rec)


def execute_one(
    proposals: list[dict[str, str]], proposal: dict[str, str], window: str,
    ordinal: int, total: int, args: argparse.Namespace,
) -> dict[str, Any]:
    scope = "XM5" if window == "XM5" else "GOLD2"
    rec = result_stub(proposal, window, scope)
    started_mono = time.monotonic()
    started_at = utc_now()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    run_id = f"gdda_{window.lower()}_{proposal['id'].lower()}_{stamp}_{rec['attempt_id'][:6]}"
    rec.update({"run_id": run_id, "started_at": started_at})
    progress(f"RUN_START [{ordinal}/{total}] id={proposal['id']} family={proposal['family']} window={window} run={run_id}")
    try:
        cfg, crypto = make_run_config(proposal, window, run_id)
        from_date, to_date = dates_for(window, crypto)
        config_path = CONFIG_DIR / (run_id + ".yaml")
        equity_name = cfg["parameters"]["EquityLogFile"]
        common_deal = COMMON_FILES / equity_name
        local_deal = DEAL_DIR / equity_name
        rec.update({
            "from_date": from_date, "to_date": to_date, "crypto_included": crypto,
            "equity_log_file": equity_name,
            "config_file": str(config_path.relative_to(REPO)),
            "baseline_lots": XM5_BASE_LOTS if crypto else GOLD_BASE_LOTS,
        })
        config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        if common_deal.exists():
            common_deal.unlink()
        wait_for_terminal(args.terminal_wait_timeout, args.poll_seconds)
        # XM5は5枠×約10年で重く、実測平均855秒。GOLD2と同じ2400秒だと
        # 正常な run までmt5bt側のタイムアウトで落ちるため期限を分ける。
        mt5bt_timeout = XM5_RUN_TIMEOUT if window == "XM5" else args.run_timeout
        command = [str(MT5BT), "run", str(config_path), "--timeout", str(mt5bt_timeout), "--no-charts", "--no-html"]
        run_log = RUN_LOG_DIR / (run_id + ".log")
        # パイプ(capture_output)は使わない。mt5bt.bat の孫プロセス metatester64.exe が
        # stdout ハンドルを継承するため、timeout 発火後の communicate() が
        # 孫の終了までブロックする。実際に1件で7.1時間ブロックした。
        # ファイルへリダイレクトすれば、親を殺した時点で即座に戻る。
        returncode = run_with_hard_timeout(command, run_log, mt5bt_timeout + 120)
        rec["returncode"] = returncode
        if returncode != 0:
            raise RuntimeError(f"mt5bt returncode={returncode}; log={run_log}")
        if not common_deal.exists() or common_deal.stat().st_size == 0:
            raise FileNotFoundError(f"FILE_COMMON deal log missing: {common_deal}")
        shutil.copyfile(common_deal, local_deal)
        measured = metrics_and_gates(local_deal, crypto)
        rec.update(measured)
        if crypto and not measured["magic_gate_pass"]:
            rec.update({
                "status": "UNVERIFIED", "decision": "UNVERIFIED_MAGIC_GATE",
                "gate_code": "CRYPTO_MAGIC_MISSING",
                "reason": (
                    f"crypto magic gate failed: ETH={measured['eth_rows']}, "
                    f"BTC funding={measured['funding_rows']}, BfxRev={measured['bfx_rows']}"
                ),
            })
        else:
            decision, gate_code, reason = classify(window, measured)
            lot_sensitive = proposal["family"] in LOT_SENSITIVE_FAMILIES
            lot_changed = measured["effective_lots"] != rec["baseline_lots"]
            rec["lot_step_verified"] = (not lot_sensitive) or lot_changed
            if lot_sensitive and not lot_changed:
                rec.update({
                    "status": "UNVERIFIED", "decision": "UNVERIFIED_LOTSTEP",
                    "gate_code": "EFFECTIVE_LOTS_UNCHANGED",
                    "reason": (
                        f"requested lot-changing proposal but effective lots remained "
                        f"{measured['effective_lots']} (baseline {rec['baseline_lots']}); {reason}"
                    ),
                })
            else:
                rec.update({"status": "OK", "decision": decision, "gate_code": gate_code, "reason": reason})
    except NotImplementedError as exc:
        rec.update({
            "status": "UNVERIFIED", "decision": "UNVERIFIED_EA_INPUT",
            "gate_code": "EA_IMPLEMENTATION_MISSING", "reason": str(exc), "error": repr(exc),
        })
    except subprocess.TimeoutExpired as exc:
        rec.update({
            "status": "FAILED", "decision": "RUN_FAILED", "gate_code": "TIMEOUT",
            "reason": f"individual run timed out: {exc}", "error": repr(exc),
        })
    except Exception as exc:  # individual failures must not stop the full queue
        rec.update({
            "status": "FAILED", "decision": "RUN_FAILED", "gate_code": type(exc).__name__,
            "reason": str(exc), "error": traceback.format_exc(limit=8),
        })
    finally:
        rec["finished_at"] = utc_now()
        rec["elapsed_seconds"] = f"{time.monotonic() - started_mono:.3f}"
        append_screen(rec)
        persist_proposal(proposals, proposal, rec)
        progress(
            f"RUN_END [{ordinal}/{total}] id={proposal['id']} window={window} "
            f"status={rec.get('status')} decision={rec.get('decision')} elapsed={rec['elapsed_seconds']}s"
        )
    return rec


def is_survivor(row: dict[str, str] | None) -> bool:
    return bool(row and row.get("status") == "OK" and row.get("decision", "").startswith("IS_SURVIVOR"))


def oos_promising(row: dict[str, str] | None) -> bool:
    return bool(row and row.get("status") == "OK" and row.get("decision") == "OOS_PASS")


def select_proposals(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("classification", "").startswith("(2)")]
    if args.family:
        wanted = set(args.family)
        selected = [row for row in selected if row["family"] in wanted]
    if args.proposal_id:
        wanted_ids = set(args.proposal_id)
        selected = [row for row in selected if row["id"] in wanted_ids]
    return selected


def run_queue(proposals: list[dict[str, str]], args: argparse.Namespace) -> None:
    selected = select_proposals(proposals, args)
    done = completed_keys(args.retry_failed, args.retry_unverified)
    actual_started = 0
    skipped = 0
    for ordinal, proposal in enumerate(selected, 1):
        pid = proposal["id"]
        stages = ["IS"] if args.stage == "is" else ["OOS"] if args.stage == "oos" else ["XM5"] if args.stage == "xm5" else ["IS", "OOS", "XM5"]
        for window in stages:
            scope = "XM5" if window == "XM5" else "GOLD2"
            key = (pid, window, scope)
            if key in done:
                skipped += 1
                progress(f"SKIP_EXISTING [{ordinal}/{len(selected)}] id={pid} window={window} scope={scope}")
                continue
            if window == "OOS" and not is_survivor(proposal_result(pid, "IS", "GOLD2")):
                progress(f"GATE_SKIP [{ordinal}/{len(selected)}] id={pid} window=OOS reason=IS_NOT_SURVIVOR")
                continue
            if window == "XM5" and not oos_promising(proposal_result(pid, "OOS", "GOLD2")):
                progress(f"GATE_SKIP [{ordinal}/{len(selected)}] id={pid} window=XM5 reason=OOS_NOT_PROMISING")
                continue
            if args.dry_run:
                progress(f"DRY_RUN [{ordinal}/{len(selected)}] id={pid} window={window} scope={scope}")
                continue
            if args.limit is not None and actual_started >= args.limit:
                progress(f"LIMIT_REACHED actual_runs={actual_started}")
                progress(f"QUEUE_SUMMARY selected={len(selected)} started={actual_started} skipped={skipped}")
                return
            actual_started += 1
            result = execute_one(proposals, proposal, window, ordinal, len(selected), args)
            done.add(key)
            if result.get("decision") in {"UNVERIFIED_EA_INPUT", "RUN_FAILED", "UNVERIFIED_LOTSTEP", "UNVERIFIED_MAGIC_GATE"}:
                break
    progress(f"QUEUE_SUMMARY selected={len(selected)} started={actual_started} skipped={skipped}")


def self_check() -> None:
    valid = DEAL_DIR / "gdd_xm5_full_off_ethfix_20260814_x1_deals.csv"
    invalid = DEAL_DIR / "gdd_xm5_full_mutex_x1_deals.csv"
    good = metrics_and_gates(valid, True)
    bad = metrics_and_gates(invalid, True)
    if not good["magic_gate_pass"]:
        raise AssertionError(f"corrected XM5 log did not pass: {good}")
    if bad["magic_gate_pass"] or bad["eth_present"]:
        raise AssertionError(f"known ETH-missing XM5 log was not rejected: {bad}")
    proposals = read_csv(PROPOSALS)
    write_unverified(proposals)
    if len(read_csv(UNVERIFIED)) != 180:
        raise AssertionError("unverified.csv does not contain 180 rows")
    print(
        json.dumps(
            {
                "self_check": "OK", "valid_magic_counts": {k: good[k] for k in ("eth_rows", "funding_rows", "bfx_rows")},
                "invalid_magic_counts": {k: bad[k] for k in ("eth_rows", "funding_rows", "bfx_rows")},
                "unverified_rows": 180,
            }, ensure_ascii=False,
        ), flush=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "is", "oos", "xm5"), default="all")
    parser.add_argument("--family", action="append", help="restrict to a family; repeatable")
    parser.add_argument("--proposal-id", action="append", help="restrict to a proposal ID; repeatable")
    parser.add_argument("--limit", type=int, help="maximum number of newly attempted runs")
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
    for directory in (CONFIG_DIR, RUN_LOG_DIR, DEAL_DIR, COMMON_FILES):
        directory.mkdir(parents=True, exist_ok=True)
    if args.self_check:
        self_check()
        return 0
    with single_driver_lock():
        ensure_screen_schema()
        proposals = read_csv(PROPOSALS)
        if len(proposals) != 1000:
            raise RuntimeError(f"proposal registry row count mismatch: {len(proposals)} != 1000")
        write_unverified(proposals)
        progress(
            f"DRIVER_START pid={os.getpid()} stage={args.stage} proposals={len(proposals)} "
            f"classification2={sum(r.get('classification','').startswith('(2)') for r in proposals)} "
            f"implemented_families={len(FAMILY_ACTIVATION)}"
        )
        run_queue(proposals, args)
        progress("DRIVER_END status=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
