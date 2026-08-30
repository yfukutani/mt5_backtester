"""Parallel, resumable OANDA FX drawdown proposal driver.

Every executable proposal is measured by a real MT5 backtest.  No trade is
removed or rescaled after the fact.  SHA-256 regression and nine-magic gates
are deliberately opt-in; use --sha-regression-gate and --magic-gate.

Most proposals first receive an IS-only SCA GBPJPY single-sleeve screen.  A
screen pass is only permission to run the nine-slot full-book IS measurement,
never an adoption decision.  Cross-sleeve proposals bypass that screen.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "oafx_dd"
PROPOSALS = ROOT / "proposals.csv"
RESULTS = ROOT / "results.csv"
UNVERIFIED = ROOT / "unverified.csv"
CONFIG_DIR = ROOT / "configs"
LOG_DIR = ROOT / "logs"
DEAL_DIR = ROOT / "run_deals"
PROGRESS = ROOT / "run_oafx.log"
LOCK = ROOT / "run_oafx.lock"
EA_SOURCE = REPO / "experts" / "MIX_EA_OANDA_SIMVERIFY.mq5"
MT5BT = REPO / "mt5bt.bat"
COMMON_FILES = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "Common" / "Files"
BASE_TEMPLATE = ROOT / "regression_simverify_is.yaml"
REGRESSION_GATE = ROOT / "regression_gate.json"


@dataclass(frozen=True)
class TerminalSpec:
    name: str
    executable: Path
    data_dir: Path

    @property
    def tester_executable(self) -> Path:
        return self.executable.with_name("metatester64.exe")


TERMINALS = (
    TerminalSpec(
        "PROD",
        Path(r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"),
        Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\EE0304F13905552AE0B5EAEFB04866EB"),
    ),
    TerminalSpec(
        "BT1",
        Path(r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"),
        Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\6142D304BFF2E6AB353977162D6F452C"),
    ),
    TerminalSpec(
        "BT2",
        Path(r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe"),
        Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\06EBB62A36630B6356B2240C609DE508"),
    ),
    TerminalSpec(
        "BT3",
        Path(r"C:\Program Files\OANDA MetaTrader 5_BT3\terminal64.exe"),
        Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\62828C99ECDEDC6E786AB3636A65EF28"),
    ),
    TerminalSpec(
        "BT4",
        Path(r"C:\Program Files\OANDA MetaTrader 5_BT4\terminal64.exe"),
        Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\9501A6965ADC505E82257549A51CD4DE"),
    ),
)

WINDOWS = {
    "SCREEN_IS": ("2021.06.21", "2026.06.20"),
    "IS": ("2021.06.21", "2026.06.20"),
    "OOS": ("2016.11.09", "2021.06.20"),
    "FULL": ("2016.11.09", "2026.06.20"),
}
BASELINE_IS = {"net": 277106.0, "pf": 1.3945, "dd_pct": 35.65, "trades": 1573}
BASELINE_SCREEN_IS = {"net": 84921.0, "pf": 1.2184, "dd_pct": 19.5314, "trades": 685}
SCREEN_ROUTE_STAGED = "SINGLE_SLEEVE_THEN_FULLBOOK"
SCREEN_ROUTE_DIRECT = "FULLBOOK_DIRECT"
MAGICS = {
    "pb_usdjpy": 20260622, "pb_gbpjpy": 20260627,
    "rsi_usdjpy": 20260610, "rsi_eurusd": 20260605,
    "rsi_gbpusd": 20260774, "pair": 20260629, "carry": 20260650,
    "sca_usdjpy": 20261000, "sca_gbpjpy": 20261001,
}
# 2026-08-30: 300秒だと孤立テスター1件につき最大5分を空費する(1 runが約400秒なので影響大)。
# terminal64が不在でmetatester64だけが残る状態は明確な残骸なので、短めに回収する。
STALE_TESTER_SECONDS = 90
DEFAULT_RUN_TIMEOUT = 1200  # 通常run374秒(最大402)に対し7200は緩すぎ、1件で4.5時間を浪費したため短縮
DEFAULT_TERMINAL_COUNT = 5
TERMINAL_START_STAGGER_SECONDS = 25
# 置き去りのterminal64を残骸と見なして回収するまでの秒数。0で無効。
# この端末ではフォワードを稼働させていない（ユーザー確認済み 2026-08-25）ため有効にする。
RECLAIM_TERMINAL_AFTER = 900

PROGRESS_LOCK = threading.Lock()
RESULT_LOCK = threading.RLock()
OOS_BASELINE_LOCK = threading.Lock()

RESULT_FIELDS = [
    "attempt_id", "run_id", "proposal_id", "family", "implementation_class", "window",
    "measurement_scope", "screening_route", "screening_reason",
    "status", "decision", "gate_code", "reason", "returncode",
    "net", "pf", "dd_pct", "trades", "dd_below_30", "profit_ratio", "pf_ratio", "dd_delta",
    "deal_rows", "deal_sha256", "projected_sha256", "effective_gj_lots", "baseline_gj_lots",
    "lot_step_verified", *[f"{name}_rows" for name in MAGICS],
    "magic_gate_enabled", "magic_gate_pass", "regression_gate_enabled", "regression_pass",
    "is_net", "is_pf", "is_dd_pct", "is_dd_below_30",
    "oos_net", "oos_pf", "oos_dd_pct", "oos_dd_below_30",
    "ea_sha256", "parameter_json", "config_file", "deal_file", "from_date", "to_date",
    "started_at", "finished_at", "elapsed_seconds", "error",
]
UNVERIFIED_FIELDS = ["proposal_id", "family", "status", "reason", "parameter_json"]


def screening_plan(proposal: dict[str, str]) -> tuple[str, str]:
    """Return the auditable stage-1 route without using backtest outcomes."""
    family = proposal["family"]
    if family == "sca_gj_overlap_gate":
        return SCREEN_ROUTE_DIRECT, (
            "OafxOverlapMaskで他枠の実保有を参照するため、単独枠では効果を測定不能"
        )
    if family == "sca_gj_realized_loss_cooldown":
        parameters = json.loads(proposal["parameter_json"])
        scope = int(parameters["OafxLossScope"])
        if scope != 1:
            labels = {2: "SCA両枠", 3: "全9枠", 4: "重複相手枠"}
            return SCREEN_ROUTE_DIRECT, (
                f"OafxLossScope={scope} ({labels.get(scope, '他枠')}) の実現損失を参照するため、"
                "単独枠では効果を測定不能"
            )
    return SCREEN_ROUTE_STAGED, (
        "SCA GBPJPY枠内の条件だけを変更するため単独枠で予備選別し、"
        "通過時は枠間重複を含む9枠フルブックで必ず本測定"
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ea_sha() -> str:
    return hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest().upper()


def progress(message: str) -> None:
    line = f"{utc_now()} {message}"
    with PROGRESS_LOCK:
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
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def ensure_outputs() -> None:
    if not RESULTS.exists() or RESULTS.stat().st_size == 0:
        atomic_csv(RESULTS, [], RESULT_FIELDS)
    else:
        with RESULTS.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            old_fields = reader.fieldnames or []
            rows = list(reader)
        if old_fields != RESULT_FIELDS:
            if not set(old_fields).issubset(RESULT_FIELDS):
                raise RuntimeError(f"results schema mismatch: {RESULTS}")
            proposals = {row["id"]: row for row in read_csv(PROPOSALS)}
            for row in rows:
                proposal = proposals.get(row.get("proposal_id", ""))
                if proposal:
                    route, route_reason = screening_plan(proposal)
                    row.setdefault("screening_route", route)
                    row.setdefault("screening_reason", route_reason)
                    row.setdefault(
                        "measurement_scope",
                        "SCA_GBPJPY_ONLY" if row.get("window") == "SCREEN_IS" else "NINE_SLOT_FULLBOOK",
                    )
            atomic_csv(RESULTS, rows, RESULT_FIELDS)
    if not UNVERIFIED.exists() or UNVERIFIED.stat().st_size == 0:
        atomic_csv(UNVERIFIED, [], UNVERIFIED_FIELDS)


def append_result(row: dict[str, Any]) -> None:
    with RESULT_LOCK:
        with RESULTS.open("a", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=RESULT_FIELDS, extrasaction="ignore").writerow(
                {field: row.get(field, "") for field in RESULT_FIELDS}
            )
            handle.flush()
            os.fsync(handle.fileno())


def command_text(command: list[str]) -> str:
    """Read short Windows utility output through a file, never a pipe."""
    with tempfile.TemporaryFile(mode="w+b") as output:
        subprocess.run(command, stdout=output, stderr=output, stdin=subprocess.DEVNULL)
        output.seek(0)
        return output.read().decode("utf-8", errors="replace")


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int
    name: str
    executable: str
    command_line: str


def normalized_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(value))).casefold()


def process_snapshot() -> list[ProcessInfo]:
    """Return MT5 process paths; paths are essential because all five names match."""
    script = (
        "$ErrorActionPreference='Stop'; "
        "@(Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -in @('terminal64.exe','metatester64.exe') } | "
        "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine) | "
        "ConvertTo-Json -Compress"
    )
    output = command_text(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]).strip()
    if not output:
        return []
    raw = json.loads(output)
    if isinstance(raw, dict):
        raw = [raw]
    return [
        ProcessInfo(
            pid=int(item.get("ProcessId") or 0),
            parent_pid=int(item.get("ParentProcessId") or 0),
            name=str(item.get("Name") or "").casefold(),
            executable=str(item.get("ExecutablePath") or ""),
            command_line=str(item.get("CommandLine") or ""),
        )
        for item in raw
        if int(item.get("ProcessId") or 0) > 0
    ]


def terminal_processes(snapshot: list[ProcessInfo], terminal: TerminalSpec) -> tuple[list[ProcessInfo], list[ProcessInfo]]:
    terminal_path = normalized_path(terminal.executable)
    tester_path = normalized_path(terminal.tester_executable)
    terminals = [proc for proc in snapshot
                 if proc.name == "terminal64.exe" and normalized_path(proc.executable) == terminal_path]
    testers = [proc for proc in snapshot
               if proc.name == "metatester64.exe" and normalized_path(proc.executable) == tester_path]
    return terminals, testers


def pid_running(pid: int) -> bool:
    output = command_text(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"])
    return any(len(row) > 1 and row[1].isdigit() and int(row[1]) == pid
               for row in csv.reader(output.splitlines()))


def kill_processes(processes: Iterable[ProcessInfo]) -> list[int]:
    killed: list[int] = []
    for proc in processes:
        result = subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL)
        if result.returncode == 0:
            killed.append(proc.pid)
    return killed


def wait_for_mt5_idle(terminal: TerminalSpec, timeout: int | None, poll_seconds: int) -> None:
    """Wait for one installation only and reclaim only that installation's orphans."""
    started = time.monotonic()
    orphan_started: float | None = None
    last_notice = -60.0
    while True:
        terminal_procs, tester_procs = terminal_processes(process_snapshot(), terminal)
        if not terminal_procs and not tester_procs:
            return
        now = time.monotonic()
        elapsed = now - started
        if tester_procs and not terminal_procs:
            if orphan_started is None:
                orphan_started = now
            if now - orphan_started >= STALE_TESTER_SECONDS:
                killed = kill_processes(tester_procs)
                if killed:
                    progress(f"KILL_ORPHAN_TESTER terminal={terminal.name} pids={killed} "
                             f"orphan_seconds={now - orphan_started:.0f}")
                    orphan_started = None
                    time.sleep(poll_seconds)
                    continue
        else:
            orphan_started = None
        # 置き去りのterminal64で無限に待たない。この端末ではフォワードを稼働させていない
        # ことをユーザーが確認済みのため、長時間居座るterminal64は前回runの残骸と見なして
        # 回収する。ライブ端末が同居する環境ではRECLAIM_TERMINAL_AFTER=0にすること。
        if terminal_procs and RECLAIM_TERMINAL_AFTER > 0 and elapsed >= RECLAIM_TERMINAL_AFTER:
            killed = kill_processes([*terminal_procs, *tester_procs])
            progress(f"RECLAIM_STALE_TERMINAL terminal={terminal.name} pids={killed} after={elapsed:.0f}s")
            started = time.monotonic()
            last_notice = -60.0
            time.sleep(poll_seconds)
            continue
        if elapsed - last_notice >= 60:
            pids = [proc.pid for proc in (*terminal_procs, *tester_procs)]
            progress(f"WAIT_MT5_IDLE terminal={terminal.name} elapsed={elapsed:.0f}s pids={pids}")
            last_notice = elapsed
        if timeout is not None and elapsed >= timeout:
            raise TimeoutError(f"{terminal.name} terminal64.exe/metatester64.exe did not become idle")
        time.sleep(poll_seconds)


