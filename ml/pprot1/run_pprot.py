"""利益保護ラウンド1の無人走査ドライバ。

OANDA 5端末を並列に使い、提案500件を IS で測り、IS を通過したものだけ OOS を測る。

## 設計上の前提（過去ラウンドの失敗から）

* 1端末=1データフォルダ。**同じ端末で2つのテストを同時に走らせない**（gold_dd2 §5.1 で
  結果を壊した実績がある）。ロックファイルで二重起動も禁止する。
* タイムアウト後の後始末が滞留して25時間を空費した実績がある（gold_dd2 §5.2）ため、
  タイムアウト時は**その端末のプロセスだけ**を実行ファイルパスで特定して落とす。
* 「取引ゼロ」は成績ではない。基準比で取引が激減した案は SLEEVE_STOPPED として
  成績から外す（gold_dd2 §4 で損失ゼロが好成績に見えた問題）。

再開可能。results.csv に成功記録がある (proposal_id, window) は再測定しない。
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "pprot1"
PROPOSALS = ROOT / "proposals.csv"
RESULTS = ROOT / "results.csv"
CONFIG_DIR = ROOT / "configs"
RUN_DIR = ROOT / "runs"
DEAL_DIR = ROOT / "run_deals"
PROGRESS = ROOT / "run_pprot.log"
LOCK = ROOT / "run_pprot.lock"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files"

TERMINALS = [
    ("PROD", r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"),
    ("BT1", r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"),
    ("BT2", r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe"),
    ("BT3", r"C:\Program Files\OANDA MetaTrader 5_BT3\terminal64.exe"),
    ("BT4", r"C:\Program Files\OANDA MetaTrader 5_BT4\terminal64.exe"),
]

WINDOWS = {
    "IS": ("2021.06.21", "2026.06.20"),
    "OOS": ("2016.11.09", "2021.06.20"),
}

# ml/pprot1/baseline_{is,oos}.yaml の実測値。--rebase で測り直せる。
BASELINE = {
    "IS": {"net": 417882.0, "pf": 2.2542, "dd": 3.7942, "trades": 301},
    "OOS": None,   # 起動時に baseline_oos.yaml の結果から読み込む
}

BASE_PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
    "En_VBO": False, "En_ETH": False, "En_SCA_GOLD": True,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64, "Oafx2LabMode": 0,
}

RUN_TIMEOUT = 1200          # 実測205〜300秒。これを超えたら異常とみなす
STALE_GRACE = 60

# 【2026-09-02 の実測】XAUUSD の every_tick は metatester64 1つで 3.7〜4.8GB を使う。
# 5端末並列だと最大24GBとなり搭載27.9GBを実質的に食い潰し、空き1.3GB(5%)まで落ちて
# ページングで全体が停止した（17時間の空費の実質的な原因。スリープは引き金にすぎない）。
# 3端末なら最大約14GBで収まる。増やす場合は必ず空きメモリを実測してから。
MAX_TERMINALS = 3

FIELDS = [
    "attempt_id", "run_id", "proposal_id", "family", "target", "window", "terminal",
    "status", "decision", "gate_code", "reason", "returncode",
    "net", "pf", "dd_pct", "trades",
    "net_ratio", "pf_ratio", "dd_delta", "trade_ratio",
    "parameter_json", "config_file", "deal_file",
    "started_at", "finished_at", "elapsed_seconds", "error",
]

# 走行中の run を端末ごとに記録する。実時計のウォッチドッグが参照する。
#
# 【2026-09-01 の事故】PCが走行中にスリープし（イベントログ 08-31 12:10:55 sleep /
# 12:10:59 resume）、5端末の metatester64 が固着して約17時間を空費した。
# subprocess.run(timeout=) は発火しなかった（elapsed 60,244秒でNO_SUMMARY復帰）。
# Windows ではサスペンド中に単調時計が進まないことがあり、サブプロセスのタイムアウトだけ
# では停止を検出できない。前ラウンド oafx_dd2 は keepawake.py で同じ事故を解決していたが
# 本ドライバへ移植していなかった。対策は二重に置く:
#   (a) SetThreadExecutionState でドライバ稼働中はスリープさせない（根本原因を断つ）
#   (b) 実時計（time.time）のウォッチドッグで、期限超過の端末だけを落とす（保険）
_inflight: dict[str, tuple[str, float]] = {}
_inflight_lock = threading.Lock()

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def suppress_sleep() -> bool:
    """ドライバが生きている間だけスリープを抑止する。電源設定自体は変更しない。"""
    try:
        prev = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:  # noqa: BLE001
        return False
    return prev != 0


def release_sleep() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:  # noqa: BLE001
        pass


def watchdog(stop: threading.Event) -> None:
    """実時計で期限を超えた run の端末だけを落とす。他ワーカーには触れない。"""
    while not stop.wait(60):
        now = time.time()
        with _inflight_lock:
            stale = [(name, exe, now - t0)
                     for name, (exe, t0) in _inflight.items()
                     if now - t0 > RUN_TIMEOUT + 120]
        for name, exe, age in stale:
            log(f"WATCHDOG_STALL terminal={name} age={age:.0f}s — 端末を落とす")
            kill_terminal(exe)
            with _inflight_lock:
                # 二重に落とさないよう、いったん記録を外す
                _inflight.pop(name, None)


_write_lock = threading.Lock()
_log_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    line = f"{utc_now()} {msg}"
    with _log_lock:
        print(line, flush=True)
        with open(PROGRESS, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def append_result(row: dict) -> None:
    with _write_lock:
        exists = RESULTS.exists()
        with open(RESULTS, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if not exists:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in FIELDS})


def load_done() -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if not RESULTS.exists():
        return done
    with open(RESULTS, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("status") == "OK":
                done.add((r["proposal_id"], r["window"]))
    return done


def kill_terminal(exe_path: str) -> None:
    """その端末の terminal64 / metatester64 だけを落とす。他ワーカーには触れない。"""
    folder = str(Path(exe_path).parent).replace("'", "''")
    ps = (
        "Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
        "Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       timeout=120, capture_output=True)
    except Exception as exc:  # noqa: BLE001
        log(f"KILL_FAILED terminal={exe_path} err={exc}")


def write_config(run_id: str, exe: str, window: str, params: dict) -> Path:
    frm, to = WINDOWS[window]
    merged = dict(BASE_PARAMS)
    merged.update(params)
    merged["ResultFileName"] = f"{run_id}_result.csv"
    merged["EquityLogFile"] = f"{run_id}_deals.csv"

    lines = [
        f"mt5_path: {exe}",
        "expert: MIX_EA_OANDA_SIMVERIFY",
        "symbol: XAUUSD",
        "period: M15",
        f"from_date: {frm}",
        f"to_date: {to}",
        "deposit: 500000",
        "currency: JPY",
        "leverage: 25",
        "model: every_tick",
        "parameters:",
    ]
    for k, v in merged.items():
        if isinstance(v, bool):
            lines.append(f"  {k}: {'true' if v else 'false'}")
        elif isinstance(v, str):
            lines.append(f"  {k}: {v}")
        else:
            lines.append(f"  {k}: {v}")
    lines += [
        f"report_dir: {RUN_DIR}",
        f"report_name: {run_id}",
        "",
    ]
    path = CONFIG_DIR / f"{run_id}.yaml"
    # PowerShell 経由で書くと BOM が付き mt5bt が先頭キーを読み違える。必ず python で書く。
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def parse_summary(run_id: str) -> dict | None:
    path = RUN_DIR / run_id / "summary.csv"
    if not path.exists():
        return None
    vals: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                vals[row[0]] = row[1]
    try:
        return {
            "net": float(vals["純利益"]),
            "pf": float(vals["プロフィットファクター"]),
            "dd_pct": float(vals["最大相対DD%"]),
            "trades": int(float(vals["総取引数"])),
        }
    except (KeyError, ValueError):
        return None


def detail(window: str, v: dict, b: dict) -> str:
    return (f"{window} net={v['net']:.0f} ({100*(v['net']/b['net']-1):+.2f}%), "
            f"PF={v['pf']:.4f} ({100*(v['pf']/b['pf']-1):+.2f}%), "
            f"DD={v['dd_pct']:.4f}% ({v['dd_pct']-b['dd']:+.4f}pt), "
            f"trades={v['trades']} ({100*(v['trades']/b['trades']-1):+.2f}%)")


def classify_is(v: dict) -> tuple[str, str, str]:
    b = BASELINE["IS"]
    reason = detail("IS", v, b)
    trade_ratio = v["trades"] / b["trades"]
    net_ratio = v["net"] / b["net"]
    dd_delta = v["dd_pct"] - b["dd"]

    # 取引が激減した案は「損失が出ないから良く見える」だけ。成績にしない。
    if trade_ratio < 0.70:
        return "SLEEVE_STOPPED", "TRADE_COUNT_BELOW_70", reason
    # 効果がノイズ帯（純益差1%未満かつDD差0.2pt未満）なら改善と見なさない
    if abs(net_ratio - 1.0) < 0.01 and abs(dd_delta) < 0.20:
        return "IS_NOISE_BAND", "EFFECT_WITHIN_NOISE_BAND", reason
    # 本ラウンドの目的は収益増強。DDを悪化させずに純益を1%以上伸ばすこと。
    if net_ratio >= 1.01 and dd_delta <= 0.50:
        return "IS_SURVIVOR_PROFIT", "PROFIT_UP_DD_OK", reason
    # 純益は横ばいでもDDが明確に下がるなら守りとして拾う
    if net_ratio >= 0.99 and dd_delta <= -0.50:
        return "IS_SURVIVOR_DD", "DD_DOWN_PROFIT_FLAT", reason
    if net_ratio < 0.99:
        return "IS_REJECT", "PROFIT_DAMAGED", reason
    return "IS_REJECT", "NO_IMPROVEMENT", reason


def classify_oos(is_reason: str, v: dict) -> tuple[str, str, str]:
    b = BASELINE["OOS"]
    reason = is_reason + "; " + detail("OOS", v, b)
    trade_ratio = v["trades"] / b["trades"]
    net_ratio = v["net"] / b["net"]
    dd_delta = v["dd_pct"] - b["dd"]

    if trade_ratio < 0.70:
        return "SLEEVE_STOPPED", "OOS_TRADE_COUNT_BELOW_70", reason
    if abs(net_ratio - 1.0) < 0.01 and abs(dd_delta) < 0.20:
        return "OOS_NOISE_BAND", "EFFECT_WITHIN_NOISE_BAND", reason
    if net_ratio >= 1.0 and dd_delta <= 0.50:
        return "ADOPT_CANDIDATE", "BOTH_WINDOWS_IMPROVED", reason
    if net_ratio >= 0.97 and dd_delta <= -0.50:
        return "ADOPT_CANDIDATE_DD", "OOS_DD_DOWN", reason
    return "OOS_REJECT", "OOS_NOT_CONFIRMED", reason


def run_once(name: str, exe: str, proposal: dict, window: str) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"pp_{window.lower()}_{proposal['proposal_id']}_{stamp}_{uuid.uuid4().hex[:6]}"
    params = json.loads(proposal["parameter_json"])
    cfg = write_config(run_id, exe, window, params)

    row = {
        "attempt_id": uuid.uuid4().hex,
        "run_id": run_id,
        "proposal_id": proposal["proposal_id"],
        "family": proposal["family"],
        "target": proposal["target"],
        "window": window,
        "terminal": name,
        "parameter_json": proposal["parameter_json"],
        "config_file": str(cfg.relative_to(REPO)),
        "deal_file": f"{run_id}_deals.csv",
        "started_at": utc_now(),
    }
    t0 = time.time()
    with _inflight_lock:
        _inflight[name] = (exe, t0)
    log(f"RUN_START id={proposal['proposal_id']} window={window} terminal={name} family={proposal['family']}")
    try:
        proc = subprocess.run(
            [str(MT5BT), "run", str(cfg), "--no-charts"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=RUN_TIMEOUT, cwd=str(REPO),
        )
        row["returncode"] = proc.returncode
    except subprocess.TimeoutExpired:
        row.update(status="FAILED", decision="RUN_FAILED", gate_code="TIMEOUT",
                   error=f"timeout>{RUN_TIMEOUT}s", returncode=-1)
        log(f"RUN_TIMEOUT id={proposal['proposal_id']} window={window} terminal={name} — 端末を再起動する")
        kill_terminal(exe)
        time.sleep(STALE_GRACE)
        row["finished_at"] = utc_now()
        row["elapsed_seconds"] = round(time.time() - t0, 3)
        return row

    finally:
        with _inflight_lock:
            _inflight.pop(name, None)

    value = parse_summary(run_id)
    row["finished_at"] = utc_now()
    row["elapsed_seconds"] = round(time.time() - t0, 3)

    if value is None:
        row.update(status="FAILED", decision="RUN_FAILED", gate_code="NO_SUMMARY",
                   error=(proc.stderr or proc.stdout or "")[-400:])
        log(f"RUN_FAILED id={proposal['proposal_id']} window={window} terminal={name} 結果CSVなし")
        return row

    b = BASELINE[window]
    row.update(status="OK", **{k: value[k] for k in ("net", "pf", "dd_pct", "trades")})
    row["net_ratio"] = round(value["net"] / b["net"], 6)
    row["pf_ratio"] = round(value["pf"] / b["pf"], 6)
    row["dd_delta"] = round(value["dd_pct"] - b["dd"], 4)
    row["trade_ratio"] = round(value["trades"] / b["trades"], 6)

    # dealログを退避（Common\Files は上書きされるため）
    src = COMMON / f"{run_id}_deals.csv"
    if src.exists():
        try:
            src.replace(DEAL_DIR / f"{run_id}_deals.csv")
        except OSError:
            pass

    # 結果を読み終えたら端末を落としてメモリを返す。
    # mt5bt は run ごとに端末を起動し直すため、ここで落としても次の run に影響しない。
    # 落とさないと metatester64 が完了後も 1.4〜4.8GB を保持したまま残り、
    # 次の run のテスターと重なって同一端末に2プロセスが並ぶ（結果を壊しうる状態）。
    kill_terminal(exe)
    return row


def worker(name: str, exe: str, work: "queue.Queue[dict]", done: set, gate_lock: threading.Lock) -> None:
    while True:
        try:
            proposal = work.get_nowait()
        except queue.Empty:
            return
        try:
            pid = proposal["proposal_id"]
            if (pid, "IS") in done:
                log(f"SKIP_EXISTING id={pid} window=IS")
                continue
            row = run_once(name, exe, proposal, "IS")
            if row["status"] != "OK":
                append_result(row)
                continue
            decision, gate, reason = classify_is(
                {"net": row["net"], "pf": row["pf"], "dd_pct": row["dd_pct"], "trades": row["trades"]})
            row.update(decision=decision, gate_code=gate, reason=reason)
            append_result(row)
            log(f"RUN_END id={pid} window=IS decision={decision} elapsed={row['elapsed_seconds']}s")

            if not decision.startswith("IS_SURVIVOR"):
                log(f"GATE_SKIP id={pid} window=OOS reason=IS_NOT_SURVIVOR decision={decision}")
                continue
            if (pid, "OOS") in done:
                log(f"SKIP_EXISTING id={pid} window=OOS")
                continue
            orow = run_once(name, exe, proposal, "OOS")
            if orow["status"] == "OK":
                od, og, oreason = classify_oos(reason, {
                    "net": orow["net"], "pf": orow["pf"],
                    "dd_pct": orow["dd_pct"], "trades": orow["trades"]})
                orow.update(decision=od, gate_code=og, reason=oreason)
                log(f"RUN_END id={pid} window=OOS decision={od} elapsed={orow['elapsed_seconds']}s")
            append_result(orow)
        except Exception as exc:  # noqa: BLE001
            log(f"WORKER_ERROR terminal={name} id={proposal.get('proposal_id')} err={exc!r}")
        finally:
            work.task_done()


def free_memory_mb() -> float:
    """空き物理メモリ(MB)。並列度が妥当かを記録に残すために使う。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
            capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip()) / 1024.0
    except Exception:  # noqa: BLE001
        return -1.0


