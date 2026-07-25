# -*- coding: utf-8 -*-
"""test_cross_broker_ledger.py -- 合成mixlogによるcross_broker_ledger.py v2の検証

ケース:
  1. SCA_USDJPY: 正常な1:1ペア（XM -500 / OANDA -477 -> 差 -23・集計対象）
  2. PairTrade: 2レグ・OANDA決済が423秒遅延（F-3再現）-> TIMEDIFF除外・時刻差併記
  3. SCA_GBPJPY: S-4期間内のXM二重往復（0.02x2）-> 1本に補正して突合・S4フラグで集計除外・警告
  4. OANDA単独シグナル -> UNMATCHED警告
  5. XM VBOの未決済建玉 -> OPEN警告

実行: python ops/test_cross_broker_ledger.py [workdir]
"""
import csv
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cross_broker_ledger as led


def ep(s):
    return int((datetime.strptime(s, "%Y-%m-%d %H:%M:%S") - datetime(1970, 1, 1)).total_seconds())


def write_mixlog(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "type", "magic", "symbol", "f1", "f2", "f3", "f4", "f5", "f6", "note"])
        for t, magic, sym, side, lot, pnl, note in rows:
            w.writerow([t, "DEAL", magic, sym, "%.5f" % side, "%.5f" % lot,
                        "1.00000", "0.00000", "0.00000", "%.5f" % pnl, note])


def main():
    work = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="ledger_test_")
    if not os.path.isdir(work):
        os.makedirs(work)
    xm_csv = os.path.join(work, "mixlog_xm.csv")
    oa_csv = os.path.join(work, "mixlog_oanda.csv")
    out_csv = os.path.join(work, "ledger_out.csv")

    xm_rows = [
        # case1: clean SCA_USDJPY roundtrip
        (ep("2026-07-22 15:20:00"), 20261000, "USDJPY", 1, 0.02, 0.0, "IN"),
        (ep("2026-07-22 18:05:00"), 20261000, "USDJPY", -1, 0.02, -500.0, "OUT"),
        # case2: PairTrade 2 legs, XM exits at bar open
        (ep("2026-07-21 10:00:03"), 20260629, "EURUSD", -1, 0.01, 0.0, "IN"),
        (ep("2026-07-21 10:00:04"), 20260629, "GBPUSD", 1, 0.01, 0.0, "IN"),
        (ep("2026-07-22 18:00:00"), 20260629, "EURUSD", 1, 0.01, 800.0, "OUT"),
        (ep("2026-07-22 18:00:01"), 20260629, "GBPUSD", -1, 0.01, -320.0, "OUT"),
        # case3: SCA_GBPJPY duplicated by the S-4 double instance (2 x 0.02, 2s apart)
        (ep("2026-07-24 15:30:00"), 20261001, "GBPJPY", 1, 0.02, 0.0, "IN"),
        (ep("2026-07-24 15:30:02"), 20261001, "GBPJPY", 1, 0.02, 0.0, "IN"),
        (ep("2026-07-24 19:00:00"), 20261001, "GBPJPY", -1, 0.02, -600.0, "OUT"),
        (ep("2026-07-24 19:00:02"), 20261001, "GBPJPY", -1, 0.02, -580.0, "OUT"),
        # case5: VBO still open on XM
        (ep("2026-07-23 18:01:00"), 20260680, "USDJPY", 1, 0.01, 0.0, "IN"),
    ]
    oa_rows = [
        # case1 counterpart (5s later, cheaper exit)
        (ep("2026-07-22 15:20:05"), 20261000, "USDJPY", 1, 0.02, 0.0, "IN"),
        (ep("2026-07-22 18:05:03"), 20261000, "USDJPY", -1, 0.02, -477.0, "OUT"),
        # case2 counterpart: exit 423s late (F-3)
        (ep("2026-07-21 10:00:05"), 20260629, "EURUSD", -1, 0.01, 0.0, "IN"),
        (ep("2026-07-21 10:00:06"), 20260629, "GBPUSD", 1, 0.01, 0.0, "IN"),
        (ep("2026-07-22 18:07:03"), 20260629, "EURUSD", 1, 0.01, 790.0, "OUT"),
        (ep("2026-07-22 18:07:04"), 20260629, "GBPUSD", -1, 0.01, -305.0, "OUT"),
        # case3 counterpart: single roundtrip
        (ep("2026-07-24 15:30:01"), 20261001, "GBPJPY", 1, 0.02, 0.0, "IN"),
        (ep("2026-07-24 19:00:01"), 20261001, "GBPJPY", -1, 0.02, -590.0, "OUT"),
        # case4: OANDA-only signal (SCA_GOLD fired only on the CFD account)
        (ep("2026-07-21 09:45:00"), 20261002, "XAUUSD", 1, 0.01, 0.0, "IN"),
        (ep("2026-07-21 20:00:00"), 20261002, "XAUUSD", -1, 0.01, -1200.0, "OUT"),
    ]
    write_mixlog(xm_csv, xm_rows)
    write_mixlog(oa_csv, oa_rows)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = led.main(["--xm", xm_csv, "--oanda", oa_csv, "--out", out_csv,
                       "--s4-start", "2026-07-21 00:07", "--s4-end", ""])
    text = buf.getvalue()
    print(text)
    assert rc == 0

    with open(out_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    fails = []

    def check(cond, label):
        if cond:
            print("  PASS  " + label)
        else:
            fails.append(label)
            print("  FAIL  " + label)

    by_sleeve = {r["sleeve"]: r for r in rows}
    check(len(rows) == 3, "3 matched pairs in ledger (SCA_USDJPY, PAIR, SCA_GBPJPY)")
    check(by_sleeve["SCA_USDJPY"]["in_stats"] == "1", "clean pair included in stats")
    check("S4_PERIOD" in by_sleeve["SCA_USDJPY"]["flags"], "clean pair carries S4_PERIOD flag")
    check("segment S4_PERIOD N=1" in text, "period-split stats line printed")
    check(by_sleeve["SCA_USDJPY"]["diff_xm_minus_oanda"] == "-23", "clean pair diff -23 JPY")
    check(by_sleeve["PAIR"]["exit_diff_s"] == "-423", "PAIR exit-time diff -423s recorded")
    check("TIMEDIFF" in by_sleeve["PAIR"]["excluded"], "PAIR excluded by TIMEDIFF (F-3)")
    check("S4_DEDUP_2to1" in by_sleeve["SCA_GBPJPY"]["flags"], "XM duplicate collapsed 2->1")
    check("S4" in by_sleeve["SCA_GBPJPY"]["excluded"], "S4 pair excluded from stats by default")
    check("in cost stats N=1" in text, "cost stats N=1 (only the clean pair)")
    check("cumulative XM-OANDA diff = -23" in text, "cumulative diff -23 JPY")
    check("[S4-DEDUP]" in text, "S4 dedup warning printed")
    check("[UNMATCHED] OANDA SCA_GOLD" in text, "OANDA-only signal warned as unmatched")
    check("[OPEN] XM VBO_USDJPY" in text, "open XM position warned")
    check("coverage=" in text, "coverage line printed")

    print("")
    print("RESULT: %d checks, %d failed" % (15, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
