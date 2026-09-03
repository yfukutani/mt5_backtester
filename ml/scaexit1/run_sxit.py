"""SCA GOLD 利確側ラウンド（scaexit1）の無人走査ドライバ。\n\npprot1 の run_pprot.py を土台にしている。相違点は対象ディレクトリと、\n基準を本ラウンド内で測り直す点（スワップ率のドリフト対策）。

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
import hashlib
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
ROOT = REPO / "ml" / "scaexit1"
PROPOSALS = ROOT / "proposals.csv"
RESULTS = ROOT / "results.csv"
CONFIG_DIR = ROOT / "configs"
RUN_DIR = ROOT / "runs"
DEAL_DIR = ROOT / "run_deals"
PROGRESS = ROOT / "run_sxit.log"
LOCK = ROOT / "run_sxit.lock"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files"

TERMINALS = [
    ("PROD", r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"),
    ("BT1", r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"),
    ("BT2", r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe"),
    ("BT3", r"C:\Program Files\OANDA MetaTrader 5_BT3\terminal64.exe"),
    ("BT4", r"C:\Program Files\OANDA MetaTrader 5_BT4\terminal64.exe"),
]

# 端末実行ファイル → データフォルダ（MQL5\Experts に .ex5 が置かれる）
TERMINAL_DATA = {
    "PROD": "EE0304F13905552AE0B5EAEFB04866EB",
    "BT1": "6142D304BFF2E6AB353977162D6F452C",
    "BT2": "06EBB62A36630B6356B2240C609DE508",
    "BT3": "62828C99ECDEDC6E786AB3636A65EF28",
    "BT4": "9501A6965ADC505E82257549A51CD4DE",
}
EA_NAME = "MIX_EA_OANDA_SIMVERIFY.ex5"
EA_SHA = [""]   # 起動時の検査で埋める

WINDOWS = {
    "IS": ("2021.06.21", "2026.06.20"),
    "OOS": ("2016.11.09", "2021.06.20"),
}

# ml/pprot1/baseline_{is,oos}.yaml の実測値。--rebase で測り直せる。
# 【重要】pprot1 の基準を流用しない。MT5テスターは現在のスワップ率を全履歴に一律適用する
# ため、測定日が違うと同じ取引でも損益が動く（pprot1 で IS -6,639円 = -1.6%、ノイズ帯超え）。
# 本ラウンドの基準は本ラウンド内で測り直したものを使う。両方とも起動時に読み込む。
BASELINE = {"IS": None, "OOS": None}

BASE_PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
    "En_VBO": False, "En_ETH": False, "En_SCA_GOLD": True,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64, "Oafx2LabMode": 0,
    "PprotMode": 0, "PprotSleeveMask": 0, "SxitMode": 0, "SxitSleeveMask": 0,
}

# 【2026-09-03 の実測】MT5テスターは現在のスワップ率を全履歴に一律適用するため、
# 同じ取引でも測定日が変わると損益が動く。GOLD 2枠の基準は3日で
# 417,882 → 411,243 → 391,947（-6.2%）と動いた。1時間あたり約0.6%で、
# 探している効果（数%）と同じ桁である。基準を1回だけ測って全案と比べるのは誤り。
# そこで N 案ごとに基準を測り直し、各結果には「そのとき使った基準」を記録する。
REBASE_EVERY = 20

RUN_TIMEOUT = 1200          # 実測205〜300秒。これを超えたら異常とみなす
STALE_GRACE = 60

# 【2026-09-02 の実測】XAUUSD の every_tick は metatester64 1つで 3.7〜4.8GB を使う。
# 5端末並列だと最大24GBとなり搭載27.9GBを実質的に食い潰し、空き1.3GB(5%)まで落ちて
# ページングで全体が停止した（17時間の空費の実質的な原因。スリープは引き金にすぎない）。
# 3端末なら最大約14GBで収まる。増やす場合は必ず空きメモリを実測してから。
MAX_TERMINALS = 3

FIELDS = [
    "attempt_id", "run_id", "proposal_id", "family", "combo", "window", "terminal",
    "status", "decision", "gate_code", "reason", "returncode",
    "net", "pf", "dd_pct", "trades",
    "net_ratio", "pf_ratio", "dd_delta", "trade_ratio",
    "baseline_net", "baseline_pf", "baseline_dd", "baseline_trades", "baseline_at",
    "baseline_pb", "baseline_sca", "pb_gold", "sca_gold", "sca_net_ratio", "pb_drift",
    "ea_sha256",
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


_baseline_lock = threading.Lock()
BASELINE_AT: dict[str, str] = {"IS": "", "OOS": ""}
BASELINES_CSV_FIELDS = ["measured_at", "window", "net", "pf", "dd", "trades",
                        "pb_gold", "sca_gold", "run_id"]

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


def sleeve_net(deal_path: Path) -> tuple[float, float]:
    """PB GOLD / SCA GOLD の枠別純益（円）。PB GOLDは本ラウンドで一切触らないので、
    スワップ率がどれだけ動いたかの目安になる。"""
    pb = sca = 0.0
    if not deal_path.exists():
        return (0.0, 0.0)
    try:
        for r in csv.DictReader(open(deal_path, encoding="utf-8")):
            m = int(r["magic"])
            if m == 20260640:
                pb += float(r["profit_jpy"])
            elif m == 20261002:
                sca += float(r["profit_jpy"])
    except (OSError, ValueError, KeyError):
        return (0.0, 0.0)
    return (pb, sca)


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
    sca = ""
    if b.get("sca"):
        sca = f", SCA枠={v.get('sca_gold', 0):.0f} ({100*(v.get('sca_gold', 0)/b['sca']-1):+.2f}%)"
    return (f"{window} net={v['net']:.0f} ({100*(v['net']/b['net']-1):+.2f}%), "
            f"PF={v['pf']:.4f} ({100*(v['pf']/b['pf']-1):+.2f}%), "
            f"DD={v['dd_pct']:.4f}% ({v['dd_pct']-b['dd']:+.4f}pt), "
            f"trades={v['trades']} ({100*(v['trades']/b['trades']-1):+.2f}%){sca}")


def classify_is(v: dict) -> tuple[str, str, str]:
    b = BASELINE["IS"]
    reason = detail("IS", v, b)
    trade_ratio = v["trades"] / b["trades"]
    # 【判定はSCA GOLD枠で行う】理由は2つ。
    #  (1) 本ラウンドが触るのはSCA GOLDだけで、PB GOLD側は無改変。ブック全体で見ると
    #      効果が約半分に薄まる。
    #  (2) スワップ率のドリフトは保有時間に比例する。実測でPB GOLD(中央56h)は2日で-8.2%、
    #      SCA GOLD(中央8.5h)は-0.8%。ブック全体で判定するとPB GOLD側のドリフトが
    #      効果と同じ桁のノイズとして乗る。
    net_ratio = (v["sca_gold"] / b["sca"]) if b.get("sca") else (v["net"] / b["net"])
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
    net_ratio = (v["sca_gold"] / b["sca"]) if b.get("sca") else (v["net"] / b["net"])
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
    run_id = f"sx_{window.lower()}_{proposal['proposal_id']}_{stamp}_{uuid.uuid4().hex[:6]}"
    params = json.loads(proposal["parameter_json"])
    cfg = write_config(run_id, exe, window, params)

    row = {
        "attempt_id": uuid.uuid4().hex,
        "run_id": run_id,
        "proposal_id": proposal["proposal_id"],
        "family": proposal["family"],
        "combo": proposal.get("combo", ""),
        "window": window,
        "terminal": name,
        "parameter_json": proposal["parameter_json"],
        "config_file": str(cfg.relative_to(REPO)),
        "deal_file": f"{run_id}_deals.csv",
        "started_at": utc_now(),
        "ea_sha256": EA_SHA[0],
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

    with _baseline_lock:
        b = dict(BASELINE[window])
        row["baseline_at"] = BASELINE_AT[window]
    row.update(status="OK", **{k: value[k] for k in ("net", "pf", "dd_pct", "trades")})
    row["net_ratio"] = round(value["net"] / b["net"], 6)
    row["pf_ratio"] = round(value["pf"] / b["pf"], 6)
    row["dd_delta"] = round(value["dd_pct"] - b["dd"], 4)
    row["trade_ratio"] = round(value["trades"] / b["trades"], 6)
    row["baseline_net"] = b["net"]
    row["baseline_pf"] = b["pf"]
    row["baseline_dd"] = b["dd"]
    row["baseline_trades"] = b["trades"]
    row["baseline_pb"] = b.get("pb", "")
    row["baseline_sca"] = b.get("sca", "")

    # dealログを退避（Common\Files は上書きされるため）
    src = COMMON / f"{run_id}_deals.csv"
    dst = DEAL_DIR / f"{run_id}_deals.csv"
    if src.exists():
        try:
            src.replace(dst)
        except OSError:
            dst = src
    pb, sca = sleeve_net(dst)
    row["pb_gold"] = round(pb)
    row["sca_gold"] = round(sca)
    if b.get("sca"):
        row["sca_net_ratio"] = round(sca / b["sca"], 6)
    if b.get("pb"):
        # PB GOLD は本ラウンドで触らない。ここがゼロから離れていれば
        # その時点でスワップ率が基準測定時からずれている。
        row["pb_drift"] = round(pb - b["pb"])

    # 結果を読み終えたら端末を落としてメモリを返す。
    # mt5bt は run ごとに端末を起動し直すため、ここで落としても次の run に影響しない。
    # 落とさないと metatester64 が完了後も 1.4〜4.8GB を保持したまま残り、
    # 次の run のテスターと重なって同一端末に2プロセスが並ぶ（結果を壊しうる状態）。
    kill_terminal(exe)
    return row


def rebase(name: str, exe: str, window: str) -> None:
    """基準を測り直して差し替える。走査中のスワップ率ドリフトを追随するため。"""
    proposal = {"proposal_id": "BASELINE", "family": "baseline", "combo": "-",
                "parameter_json": json.dumps({})}
    row = run_once(name, exe, proposal, window)
    if row["status"] != "OK":
        log(f"REBASE_FAILED window={window} terminal={name} — 旧基準を使い続ける")
        return
    with _baseline_lock:
        old_net = BASELINE[window]["net"] if BASELINE[window] else 0.0
        BASELINE[window] = {"net": row["net"], "pf": row["pf"],
                            "dd": row["dd_pct"], "trades": row["trades"],
                            "pb": row["pb_gold"], "sca": row["sca_gold"]}
        BASELINE_AT[window] = row["finished_at"]
    drift = (row["net"] / old_net - 1.0) * 100 if old_net else 0.0
    log(f"REBASE window={window} net={row['net']:.0f} pb={row['pb_gold']} "
        f"sca={row['sca_gold']} 前回比={drift:+.2f}%")
    path = ROOT / "baselines.csv"
    exists = path.exists()
    with _write_lock:
        with open(path, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=BASELINES_CSV_FIELDS)
            if not exists:
                w.writeheader()
            w.writerow({"measured_at": row["finished_at"], "window": window,
                        "net": row["net"], "pf": row["pf"], "dd": row["dd_pct"],
                        "trades": row["trades"], "pb_gold": row["pb_gold"],
                        "sca_gold": row["sca_gold"], "run_id": row["run_id"]})


_since_rebase = [0]
_rebase_lock = threading.Lock()


def maybe_rebase(name: str, exe: str) -> None:
    with _rebase_lock:
        _since_rebase[0] += 1
        due = _since_rebase[0] >= REBASE_EVERY
        if due:
            _since_rebase[0] = 0
    if due:
        rebase(name, exe, "IS")
        rebase(name, exe, "OOS")


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
                {"net": row["net"], "pf": row["pf"], "dd_pct": row["dd_pct"],
                 "trades": row["trades"], "sca_gold": row["sca_gold"]})
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
                    "net": orow["net"], "pf": orow["pf"], "dd_pct": orow["dd_pct"],
                    "trades": orow["trades"], "sca_gold": orow["sca_gold"]})
                orow.update(decision=od, gate_code=og, reason=oreason)
                log(f"RUN_END id={pid} window=OOS decision={od} elapsed={orow['elapsed_seconds']}s")
            append_result(orow)
            maybe_rebase(name, exe)
        except Exception as exc:  # noqa: BLE001
            log(f"WORKER_ERROR terminal={name} id={proposal.get('proposal_id')} err={exc!r}")
        finally:
            work.task_done()


def verify_ea_deployed(names: list[str]) -> str:
    """使う全端末に同一の .ex5 が配備されているか検査する。

    【2026-09-03 の事故】SXITラボを実装した後、コンパイル先の BT1 にしか .ex5 を
    配備しなかった。MT5は**未知のSETパラメータを黙って無視する**ため、旧バイナリの
    端末では「設定したのにOFFのままの結果」が出て、それが正常値のように記録された
    （gold_dd2 の UNVERIFIED_EA_INPUT と同じ罠）。走査前に必ず突き合わせる。
    """
    root = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    digests: dict[str, str] = {}
    for name in names:
        folder = TERMINAL_DATA.get(name)
        if folder is None:
            raise SystemExit(f"端末 {name} のデータフォルダが未登録")
        path = root / folder / "MQL5" / "Experts" / EA_NAME
        if not path.exists():
            raise SystemExit(f"端末 {name} に {EA_NAME} が無い: {path}")
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    uniq = set(digests.values())
    if len(uniq) != 1:
        detail = " / ".join(f"{k}={v[:16]}" for k, v in digests.items())
        raise SystemExit(
            "端末ごとに .ex5 が違う。旧バイナリの端末では新しい入力が黙って無視され、"
            f"偽の測定値が出る。全端末に配備し直すこと: {detail}")
    return uniq.pop()


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


def load_baseline(window: str) -> None:
    """本ラウンドで測った基準を読む。"""
    if BASELINE[window] is not None:
        return
    name = f"scaexit1_baseline_{window.lower()}"
    for base in (ROOT / "runs", REPO / "results", Path.cwd() / "results"):
        p = base / name / "summary.csv"
        if p.exists():
            vals: dict[str, str] = {}
            for row in csv.reader(open(p, encoding="utf-8")):
                if len(row) >= 2:
                    vals[row[0]] = row[1]
            pb, sca = sleeve_net(COMMON / f"scaexit1_baseline_{window.lower()}_deals.csv")
            BASELINE[window] = {
                "net": float(vals["純利益"]), "pf": float(vals["プロフィットファクター"]),
                "dd": float(vals["最大相対DD%"]), "trades": int(float(vals["総取引数"])),
                "pb": pb, "sca": sca,
            }
            log(f"BASELINE_{window} {BASELINE[window]}")
            return
    raise SystemExit(f"{window}基準が見つからない。先に baseline_{window.lower()}.yaml を実行すること。")


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
        names = [n for n, _ in TERMINALS[:args.terminals]]
        EA_SHA[0] = verify_ea_deployed(names)
        log(f"EA_VERIFIED sha256={EA_SHA[0]} terminals={','.join(names)}")
        log(f"MEMORY_FREE_MB {free_memory_mb():.0f} terminals={args.terminals}")
        load_baseline("IS")
        load_baseline("OOS")

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
