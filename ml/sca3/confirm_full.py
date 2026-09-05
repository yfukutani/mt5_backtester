"""残りの候補もフルブック（本番構成）で測る。

【なぜ必要か】confirm.py の結果で、GOLD 3枠だけの本では候補が軒並みOOSのDD優位ゲートを
落とすのに、暗号3枠を足したフルブックでは S3018 が両窓で明確に通った
（IS +0.130 / OOS +0.107、ISではDDが絶対値でも減少）。第3枠の純益寄与自体は両ブックで
完全に同一（IS +74,955 / OOS +23,335）なので、差はDDの出方だけ、つまり
**他の枠と谷がずれることによる分散効果**である。

本番はフルブックなので判断に使うべきはこちら。ただし S3018 一件だけでは
偶然と区別できないため、他の候補でも同じことが起きるかを確かめる。

基準は同一セッションで測り直す（スワップ率ドリフトを跨がせないため）。
"""
import csv
import json
from pathlib import Path

from confirm import (CONFIG_DIR, DEAL_DIR, FULL_BOOK, OUT, RUN_DIR, ROOT,
                     log, run)

TARGETS = ["S3017", "S3016", "S3001"]
OUT_FULL = ROOT / "confirm_full_results.csv"


def main():
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    props = {r["proposal_id"]: r for r in
             csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8"))}

    jobs = []
    for w in ("IS", "OOS"):
        jobs.append(("FULL_BASE2", FULL_BOOK, {"Sca3Enable": False}, w))
        for pid in TARGETS:
            jobs.append((f"FULL_{pid}", FULL_BOOK,
                         json.loads(props[pid]["parameter_json"]), w))

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        log(f"CONFIRM_FULL_START jobs={len(jobs)}")
        for label, book, params, window in jobs:
            results.append(run(label, book, params, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = ["label", "window", "status", "net", "pf", "dd_pct", "monthly_pct",
              "trades", "pb_net", "pb_n", "sca1_net", "sca1_n", "sca2_net", "sca2_n",
              "sca3_net", "sca3_n", "elapsed", "run_id"]
    with open(OUT_FULL, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})
    log(f"CONFIRM_FULL_END rows={len(results)} -> {OUT_FULL}")


if __name__ == "__main__":
    main()