def run_command(command: list[str], log_path: Path, timeout: int, poll_seconds: int,
                terminal: TerminalSpec) -> int:
    """Redirect child output to disk and also reclaim a lone tester while waiting."""
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL)
        started = time.monotonic()
        orphan_started: float | None = None
        last_notice = -60.0
        while process.poll() is None:
            now = time.monotonic()
            elapsed = now - started
            terminal_procs, tester_procs = terminal_processes(process_snapshot(), terminal)
            if tester_procs and not terminal_procs:
                if orphan_started is None:
                    orphan_started = now
                elif now - orphan_started >= STALE_TESTER_SECONDS:
                    killed = kill_processes(tester_procs)
                    if killed:
                        progress(f"KILL_ORPHAN_TESTER_DURING_RUN terminal={terminal.name} pids={killed} "
                                 f"orphan_seconds={now - orphan_started:.0f}")
                        orphan_started = None
            else:
                orphan_started = None
            if elapsed - last_notice >= 60:
                progress(f"RUN_HEARTBEAT terminal={terminal.name} pid={process.pid} elapsed={elapsed:.0f}s")
                last_notice = elapsed
            if elapsed >= timeout:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL)
                owned = terminal_processes(process_snapshot(), terminal)
                kill_processes([*owned[0], *owned[1]])
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(poll_seconds)
        return int(process.returncode)


