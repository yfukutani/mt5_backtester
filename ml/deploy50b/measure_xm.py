"""XM構成（GOLD 2枠 ＋ 暗号3枠）を口座50万で測る。OANDA側と同一条件・同一時期。

【EAの選択】検証用の MIX_EA_SIMVERIFY.mq5 には採用済みの
「PB GOLD 保有上限64バー」（GoldPBHoldBars）が実装されていない。本番XM版の
MIX_EA.mq5 にのみ入っている。OANDA側は SIMVERIFY に GoldPBHoldBars があり
本番と等価なので、XM側は本番EAそのものを使って条件を揃える。

【比較の公平性】OANDA側（ml/deploy50b/measure.py）と同じ日・同じスワップ率で測る。
測定日が違うと同じ取引でも損益が動く（docs/sca_gold_exit_20260904.md §4）。
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
OUT = ROOT / "results_xm.csv"
LOG = ROOT / "measure_xm.log"
MT5BT = REPO / "mt5bt.bat"

DEPOSIT = 500000
RUN_TIMEOUT = 5400

# XM端末は2つある。暗号のティックデータが重いので2並列まで。
TERMINALS = [
    ("XM1", r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"),
]

WINDOWS = {
    "IS":   ("2021.06.21", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}

# XM構成: GOLD 2枠 ＋ 暗号3枠。採用済みの改善はEA既定に入っている
# （RR1.8/1.7、UseGoldHourGate=true、GoldPBHoldBars=64）。
XM_PARAMS = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
    "En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True,
    "En_SCA_GOLD": True, "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
    "UseGoldHourGate": True, "GoldPBHoldBars": 64,
}
XM_MULT_KEYS = ["Mult_PB_GOLD", "Mult_SCA_GOLD", "Mult_ETH",
                "Mult_BTC_FUND", "Mult_BFXREV"]
# GOLD単体との比較用に、暗号を切った構成も測る
XM_GOLD_ONLY = dict(XM_PARAMS)
XM_GOLD_ONLY.update({"En_ETH": False, "En_BTC_FUND": False, "En_BFXREV": False})

BOOKS = {
    "XM5":   (XM_PARAMS, XM_MULT_KEYS, [1, 3, 5, 8, 10, 15]),
    "XMGOLD": (XM_GOLD_ONLY, ["Mult_PB_GOLD", "Mult_SCA_GOLD"], [1, 5]),
}

_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    with _lock:
        print(line, flush=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def write_config(run_id: str, exe: str, book: str, mult: int, window: str) -> Path:
    params, mult_keys, _ = BOOKS[book]
    frm, to, _ = WINDOWS[window]
    merged = dict(params)
    for k in mult_keys:
        merged[k] = float(mult)
    merged["ResultFileName"] = f"{run_id}_result.csv"
    merged["EquityLogFile"] = f"{run_id}_deals.csv"
    lines = [
        f"mt5_path: {exe}", "expert: MIX_EA", "symbol: USDJPY", "period: M15",
        f"from_date: {frm}", f"to_date: {to}", f"deposit: {DEPOSIT}",
        "currency: JPY", "leverage: 25", "model: every_tick", "parameters:",
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
    log(f"RUN_START book={book} x{mult} window={window}")
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
    jobs = [(b, m, w) for b, (_, _, mults) in BOOKS.items() for m in mults for w in WINDOWS]
    work: "queue.Queue" = queue.Queue()
    for j in jobs:
        work.put(j)
    results: list[dict] = []
    log(f"MEASURE_START jobs={len(jobs)} deposit={DEPOSIT} expert=MIX_EA")

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
