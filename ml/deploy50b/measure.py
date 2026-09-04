"""口座50万円での配分を、現在のEA・現在のスワップ率で測り直す。

【なぜ測り直すか】docs/deploy50_oanda_vs_xm_20260821.md の数値は 2026-08-21 の測定。
その後、MT5テスターが「現在のスワップ率を全履歴に一律適用する」近似のせいで
基準が最大6%動くことが判明した（docs/sca_gold_exit_20260904.md §4）。
配分と月利を判断する数値は、同一セッションで測り直した値を使う。

【換算】全枠が基準ロット0.01固定、リスク建て枠も RefCap 固定なので、損益もDDも
入金額に依存しない円額として出る。入金50万で直接測れば、報告される
「最大相対DD%」がそのまま50万に対する比率になる。

月利 = 純利益 ÷ 入金額 ÷ 月数（非複利・単純割り）。docs/deploy50 と同じ定義。
"""
from __future__ import annotations

import csv
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "deploy50b"
RUN_DIR = ROOT / "runs"
CONFIG_DIR = ROOT / "configs"
OUT = ROOT / "results.csv"
LOG = ROOT / "measure.log"
MT5BT = REPO / "mt5bt.bat"

DEPOSIT = 500000
RUN_TIMEOUT = 3600

TERMINALS = [
    ("PROD", r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"),
    ("BT1", r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"),
]

WINDOWS = {
    "IS":   ("2021.06.21", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}

# CFD口座: GOLD 2枠のみ。採用済みの改善をすべて有効にする。
CFD_PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": True,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64,
}
CFD_MULT_KEYS = ["Mult_PB_GOLD", "Mult_SCA_GOLD"]
CFD_SYMBOL = "XAUUSD"

# FX口座: 10枠。GOLDと暗号は載せない。
FX_PARAMS = {
    "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
    "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
    "En_ETH": False, "En_SCA_GOLD": False,
    "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64,
    "RefCap_PB_USDJPY": 100000, "RefCap_PB_GBPJPY": 100000, "RefCap_CARRY": 100000,
}
FX_MULT_KEYS = ["Mult_PB_USDJPY", "Mult_PB_GBPJPY", "Mult_RSI_USDJPY",
                "Mult_RSI_EURUSD", "Mult_RSI_GBPUSD", "Mult_PAIR",
                "Mult_CARRY", "Mult_SCA_USDJPY", "Mult_SCA_GBPJPY"]
FX_SYMBOL = "USDJPY"

BOOKS = {
    "CFD": (CFD_PARAMS, CFD_MULT_KEYS, CFD_SYMBOL, [1, 3, 5, 6, 8, 10, 12, 15]),
    "FX":  (FX_PARAMS, FX_MULT_KEYS, FX_SYMBOL, [1, 2, 3]),
}

_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    with _lock:
        print(line, flush=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def write_config(run_id: str, exe: str, book: str, mult: int, window: str) -> Path:
    params, mult_keys, symbol, _ = BOOKS[book]
    frm, to, _ = WINDOWS[window]
    merged = dict(params)
    for k in mult_keys:
        merged[k] = float(mult)
    merged["ResultFileName"] = f"{run_id}_result.csv"
    merged["EquityLogFile"] = f"{run_id}_deals.csv"

    lines = [
        f"mt5_path: {exe}",
        "expert: MIX_EA_OANDA_SIMVERIFY",
        f"symbol: {symbol}",
        "period: M15",
        f"from_date: {frm}",
        f"to_date: {to}",
        f"deposit: {DEPOSIT}",
        "currency: JPY",
        "leverage: 25",
        "model: every_tick",
        "parameters:",
    ]
    for k, v in merged.items():
        lines.append(f"  {k}: {'true' if v is True else 'false' if v is False else v}")
    lines += [f"report_dir: {RUN_DIR}", f"report_name: {run_id}", ""]
    path = CONFIG_DIR / f"{run_id}.yaml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def parse(run_id: str) -> dict | None:
    p = RUN_DIR / run_id / "summary.csv"
    if not p.exists():
        return None
    v = {r[0]: r[1] for r in csv.reader(open(p, encoding="utf-8")) if len(r) >= 2}
    try:
        return {"net": float(v["純利益"]), "pf": float(v["プロフィットファクター"]),
                "dd_pct": float(v["最大相対DD%"]), "trades": int(float(v["総取引数"])),
                "win_pct": float(v["勝率%"])}
    except (KeyError, ValueError):
        return None


def kill_terminal(exe: str) -> None:
    folder = str(Path(exe).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       timeout=120, capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def run_one(name: str, exe: str, book: str, mult: int, window: str) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"d50b_{book.lower()}_x{mult}_{window.lower()}_{stamp}_{uuid.uuid4().hex[:4]}"
    cfg = write_config(run_id, exe, book, mult, window)
    log(f"RUN_START book={book} x{mult} window={window} terminal={name}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        log(f"RUN_TIMEOUT book={book} x{mult} window={window}")
        kill_terminal(exe)
        return {"book": book, "mult": mult, "window": window, "status": "FAILED"}

    v = parse(run_id)
    kill_terminal(exe)
    months = WINDOWS[window][2]
    row = {"book": book, "mult": mult, "window": window, "run_id": run_id,
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1),
           "deposit": DEPOSIT, "months": months}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / months, 4)
        row["rf"] = round(v["net"] / (v["dd_pct"] / 100 * DEPOSIT), 2) if v["dd_pct"] else 0
    log(f"RUN_END book={book} x{mult} {window} net={row.get('net')} "
        f"dd={row.get('dd_pct')}% 月利={row.get('monthly_pct')}% elapsed={row['elapsed']}s")
    return row


def main() -> None:
    for d in (RUN_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)
    jobs = [(b, m, w) for b, (_, _, _, mults) in BOOKS.items()
            for m in mults for w in WINDOWS]
    work: "queue.Queue" = queue.Queue()
    for j in jobs:
        work.put(j)
    results: list[dict] = []
    log(f"MEASURE_START jobs={len(jobs)} deposit={DEPOSIT}")

    def worker(name: str, exe: str) -> None:
        while True:
            try:
                book, mult, window = work.get_nowait()
            except queue.Empty:
                return
            try:
                r = run_one(name, exe, book, mult, window)
                with _lock:
                    results.append(r)
            finally:
                work.task_done()

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        threads = []
        for name, exe in TERMINALS:
            t = threading.Thread(target=worker, args=(name, exe), daemon=True)
            t.start()
            threads.append(t)
            time.sleep(25)
        for t in threads:
            t.join()
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = ["book", "mult", "window", "status", "deposit", "months", "net", "pf",
              "dd_pct", "monthly_pct", "rf", "trades", "win_pct", "elapsed", "run_id"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(results, key=lambda x: (x["book"], x["window"], x["mult"])):
            w.writerow({k: r.get(k, "") for k in fields})
    log(f"MEASURE_END rows={len(results)} -> {OUT}")


if __name__ == "__main__":
    main()
