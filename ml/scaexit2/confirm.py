"""ラウンド3の主要案を、基準と同一セッションで測り直して確定させる。

【なぜ必要か】走査中の 2026-09-03 20:28 にスワップ率が戻り、基準が
391,947 → 417,882（PB GOLD +23,928 / SCA GOLD +2,007）へジャンプした。
19:41 に走った HX0039 は新しいスワップ体制なのに古い基準と比較されており、
IS +2.88% のうち約1.06ptがスワップ由来である。
基準と候補を連続して測り、その中だけで比較する。

測る対象:
  BASELINE          現行（RR1.7・TP延長なし）
  HX0039_RR175      RRを1.75へ（唯一、少数依存でない案）
  EXT095            TPを0.95ATR延長（ISのピーク）
  EXT100            TPを1.00ATR延長（pprot1のPP0428）
  EXT150            TPを1.50ATR延長（＝TP到達不能＝TP撤廃相当。OOSの最良）
  TPATR260          TPを2.60ATR距離へ（同じくTP撤廃相当）
  RR175_EXT150      RR1.75 と TP撤廃の併用
"""
from __future__ import annotations

import csv
import json
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_hx import (  # noqa: E402
    COMMON, MT5BT, REPO, ROOT, TERMINALS, kill_terminal, release_sleep,
    sca_positions, sleeve_net, suppress_sleep, verify_ea_deployed, write_config,
)

CONFIRM_DIR = ROOT / "confirm"
OUT = ROOT / "confirm_results.csv"
LOG = ROOT / "confirm.log"
RUN_TIMEOUT = 1800

BASE = {
    "SxitMode": 0, "SxitSleeveMask": 0, "SxitRR": 0.0, "SxitTPATR": 0.0,
    "SxitTradeEndHour": -1, "SxitForceCloseHour": -1,
    "SxitProfitCloseHour": -1, "SxitLossCloseHour": -1,
    "SxitProfitHoldATR": 0.0, "SxitHoldUntilHour": -1,
    "PprotMode": 0, "PprotSleeveMask": 0,
    "PprotArmPeakATR": 0.0, "PprotTPExtendATR": 0.0,
}


def cand(**kw):
    p = dict(BASE)
    p.update(kw)
    return p


CASES = [
    ("BASELINE", cand()),
    ("HX0039_RR175", cand(SxitMode=3, SxitSleeveMask=1, SxitRR=1.75)),
    ("EXT095", cand(SxitMode=1, PprotMode=14, PprotSleeveMask=2,
                    PprotArmPeakATR=0.5, PprotTPExtendATR=0.95)),
    ("EXT100", cand(SxitMode=1, PprotMode=14, PprotSleeveMask=2,
                    PprotArmPeakATR=0.5, PprotTPExtendATR=1.00)),
    ("EXT150", cand(SxitMode=1, PprotMode=14, PprotSleeveMask=2,
                    PprotArmPeakATR=0.5, PprotTPExtendATR=1.50)),
    ("TPATR260", cand(SxitMode=2, SxitSleeveMask=1, SxitTPATR=2.60)),
    ("RR175_EXT150", cand(SxitMode=4, SxitSleeveMask=1, SxitRR=1.75,
                          PprotMode=14, PprotSleeveMask=2,
                          PprotArmPeakATR=0.5, PprotTPExtendATR=1.50)),
]

_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    with _lock:
        print(line, flush=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def parse(run_id: str) -> dict | None:
    p = CONFIRM_DIR / run_id / "summary.csv"
    if not p.exists():
        return None
    v = {r[0]: r[1] for r in csv.reader(open(p, encoding="utf-8")) if len(r) >= 2}
    try:
        return {"net": float(v["純利益"]), "pf": float(v["プロフィットファクター"]),
                "dd_pct": float(v["最大相対DD%"]), "trades": int(float(v["総取引数"]))}
    except (KeyError, ValueError):
        return None


def run_one(name: str, exe: str, label: str, params: dict, window: str) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"cf_{window.lower()}_{label}_{stamp}_{uuid.uuid4().hex[:6]}"
    cfg = write_config(run_id, exe, window, params)
    cfg.write_text(cfg.read_text(encoding="utf-8").replace(
        f"report_dir: {ROOT / 'runs'}", f"report_dir: {CONFIRM_DIR}"), encoding="utf-8")

    log(f"RUN_START label={label} window={window} terminal={name}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        log(f"RUN_TIMEOUT label={label} window={window}")
        kill_terminal(exe)
        return {"label": label, "window": window, "status": "FAILED"}

    v = parse(run_id)
    src = COMMON / f"{run_id}_deals.csv"
    dst = ROOT / "run_deals" / f"{run_id}_deals.csv"
    if src.exists():
        try:
            src.replace(dst)
        except OSError:
            dst = src
    pb, sca = sleeve_net(dst)
    kill_terminal(exe)
    row = {"label": label, "window": window, "run_id": run_id,
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1),
           "pb_gold": round(pb), "sca_gold": round(sca), "deal_file": dst.name}
    if v:
        row.update(v)
    log(f"RUN_END label={label} window={window} net={row.get('net')} "
        f"pb={row['pb_gold']} sca={row['sca_gold']} elapsed={row['elapsed']}s")
    return row


def main() -> None:
    CONFIRM_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "run_deals").mkdir(parents=True, exist_ok=True)
    names = [n for n, _ in TERMINALS[:2]]
    sha = verify_ea_deployed(names)
    log(f"EA_VERIFIED sha256={sha}")

    jobs = [(lbl, p, w) for w in ("IS", "OOS") for lbl, p in CASES]
    work: "queue.Queue" = queue.Queue()
    for j in jobs:
        work.put(j)
    results: list[dict] = []

    def worker(name: str, exe: str) -> None:
        while True:
            try:
                label, params, window = work.get_nowait()
            except queue.Empty:
                return
            try:
                r = run_one(name, exe, label, params, window)
                with _lock:
                    results.append(r)
            finally:
                work.task_done()

    if suppress_sleep():
        log("SLEEP_SUPPRESSED")
    try:
        threads = []
        for name, exe in TERMINALS[:2]:
            t = threading.Thread(target=worker, args=(name, exe), daemon=True)
            t.start()
            threads.append(t)
            time.sleep(25)
        for t in threads:
            t.join()
    finally:
        release_sleep()

    fields = ["label", "window", "run_id", "status", "net", "pf", "dd_pct",
              "trades", "pb_gold", "sca_gold", "elapsed", "deal_file"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(results, key=lambda x: (x["window"], x["label"])):
            w.writerow({k: r.get(k, "") for k in fields})
    log(f"CONFIRM_END rows={len(results)} -> {OUT}")


if __name__ == "__main__":
    main()