def load_oos_baseline() -> None:
    """baseline_oos.yaml の実測結果を results ディレクトリから読む。"""
    if BASELINE["OOS"] is not None:
        return
    for base in (REPO / "results", Path.cwd() / "results", ROOT / "runs"):
        p = base / "pprot1_baseline_oos" / "summary.csv"
        if p.exists():
            vals: dict[str, str] = {}
            for row in csv.reader(open(p, encoding="utf-8")):
                if len(row) >= 2:
                    vals[row[0]] = row[1]
            BASELINE["OOS"] = {
                "net": float(vals["純利益"]), "pf": float(vals["プロフィットファクター"]),
                "dd": float(vals["最大相対DD%"]), "trades": int(float(vals["総取引数"])),
            }
            log(f"BASELINE_OOS {BASELINE['OOS']}")
            return
    raise SystemExit("OOS基準が見つからない。先に baseline_oos.yaml を実行すること。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="先頭N件だけ処理する（試走用）")
    ap.add_argument("--terminals", type=int, default=MAX_TERMINALS,
                    help="並列端末数。メモリ実測に基づき既定3。増やす前に空きメモリを確認すること")
    args = ap.parse_args()

    for d in (CONFIG_DIR, RUN_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if LOCK.exists():
        raise SystemExit(f"ロックが存在する: {LOCK}。ドライバの二重起動は結果を壊す。"
                         f"先行が本当に停止しているのを確認してから削除すること。")
    LOCK.write_text(f"pid={os.getpid()} started={utc_now()}\n", encoding="utf-8")

    stop_watchdog = threading.Event()
    if suppress_sleep():
        log("SLEEP_SUPPRESSED ドライバ稼働中はスリープしない（終了時に自動解除）")
    else:
        log("SLEEP_SUPPRESS_FAILED ⚠️スリープで走査が止まる可能性がある")

    try:
        threading.Thread(target=watchdog, args=(stop_watchdog,),
                         name="watchdog", daemon=True).start()
        log(f"MEMORY_FREE_MB {free_memory_mb():.0f} terminals={args.terminals}")
        load_oos_baseline()
        log(f"BASELINE_IS {BASELINE['IS']}")

        proposals = list(csv.DictReader(open(PROPOSALS, encoding="utf-8")))
        if args.limit:
            proposals = proposals[:args.limit]
        done = load_done()
        log(f"DRIVER_START proposals={len(proposals)} already_done={len(done)} "
            f"terminals={args.terminals}")

        work: "queue.Queue[dict]" = queue.Queue()
        for p in proposals:
            work.put(p)

        gate_lock = threading.Lock()
        threads = []
        for name, exe in TERMINALS[:args.terminals]:
            t = threading.Thread(target=worker, args=(name, exe, work, done, gate_lock),
                                 name=name, daemon=True)
            t.start()
            threads.append(t)
            time.sleep(25)   # 端末の同時起動は履歴同期で詰まる。ずらして立ち上げる。

        for t in threads:
            t.join()
        log("DRIVER_END status=OK")
    finally:
        stop_watchdog.set()
        release_sleep()
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
