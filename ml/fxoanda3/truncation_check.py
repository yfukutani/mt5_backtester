# -*- coding: utf-8 -*-
"""**その run は窓を最後まで走ったのか**を機械的に判定する（2026-09-17）。

【なぜ要るのか】
OANDA はロスカット水準が 100% なので、cap を高くした構成は
**テストの途中で口座が飛び、テスターがその場でパスを終える。**
このとき `summary.csv` の純益も最大DDも「途中まで」の値になるが、
**行の見た目は完走した run と区別がつかない**（status は OK のまま）。

2026-09-17 の P001 はこれで危うく「純益 386,790円・最大DD 13.2%」と読むところだった。
実際は 24か月窓のうち **約4か月**しか走っていない。

【判定】
deal ログの最終時刻が窓の終端に届いているか。
`足りない日数 > 30日` なら **TRUNCATED**（失格）とする。
30日の猶予は「窓の最後に取引が無かっただけ」を誤判定しないため。

使い方: python ml/fxoanda3/truncation_check.py [results.csv ...]
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GRACE_DAYS = 30

WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09"),
    "W2": ("2017.11.09", "2019.11.09"),
    "W3": ("2018.11.09", "2020.11.09"),
    "OOS": ("2016.11.09", "2021.06.20"),
    "V1": ("2016.11.09", "2018.11.09"), "V2": ("2017.05.09", "2019.05.09"),
    "V3": ("2017.11.09", "2019.11.09"), "V4": ("2018.05.09", "2020.05.09"),
    "V5": ("2018.11.09", "2020.11.09"), "V6": ("2019.05.09", "2021.05.09"),
    "V7": ("2019.06.20", "2021.06.20"),
}


def end_ts(window):
    s = WINDOWS.get(window)
    if not s:
        return None
    return datetime.strptime(s[1], "%Y.%m.%d").replace(tzinfo=timezone.utc).timestamp()


def last_deal_ts(path):
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8", errors="replace")))
    except OSError:
        return None
    ts = [int(r["time"]) for r in rows if r.get("time", "").isdigit()]
    return max(ts) if ts else None


def main():
    paths = sys.argv[1:] or [str(ROOT / "results.csv")]
    print("| run | 窓 | 最終約定 | 窓の終端 | 不足日数 | 判定 | 純益 | 取引 |")
    print("|---|---|---|---|---:|---|---:|---:|")
    bad = 0
    for p in paths:
        if not Path(p).exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("status") != "OK":
                continue
            deals = r.get("deals", "")
            e = end_ts(r["window"])
            last = last_deal_ts(deals) if deals else None
            if e is None or last is None:
                verdict, short = "不明", ""
            else:
                short = (e - last) / 86400.0
                verdict = "**TRUNCATED**" if short > GRACE_DAYS else "完走"
                if short > GRACE_DAYS:
                    bad += 1
            ls = (datetime.fromtimestamp(last, timezone.utc).strftime("%Y-%m-%d")
                  if last else "-")
            es = (datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%d")
                  if e else "-")
            print(f"| {r['proposal_id']} | {r['window']} | {ls} | {es} | "
                  f"{short:.0f} | {verdict} | {float(r['net']):,.0f} | {r['trades']} |")
    print("")
    print(f"> **失格（途中で口座が飛んだ）: {bad}件。**")
    print("> TRUNCATED の行は純益も最大DDも読んではいけない。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
