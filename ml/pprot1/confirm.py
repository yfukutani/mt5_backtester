"""採用候補を基準と同一セッションで測り直して確定させる。

【なぜ必要か】MT5テスターは「現在のスワップ率を全履歴に一律適用」する近似のため、
測定日が違うと同じ取引でも損益が変わる。本ラウンドは基準を 2026-08-31 に、候補を
09-01〜02 に測っており、対照枠(PB GOLD)の実測で −6,128円のドリフトが確認された。
これはノイズ帯(1%)を超える大きさなので、確定にはスワップ率を揃えた再測定が要る。

基準と候補を **連続して** 測り、その中だけで比較する。
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
from run_pprot import (  # noqa: E402
    BASE_PARAMS, COMMON, MT5BT, REPO, ROOT, TERMINALS, WINDOWS,
    kill_terminal, release_sleep, suppress_sleep, write_config,
)

CONFIRM_DIR = ROOT / "confirm"
OUT = ROOT / "confirm_results.csv"
LOG = ROOT / "confirm.log"
CANDIDATES = ["PP0426", "PP0428", "PP0430", "PP0432", "PP0436"]
RUN_TIMEOUT = 1800

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


def sleeve_net(deal_path: Path) -> tuple[float, float]:
    """PB GOLD / SCA GOLD の枠別純益（円）。"""
    pb = sca = 0.0
    if not deal_path.exists():
        return (0.0, 0.0)
    for r in csv.DictReader(open(deal_path, encoding="utf-8")):
        m = int(r["magic"])
        if m == 20260640:
            pb += float(r["profit_jpy"])
        elif m == 20261002:
            sca += float(r["profit_jpy"])
    return (pb, sca)


def run_one(name: str, exe: str, label: str, params: dict, window: str) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"cf_{window.lower()}_{label}_{stamp}_{uuid.uuid4().hex[:6]}"
    # write_config は RUN_DIR に出すので、確認用は report_dir だけ差し替える
    cfg = write_config(run_id, exe, window, params)
    text = cfg.read_text(encoding="utf-8").replace(
        f"report_dir: {ROOT / 'runs'}", f"report_dir: {CONFIRM_DIR}")
    cfg.write_text(text, encoding="utf-8")

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
           "pb_gold": round(pb), "sca_gold": round(sca)}
    if v:
        row.update(v)
    log(f"RUN_END label={label} window={window} "
        f"net={row.get('net')} pb={row['pb_gold']} sca={row['sca_gold']} "
        f"elapsed={row['elapsed']}s")
    return row


def main() -> None:
    CONFIRM_DIR.mkdir(parents=True, exist_ok=True)
    props = {p["proposal_id"]: p for p in
             csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8"))}

    jobs: list[tuple[str, dict, str]] = []
    for window in ("IS", "OOS"):
        jobs.append(("BASELINE", {}, window))
        for pid in CANDIDATES:
            jobs.append((pid, json.loads(props[pid]["parameter_json"]), window))

    work: "queue.Queue[tuple[str, dict, str]]" = queue.Queue()
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
              "trades", "pb_gold", "sca_gold", "elapsed"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(results, key=lambda x: (x["window"], x["label"])):
            w.writerow({k: r.get(k, "") for k in fields})
    log(f"CONFIRM_END rows={len(results)} -> {OUT}")


if __name__ == "__main__":
    main()
