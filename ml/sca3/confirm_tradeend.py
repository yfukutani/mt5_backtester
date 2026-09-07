"""締切17h（S3018）がDD優位の台地なのかスパイクなのかを、フルブックで確定させる。

【なぜ必要か】confirm_full.py で、フルブックのIS側は4案すべてDDが絶対値でも減る
（構造的な分散効果）一方、OOS側は S3018（締切17h）だけが固定ロット比較を通り、
両隣の 15h と 20h は落ちた。掃引ではDD優位を測っていないので、締切軸のDD優位が
台地なのかスパイクなのかが未確定のまま残っている。

sca2b で「DD優位の指標は0近傍でノイズに埋もれる」（RRが1.3/1.5/2.4は通り1.9/2.1が
落ちる非単調）ことを記録しており、S3018 単独の +0.107 を額面通りに採ってはいけない。
締切 14/16/17/18/19h を刻んで測り、17h の周りが正なら台地、17h だけなら過学習として扱う。

基準は同一セッションで測り直す。
"""
import json
from pathlib import Path

from confirm import (CONFIG_DIR, DEAL_DIR, FULL_BOOK, RUN_DIR, ROOT, log, run)

# S3018 の設定。締切だけを振る。
S3018 = {
    "Sca3Enable": True, "Sca3RangeStart": 9, "Sca3RangeEnd": 11,
    "Sca3TradeEnd": 17, "Sca3ForceClose": 23,
    "Sca3MinRange": 0.40, "Sca3MaxRange": 1.00, "Sca3Buffer": 0.0,
    "Sca3RR": 1.7, "Sca3SkipFriday": True, "Sca3RevBoost": True,
    "Sca3BoostMult": 2.0, "Sca3Lot": 0.01,
}
TRADE_ENDS = [14, 16, 17, 18, 19]
OUT_TE = ROOT / "confirm_tradeend_results.csv"


def main():
    import csv
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    jobs = []
    for w in ("IS", "OOS"):
        jobs.append(("FULL_BASE3", FULL_BOOK, {"Sca3Enable": False}, w))
        for te in TRADE_ENDS:
            p = dict(S3018)
            p["Sca3TradeEnd"] = te
            jobs.append((f"TE{te}", FULL_BOOK, p, w))

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        log(f"CONFIRM_TE_START jobs={len(jobs)}")
        for label, book, params, window in jobs:
            results.append(run(label, book, params, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = ["label", "window", "status", "net", "pf", "dd_pct", "monthly_pct",
              "trades", "pb_net", "pb_n", "sca1_net", "sca1_n", "sca2_net", "sca2_n",
              "sca3_net", "sca3_n", "elapsed", "run_id"]
    with open(OUT_TE, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})
    log(f"CONFIRM_TE_END rows={len(results)} -> {OUT_TE}")


if __name__ == "__main__":
    main()