class LaunchGate:
    """Reserve globally staggered launch slots to avoid local-agent port races."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._next_launch = time.monotonic()

    def wait(self, terminal: TerminalSpec) -> None:
        with self._lock:
            now = time.monotonic()
            launch_at = max(now, self._next_launch)
            self._next_launch = launch_at + self.interval_seconds
        delay = launch_at - now
        if delay > 0.01:
            progress(f"WAIT_LAUNCH_SLOT terminal={terminal.name} seconds={delay:.1f}")
            time.sleep(delay)


@contextmanager
def driver_lock() -> Iterable[None]:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        detail = LOCK.read_text(encoding="ascii", errors="replace")
        match = re.search(r"pid=(\d+)", detail)
        if match and pid_running(int(match.group(1))):
            raise RuntimeError(f"another run_oafx.py is active: {detail.strip()}") from exc
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, f"pid={os.getpid()} started={utc_now()}\n".encode("ascii"))
        os.close(fd)
        yield
    finally:
        LOCK.unlink(missing_ok=True)


def ea_inputs() -> set[str]:
    return set(re.findall(r"^\s*input\s+\w+\s+(\w+)", EA_SOURCE.read_text(encoding="utf-8"), re.M))


def verify_runtime(terminals: Iterable[TerminalSpec]) -> None:
    if not MT5BT.is_file():
        raise FileNotFoundError(f"mt5bt launcher missing: {MT5BT}")
    source_digest = hashlib.sha256(EA_SOURCE.read_bytes()).digest()
    for terminal in terminals:
        if not terminal.executable.is_file():
            raise FileNotFoundError(f"terminal64.exe missing for {terminal.name}: {terminal.executable}")
        if not terminal.tester_executable.is_file():
            raise FileNotFoundError(f"metatester64.exe missing for {terminal.name}: {terminal.tester_executable}")
        installed_source = terminal.data_dir / "MQL5" / "Experts" / EA_SOURCE.name
        installed_binary = installed_source.with_suffix(".ex5")
        if not installed_source.is_file() or not installed_binary.is_file():
            raise FileNotFoundError(f"installed SIMVERIFY mq5/ex5 missing for {terminal.name}")
        if hashlib.sha256(installed_source.read_bytes()).digest() != source_digest:
            raise RuntimeError(f"installed SIMVERIFY source differs from repository for {terminal.name}")
        if installed_binary.stat().st_mtime < installed_source.stat().st_mtime:
            raise RuntimeError(f"installed SIMVERIFY ex5 is older than source for {terminal.name}")


def read_summary(run_id: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    path = REPO / "results" / run_id / "summary.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2:
                values[row[0]] = row[1]
    return {
        "net": float(values["純利益"]), "pf": float(values["プロフィットファクター"]),
        "dd_pct": float(values["最大相対DD%"]), "trades": int(values["総取引数"]),
    }


def projected_sha(rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["time", "profit"])
    writer.writerows((row["time"], row["profit"]) for row in rows)
    return hashlib.sha256(output.getvalue().encode("utf-8")).hexdigest().upper()


def deal_metrics(path: Path) -> dict[str, Any]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"empty deal log: {path}")
    counts = {name: 0 for name in MAGICS}
    gj_lots: set[float] = set()
    for row in rows:
        magic = int(float(row.get("magic", 0) or 0))
        volume = float(row.get("volume", 0) or 0)
        for name, expected in MAGICS.items():
            if magic == expected:
                counts[name] += 1
        if magic == MAGICS["sca_gbpjpy"] and volume > 0:
            gj_lots.add(volume)
    return {
        "deal_rows": len(rows),
        "deal_sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        "projected_sha256": projected_sha(rows),
        "effective_gj_lots": "|".join(f"{lot:.2f}" for lot in sorted(gj_lots)),
        **{f"{name}_rows": count for name, count in counts.items()},
    }


def all_magics_present(deals: dict[str, Any]) -> bool:
    return all(int(deals[f"{name}_rows"]) > 0 for name in MAGICS)


def base_config(window: str, run_id: str, deal_name: str) -> dict[str, Any]:
    cfg = yaml.safe_load(BASE_TEMPLATE.read_text(encoding="utf-8-sig"))
    cfg = copy.deepcopy(cfg)
    cfg["expert"] = "MIX_EA_OANDA_SIMVERIFY"
    cfg["from_date"], cfg["to_date"] = WINDOWS[window]
    cfg["report_dir"] = "results"
    cfg["report_name"] = run_id
    cfg["model"] = "every_tick"
    cfg["parameters"]["OafxLabMode"] = 0
    cfg["parameters"]["ResultFileName"] = run_id + "_result.csv"
    cfg["parameters"]["EquityLogFile"] = deal_name
    if window == "SCREEN_IS":
        for name in tuple(cfg["parameters"]):
            if name.startswith("En_"):
                cfg["parameters"][name] = False
        cfg["parameters"]["En_SCA_GBPJPY"] = True
    return cfg


def latest_rows() -> dict[tuple[str, str], dict[str, str]]:
    latest: dict[tuple[str, str], dict[str, str]] = {}
    with RESULT_LOCK:
        for row in read_csv(RESULTS):
            latest[(row["proposal_id"], row["window"])] = row
    return latest


def numeric_reason(window: str, value: dict[str, Any], base: dict[str, Any]) -> str:
    return (f"{window} net={value['net']:.2f} ratio={value['net']/base['net']:.4f}, "
            f"PF={value['pf']:.4f} ratio={value['pf']/base['pf']:.4f}, "
            f"DD={value['dd_pct']:.4f}% delta={value['dd_pct']-base['dd_pct']:+.4f}pt, "
            f"DD<30={'YES' if value['dd_pct'] < 30 else 'NO'}; baseline "
            f"net={base['net']:.2f}, PF={base['pf']:.4f}, DD={base['dd_pct']:.4f}%")


def classify_is(value: dict[str, Any]) -> tuple[str, str, str]:
    base = BASELINE_IS
    reason = numeric_reason("IS", value, base)
    if value["dd_pct"] < base["dd_pct"] and value["net"] >= base["net"] * .90:
        if value["net"] > base["net"] and value["pf"] > base["pf"]:
            return "IS_SURVIVOR_STRICT", "STRICT_IS", reason
        return "IS_SURVIVOR_DD", "DD_AND_PROFIT_GATE", reason
    if value["dd_pct"] < base["dd_pct"] and value["net"] < base["net"] * .90:
        return "IS_REJECT_TRADEOFF", "PROFIT_DAMAGE_GT10", reason
    return "IS_REJECT", "DD_NOT_IMPROVED", reason


def classify_screen_is(value: dict[str, Any]) -> tuple[str, str, str]:
    """Pre-screen only; these labels must never be treated as adoption decisions."""
    base = BASELINE_SCREEN_IS
    detail = numeric_reason("SCREEN_IS(SCA GBPJPY単独)", value, base)
    caveat = "単独枠の予備選別であり採否判定ではない。フルブックでは異なる結果になりうる。"
    if value["dd_pct"] < base["dd_pct"] and value["net"] >= base["net"] * .90:
        if value["net"] > base["net"] and value["pf"] > base["pf"]:
            return "SCREEN_PASS_STRICT", "SINGLE_STRICT_GATE", f"{caveat} {detail}"
        return "SCREEN_PASS_DD", "SINGLE_DD_AND_PROFIT_GATE", f"{caveat} {detail}"
    if value["dd_pct"] < base["dd_pct"]:
        code = "SINGLE_PROFIT_DAMAGE_GT10"
    else:
        code = "SINGLE_DD_NOT_IMPROVED"
    return (
        "SCREEN_OUT_SINGLE_SLEEVE",
        code,
        f"単独枠では劣後。{caveat} {detail}",
    )


def classify_oos(is_row: dict[str, str], value: dict[str, Any], base_oos: dict[str, Any]) -> tuple[str, str, str]:
    is_value = {key: float(is_row[key]) for key in ("net", "pf", "dd_pct")}
    is_dd = is_value["dd_pct"] < BASELINE_IS["dd_pct"]
    oos_dd = value["dd_pct"] < base_oos["dd_pct"]
    is_profit_ok = is_value["net"] >= BASELINE_IS["net"] * .90
    oos_profit_ok = value["net"] >= base_oos["net"] * .90
    strict = (is_dd and oos_dd and is_value["net"] > BASELINE_IS["net"] and
              is_value["pf"] > BASELINE_IS["pf"] and value["net"] > base_oos["net"] and
              value["pf"] > base_oos["pf"])
    reason = numeric_reason("OOS", value, base_oos)
    if strict:
        return "STRICT_IMPROVEMENT", "STRICT_BOTH", reason
    if is_dd and oos_dd and is_profit_ok and oos_profit_ok:
        return "DD_IMPROVEMENT", "DD_BOTH_PROFIT_WITHIN10", reason
    if is_dd and oos_dd:
        return "TRADEOFF", "DD_BOTH_PROFIT_DAMAGE", reason
    return "REJECT", "DD_NOT_LOWER_BOTH", reason


def execute(proposal: dict[str, str] | None, window: str, args: argparse.Namespace,
            terminal: TerminalSpec, launch_gate: LaunchGate,
            purpose: str = "proposal") -> dict[str, Any]:
    if purpose == "regression":
        proposal_id, family, implementation_class, parameters = "REGRESSION_BASELINE", "regression", "gate", {}
    elif purpose == "oos_baseline":
        proposal_id, family, implementation_class, parameters = "BASELINE_OOS", "baseline", "gate", {}
    else:
        assert proposal is not None
        proposal_id, family = proposal["id"], proposal["family"]
        implementation_class = proposal["implementation_class"]
        parameters = json.loads(proposal["parameter_json"])
    attempt = uuid.uuid4().hex
    run_id = f"oafx_{window.lower()}_{proposal_id.lower()}_{datetime.now():%Y%m%d%H%M%S}_{attempt[:6]}"
    record: dict[str, Any] = {
        "attempt_id": attempt, "run_id": run_id, "proposal_id": proposal_id,
        "family": family, "implementation_class": implementation_class, "window": window,
        "started_at": utc_now(), "from_date": WINDOWS[window][0], "to_date": WINDOWS[window][1],
        "ea_sha256": ea_sha(), "parameter_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
        "magic_gate_enabled": args.magic_gate, "regression_gate_enabled": args.sha_regression_gate,
        "baseline_gj_lots": "0.01|0.06",
    }
    if proposal is not None:
        route, route_reason = screening_plan(proposal)
        record.update(
            measurement_scope="SCA_GBPJPY_ONLY" if window == "SCREEN_IS" else "NINE_SLOT_FULLBOOK",
            screening_route=route,
            screening_reason=route_reason,
        )
    else:
        record["measurement_scope"] = "NINE_SLOT_FULLBOOK"
    started = time.monotonic()
    progress(f"RUN_START id={proposal_id} family={family} window={window} "
             f"terminal={terminal.name} run={run_id}")
    try:
        unknown = sorted(set(parameters) - ea_inputs())
        if unknown:
            raise NotImplementedError("SIMVERIFY input missing: " + ",".join(unknown))
        deal_name = run_id + "_deals.csv"
        cfg = base_config(window, run_id, deal_name)
        cfg["mt5_path"] = str(terminal.executable)
        cfg["parameters"].update(parameters)
        config_path = CONFIG_DIR / f"{run_id}.yaml"
        config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        common_deal = COMMON_FILES / deal_name
        local_deal = DEAL_DIR / deal_name
        common_deal.unlink(missing_ok=True)
        record["config_file"] = str(config_path.relative_to(REPO))
        record["deal_file"] = str(local_deal.relative_to(REPO))
        # A missing executable and an already-running terminal are separate hard checks.
        if not terminal.executable.is_file():
            raise FileNotFoundError(f"terminal64.exe missing before launch: {terminal.executable}")
        wait_for_mt5_idle(terminal, args.terminal_wait_timeout, args.poll_seconds)
        launch_gate.wait(terminal)
        command = [str(MT5BT), "run", str(config_path), "--timeout", str(args.run_timeout),
                   "--no-charts", "--no-html"]
        record["returncode"] = run_command(command, LOG_DIR / f"{run_id}.log",
                                            args.run_timeout + 600, args.poll_seconds, terminal)
        if record["returncode"] != 0:
            raise RuntimeError(f"mt5bt returned {record['returncode']}")
        wait_for_mt5_idle(terminal, args.terminal_wait_timeout, args.poll_seconds)
        if not common_deal.is_file() or common_deal.stat().st_size == 0:
            raise FileNotFoundError(f"FILE_COMMON deal log missing: {common_deal}")
        shutil.copyfile(common_deal, local_deal)
        summary = read_summary(run_id)
        deals = deal_metrics(local_deal)
        record.update(summary)
        record.update(deals)
        record["dd_below_30"] = summary["dd_pct"] < 30
        magic_pass = (int(deals["sca_gbpjpy_rows"]) > 0 if window == "SCREEN_IS"
                      else all_magics_present(deals))
        record["magic_gate_pass"] = magic_pass
        if args.magic_gate and not magic_pass:
            expected_magics = ("sca_gbpjpy",) if window == "SCREEN_IS" else tuple(MAGICS)
            missing = [name for name in expected_magics if deals[f"{name}_rows"] == 0]
            record.update(status="UNVERIFIED", decision="UNVERIFIED_MAGIC_GATE",
                          gate_code="MAGIC_MISSING", reason="missing magic: " + ",".join(missing))
        elif purpose == "regression":
            reference = json.loads(REGRESSION_GATE.read_text(encoding="utf-8"))["windows"][window]
            expected = reference["summary"]
            checks = {
                "net": abs(summary["net"] - float(expected["net"])) < .005,
                "pf": abs(summary["pf"] - float(expected["pf"])) < .00005,
                "dd": abs(summary["dd_pct"] - float(expected["dd_pct"])) < .00005,
                "trades": summary["trades"] == int(expected["trades"]),
                "raw_sha": deals["deal_sha256"] == reference["simverify_deal_sha256"],
                "projected_sha": deals["projected_sha256"] == reference["projected_time_profit_sha256"],
                "nine_magics": magic_pass,
            }
            failed = [name for name, passed in checks.items() if not passed]
            record["regression_pass"] = not failed
            record.update(status="OK" if not failed else "INVALID",
                          decision="REGRESSION_PASS" if not failed else "REGRESSION_FAIL",
                          gate_code="SHA256_EXACT" if not failed else "REGRESSION_MISMATCH",
                          reason="exact summary/raw/projected SHA and nine magics" if not failed else "failed: " + ",".join(failed))
        elif purpose == "oos_baseline":
            record.update(status="OK", decision="BASELINE_MEASURED", gate_code="ACTUAL_MT5",
                          reason="OOS baseline measured by actual MT5")
        else:
            lot_sensitive = "OafxGJBoostMult" in parameters
            record["lot_step_verified"] = (not lot_sensitive) or deals["effective_gj_lots"] != record["baseline_gj_lots"]
            if lot_sensitive and not record["lot_step_verified"]:
                record.update(status="UNVERIFIED", decision="UNVERIFIED_LOTSTEP",
                              gate_code="EFFECTIVE_LOTS_UNCHANGED",
                              reason=f"SCA GBPJPY lots unchanged: {deals['effective_gj_lots']}")
            elif window == "SCREEN_IS":
                decision, code, reason = classify_screen_is(summary)
                record.update(status="OK", decision=decision, gate_code=code, reason=reason)
                record["profit_ratio"] = summary["net"] / BASELINE_SCREEN_IS["net"]
                record["pf_ratio"] = summary["pf"] / BASELINE_SCREEN_IS["pf"]
                record["dd_delta"] = summary["dd_pct"] - BASELINE_SCREEN_IS["dd_pct"]
            elif window == "IS":
                decision, code, reason = classify_is(summary)
                record.update(status="OK", decision=decision, gate_code=code, reason=reason)
                record["profit_ratio"] = summary["net"] / BASELINE_IS["net"]
                record["pf_ratio"] = summary["pf"] / BASELINE_IS["pf"]
                record["dd_delta"] = summary["dd_pct"] - BASELINE_IS["dd_pct"]
                record.update(is_net=summary["net"], is_pf=summary["pf"], is_dd_pct=summary["dd_pct"],
                              is_dd_below_30=summary["dd_pct"] < 30)
            elif window == "OOS":
                latest = latest_rows()
                is_row = latest[(proposal_id, "IS")]
                baseline_row = latest[("BASELINE_OOS", "OOS")]
                base_oos = {key: float(baseline_row[key]) for key in ("net", "pf", "dd_pct")}
                decision, code, reason = classify_oos(is_row, summary, base_oos)
                record.update(status="OK", decision=decision, gate_code=code, reason=reason)
                record["profit_ratio"] = summary["net"] / base_oos["net"]
                record["pf_ratio"] = summary["pf"] / base_oos["pf"]
                record["dd_delta"] = summary["dd_pct"] - base_oos["dd_pct"]
                record.update(
                    is_net=is_row["net"], is_pf=is_row["pf"], is_dd_pct=is_row["dd_pct"],
                    is_dd_below_30=float(is_row["dd_pct"]) < 30,
                    oos_net=summary["net"], oos_pf=summary["pf"], oos_dd_pct=summary["dd_pct"],
                    oos_dd_below_30=summary["dd_pct"] < 30,
                )
    except NotImplementedError as exc:
        record.update(status="UNVERIFIED", decision="UNVERIFIED_EA_INPUT",
                      gate_code="EA_INPUT_MISSING", reason=str(exc), error=repr(exc))
    except subprocess.TimeoutExpired as exc:
        record.update(status="FAILED", decision="RUN_FAILED", gate_code="TIMEOUT",
                      reason=str(exc), error=repr(exc))
    except Exception as exc:
        record.update(status="FAILED", decision="RUN_FAILED", gate_code=type(exc).__name__,
                      reason=str(exc), error=traceback.format_exc(limit=10))
    record["finished_at"] = utc_now()
    record["elapsed_seconds"] = f"{time.monotonic() - started:.3f}"
    append_result(record)
    progress(f"RUN_END id={proposal_id} window={window} terminal={terminal.name} status={record.get('status')} "
             f"decision={record.get('decision')} elapsed={record['elapsed_seconds']}s")
    return record


def completed(row: dict[str, str] | None, args: argparse.Namespace) -> bool:
    if not row or row.get("ea_sha256") != ea_sha():
        return False
    if args.retry_failed and row.get("status") in {"FAILED", "INVALID"}:
        return False
    if args.retry_unverified and row.get("status") == "UNVERIFIED":
        return False
    return True


def select_proposals(args: argparse.Namespace) -> list[dict[str, str]]:
    rows = [row for row in read_csv(PROPOSALS) if row["implementation_class"].startswith("2")]
    if args.family:
        rows = [row for row in rows if row["family"] in set(args.family)]
    if args.proposal_id:
        rows = [row for row in rows if row["id"] in set(args.proposal_id)]
    return rows


def ensure_regression(args: argparse.Namespace, latest: dict[tuple[str, str], dict[str, str]],
                      terminal: TerminalSpec, launch_gate: LaunchGate) -> None:
    if not args.sha_regression_gate:
        progress("REGRESSION_GATE disabled")
        return
    for window in ("IS", "FULL"):
        key = ("REGRESSION_BASELINE", window)
        row = latest.get(key)
        if completed(row, args) and row.get("regression_pass") == "True":
            progress(f"SKIP_REGRESSION window={window} reason=existing exact pass")
            continue
        result = execute(None, window, args, terminal, launch_gate, purpose="regression")
        latest[key] = {key2: str(value) for key2, value in result.items()}
        if result.get("decision") != "REGRESSION_PASS":
            raise RuntimeError(f"regression gate failed for {window}; proposals blocked")


def ensure_oos_baseline(args: argparse.Namespace, latest: dict[tuple[str, str], dict[str, str]],
                        state_lock: threading.Lock, terminal: TerminalSpec,
                        launch_gate: LaunchGate) -> None:
    # Multiple survivor workers can arrive together. Exactly one may measure
    # and publish the shared held-out baseline.
    with OOS_BASELINE_LOCK:
        key = ("BASELINE_OOS", "OOS")
        with state_lock:
            row = latest.get(key)
        if completed(row, args) and row.get("status") == "OK":
            progress("SKIP_BASELINE_OOS reason=existing actual measurement")
            return
        result = execute(None, "OOS", args, terminal, launch_gate, purpose="oos_baseline")
        with state_lock:
            latest[key] = {key2: str(value) for key2, value in result.items()}
        if result.get("status") != "OK":
            raise RuntimeError("OOS baseline measurement failed")


class RunBudget:
    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.started = 0
        self._lock = threading.Lock()

    def claim(self) -> bool:
        with self._lock:
            if self.limit is not None and self.started >= self.limit:
                return False
            self.started += 1
            return True


class QueueStats:
    def __init__(self) -> None:
        self.skipped = 0
        self.gated = 0
        self._lock = threading.Lock()

    def add(self, field: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + amount)


def run_queue(args: argparse.Namespace) -> None:
    latest = latest_rows()
    terminals = TERMINALS[:args.terminal_count]
    launch_gate = LaunchGate(args.start_stagger_seconds)
    ensure_regression(args, latest, terminals[0], launch_gate)
    if args.regression_only:
        return
    stages = {"all": ("IS", "OOS"), "is": ("IS",), "oos": ("OOS",)}[args.stage]
    selected = select_proposals(args)
    jobs: Queue[tuple[int, dict[str, str]]] = Queue()
    for ordinal, proposal in enumerate(selected, 1):
        jobs.put((ordinal, proposal))
    state_lock = threading.Lock()
    budget = RunBudget(args.limit)
    stats = QueueStats()
    stop = threading.Event()
    errors: Queue[str] = Queue()

    def process_proposal(ordinal: int, proposal: dict[str, str], terminal: TerminalSpec) -> None:
        route, route_reason = screening_plan(proposal)
        with state_lock:
            existing_is = latest.get((proposal["id"], "IS"))
        has_completed_is = completed(existing_is, args)
        if "IS" in stages and route == SCREEN_ROUTE_STAGED and not has_completed_is:
            screen_key = (proposal["id"], "SCREEN_IS")
            with state_lock:
                screen_row = latest.get(screen_key)
            if completed(screen_row, args):
                stats.add("skipped")
                progress(f"SKIP_EXISTING [{ordinal}/{len(selected)}] id={proposal['id']} window=SCREEN_IS")
            else:
                if args.dry_run:
                    progress(f"DRY_RUN [{ordinal}/{len(selected)}] id={proposal['id']} window=SCREEN_IS")
                    return
                if not budget.claim():
                    stop.set()
                    return
                result = execute(proposal, "SCREEN_IS", args, terminal, launch_gate)
                with state_lock:
                    latest[screen_key] = {key: str(value) for key, value in result.items()}
                    screen_row = latest[screen_key]
                if result.get("status") in {"FAILED", "INVALID", "UNVERIFIED"}:
                    return
            if not (screen_row and screen_row.get("status") == "OK" and
                    screen_row.get("decision", "").startswith("SCREEN_PASS")):
                stats.add("gated")
                detail = "missing SCREEN_IS result" if not screen_row else (
                    f"decision={screen_row.get('decision')} net={screen_row.get('net')} "
                    f"PF={screen_row.get('pf')} DD={screen_row.get('dd_pct')}%"
                )
                progress(f"GATE_SKIP id={proposal['id']} window=IS reason=SINGLE_SLEEVE_INFERIOR {detail}")
                return
        elif "IS" in stages and route == SCREEN_ROUTE_DIRECT:
            progress(f"SCREEN_BYPASS [{ordinal}/{len(selected)}] id={proposal['id']} "
                     f"route={route} reason={route_reason}")
        elif "IS" in stages and has_completed_is:
            progress(f"SCREEN_SKIP_EXISTING_FULLBOOK [{ordinal}/{len(selected)}] id={proposal['id']} "
                     "reason=existing fullbook IS retained")
        for window in stages:
            key = (proposal["id"], window)
            with state_lock:
                existing = latest.get(key)
            if completed(existing, args):
                stats.add("skipped")
                progress(f"SKIP_EXISTING [{ordinal}/{len(selected)}] id={proposal['id']} window={window}")
                continue
            if window == "OOS":
                with state_lock:
                    is_row = latest.get((proposal["id"], "IS"))
                if not (is_row and is_row.get("status") == "OK" and
                        is_row.get("decision", "").startswith("IS_SURVIVOR")):
                    stats.add("gated")
                    detail = "missing IS result" if not is_row else (
                        f"decision={is_row.get('decision')} net={is_row.get('net')} "
                        f"PF={is_row.get('pf')} DD={is_row.get('dd_pct')}%")
                    progress(f"GATE_SKIP id={proposal['id']} window=OOS reason=IS_NOT_SURVIVOR {detail}")
                    continue
                # Measure the held-out baseline lazily: a queue with no IS
                # survivors must not spend an unnecessary MT5 run on OOS.
                ensure_oos_baseline(args, latest, state_lock, terminal, launch_gate)
            if args.dry_run:
                progress(f"DRY_RUN [{ordinal}/{len(selected)}] id={proposal['id']} window={window}")
                continue
            if not budget.claim():
                stop.set()
                return
            result = execute(proposal, window, args, terminal, launch_gate)
            with state_lock:
                latest[key] = {key2: str(value) for key2, value in result.items()}
            if result.get("status") in {"FAILED", "INVALID", "UNVERIFIED"}:
                break

    def worker(terminal: TerminalSpec) -> None:
        while not stop.is_set():
            try:
                ordinal, proposal = jobs.get_nowait()
            except Empty:
                return
            try:
                process_proposal(ordinal, proposal, terminal)
            except Exception:
                errors.put(f"terminal={terminal.name} proposal={proposal['id']}\n{traceback.format_exc()}")
                stop.set()
            finally:
                jobs.task_done()

    threads = [threading.Thread(target=worker, args=(terminal,), name=f"oafx-{terminal.name}")
               for terminal in terminals]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if args.limit is not None and budget.started >= args.limit:
        progress(f"LIMIT_REACHED actual_proposal_runs={budget.started}")
    progress(f"QUEUE_SUMMARY selected={len(selected)} started={budget.started} "
             f"skipped={stats.skipped} gated={stats.gated}")
    if not errors.empty():
        raise RuntimeError("parallel worker failed:\n" + errors.get())


def self_check() -> None:
    proposals = read_csv(PROPOSALS)
    class2 = [row for row in proposals if row["implementation_class"].startswith("2")]
    class3 = [row for row in proposals if row["implementation_class"].startswith("3")]
    if len(proposals) != 1000 or len({row["id"] for row in proposals}) != 1000:
        raise AssertionError("proposal registry must contain exactly 1,000 unique IDs")
    if len(class2) != 900 or len(class3) != 100:
        raise AssertionError(f"unexpected implementation split: class2={len(class2)} class3={len(class3)}")
    unverified = read_csv(UNVERIFIED)
    if len(unverified) != 100 or any(not row["reason"] for row in unverified):
        raise AssertionError("all 100 class-3 proposals need individual unverified reasons")
    known = ea_inputs()
    missing = {}
    for row in class2:
        absent = sorted(set(json.loads(row["parameter_json"])) - known)
        if absent:
            missing[row["id"]] = absent
    if missing:
        raise AssertionError(f"proposal inputs missing from SIMVERIFY: {missing}")
    route_counts = {SCREEN_ROUTE_STAGED: 0, SCREEN_ROUTE_DIRECT: 0}
    direct_families: dict[str, int] = {}
    for row in class2:
        route, reason = screening_plan(row)
        if not reason:
            raise AssertionError(f"screening reason missing: {row['id']}")
        route_counts[route] += 1
        if route == SCREEN_ROUTE_DIRECT:
            direct_families[row["family"]] = direct_families.get(row["family"], 0) + 1
    if route_counts != {SCREEN_ROUTE_STAGED: 725, SCREEN_ROUTE_DIRECT: 175}:
        raise AssertionError(f"unexpected screening routes: {route_counts}")
    screen_cfg = base_config("SCREEN_IS", "self_check", "self_check.csv")
    enabled = {name for name, value in screen_cfg["parameters"].items()
               if name.startswith("En_") and value is True}
    if enabled != {"En_SCA_GBPJPY"} or screen_cfg.get("model") != "every_tick":
        raise AssertionError(f"invalid SCREEN_IS config: enabled={enabled}, model={screen_cfg.get('model')}")
    defaults = parse_args([])
    if defaults.sha_regression_gate or defaults.magic_gate:
        raise AssertionError("regression and magic gates must default OFF")
    if defaults.terminal_count != DEFAULT_TERMINAL_COUNT:
        raise AssertionError("all verified terminals must be enabled by default")
    if defaults.start_stagger_seconds != TERMINAL_START_STAGGER_SECONDS:
        raise AssertionError("unexpected terminal launch stagger default")
    synthetic = [
        ProcessInfo(10, 1, "terminal64.exe", str(TERMINALS[0].executable), ""),
        ProcessInfo(11, 10, "metatester64.exe", str(TERMINALS[0].tester_executable), ""),
        ProcessInfo(20, 1, "terminal64.exe", str(TERMINALS[1].executable), ""),
        ProcessInfo(21, 20, "metatester64.exe", str(TERMINALS[1].tester_executable), ""),
    ]
    prod_processes = terminal_processes(synthetic, TERMINALS[0])
    if [[proc.pid for proc in group] for group in prod_processes] != [[10], [11]]:
        raise AssertionError("terminal-specific process ownership failed")
    known_deals = deal_metrics(ROOT / "deals" / "oafx_regression_simverify_full_deals.csv")
    if not all_magics_present(known_deals):
        raise AssertionError("known nine-magic regression log was rejected")
    forced_missing = dict(known_deals)
    forced_missing["carry_rows"] = 0
    if all_magics_present(forced_missing):
        raise AssertionError("synthetic missing-magic case was not rejected")
    print(json.dumps({
        "self_check": "OK", "proposals": len(proposals), "executable": len(class2),
        "large_dev_unverified": len(class3), "families": len({row["family"] for row in proposals}),
        "sha_regression_gate_default": defaults.sha_regression_gate,
        "magic_gate_default": defaults.magic_gate, "run_timeout_default": defaults.run_timeout,
        "terminal_count_default": defaults.terminal_count,
        "start_stagger_seconds": defaults.start_stagger_seconds,
        "terminal_process_isolation": "PASS",
        "stale_tester_seconds": STALE_TESTER_SECONDS,
        "screening_routes": route_counts, "fullbook_direct_families": direct_families,
        "screen_model": screen_cfg["model"], "screen_enabled": sorted(enabled),
        "magic_positive_case": "PASS", "magic_negative_case": "REJECT",
    }, ensure_ascii=False), flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "is", "oos"), default="all")
    parser.add_argument("--family", action="append")
    parser.add_argument("--proposal-id", action="append")
    parser.add_argument("--limit", type=int, help="maximum actual proposal runs; baseline/gates excluded")
    parser.add_argument("--run-timeout", type=int, default=DEFAULT_RUN_TIMEOUT)
    parser.add_argument("--terminal-wait-timeout", type=int, default=None)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--terminal-count", type=int, default=DEFAULT_TERMINAL_COUNT,
                        help=f"number of verified terminals to use (1-{len(TERMINALS)})")
    parser.add_argument("--start-stagger-seconds", type=float, default=TERMINAL_START_STAGGER_SECONDS,
                        help="minimum interval between any two MT5 launches")
    parser.add_argument("--sha-regression-gate", action="store_true")
    parser.add_argument("--magic-gate", action="store_true")
    parser.add_argument("--regression-only", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-unverified", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    if not 1 <= args.terminal_count <= len(TERMINALS):
        raise ValueError(f"--terminal-count must be between 1 and {len(TERMINALS)}")
    if args.start_stagger_seconds < 0:
        raise ValueError("--start-stagger-seconds must be non-negative")
    enabled_terminals = TERMINALS[:args.terminal_count]
    for directory in (ROOT, CONFIG_DIR, LOG_DIR, DEAL_DIR, COMMON_FILES):
        directory.mkdir(parents=True, exist_ok=True)
    ensure_outputs()
    verify_runtime(enabled_terminals)
    if args.self_check:
        self_check()
        return 0
    with driver_lock():
        progress(f"DRIVER_START pid={os.getpid()} stage={args.stage} targets={len(select_proposals(args))} "
                 f"terminals={','.join(t.name for t in enabled_terminals)} "
                 f"stagger={args.start_stagger_seconds:g}s sha_gate={args.sha_regression_gate} "
                 f"magic_gate={args.magic_gate}")
        run_queue(args)
        progress("DRIVER_END status=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
