# -*- coding: utf-8 -*-
"""GOLD枠の曜日×時間帯の損益分布を実測dealから診断する。

目的: 「月曜(週明け)と金曜(週末)が不安定」という仮説を数字で確かめ、
不安定な"時間帯"を特定する。日単位の除外より粒度を細かくするため。

これは原因診断であって採否判定ではない。ここで見つけた時間帯は必ず
EAに実装して実バックテストで測り直す(後処理シミュレーションは無効)。
"""
import csv
import glob
import os
from collections import defaultdict
from datetime import datetime, timezone

COMMON = r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files"
PB_GOLD, SCA_GOLD = 20260640, 20261002
WD = ["月", "火", "水", "木", "金", "土", "日"]


def load(path):
    """EquityLogFileのdeal行を読む。entry=1(決済)のみ損益を持つ。"""
    out = []
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            try:
                magic = int(float(row.get("magic", "")))
                if magic not in (PB_GOLD, SCA_GOLD):
                    continue
                if int(float(row.get("entry", "0"))) != 1:
                    continue
                t = datetime.fromtimestamp(int(float(row["time"])), tz=timezone.utc)
                pj = row.get("profit_jpy") or row.get("profit")
                out.append((magic, t, float(pj)))
            except (TypeError, ValueError, KeyError):
                continue
    return out


def report(deals, label):
    print("\n############ %s (決済 %d件) ############" % (label, len(deals)))
    for magic, name in ((PB_GOLD, "PB GOLD"), (SCA_GOLD, "SCA GOLD")):
        sub = [(t, p) for m, t, p in deals if m == magic]
        if not sub:
            continue
        print("\n=== %s : %d件 ===" % (name, len(sub)))

        byday = defaultdict(list)
        for t, p in sub:
            byday[t.weekday()].append(p)
        print("--- 曜日別（決済時刻ベース・UTC） ---")
        print("曜日   件数      合計損益      平均     勝率   最大損失")
        for d in range(7):
            v = byday.get(d)
            if not v:
                continue
            wins = len([x for x in v if x > 0])
            print("%s   %5d  %+12.0f  %+8.0f  %5.1f%%  %+10.0f"
                  % (WD[d], len(v), sum(v), sum(v) / len(v),
                     100.0 * wins / len(v), min(v)))

        print("--- 月曜・金曜の時間帯別（UTC時） ---")
        for d in (0, 4):
            byh = defaultdict(list)
            for t, p in sub:
                if t.weekday() == d:
                    byh[t.hour].append(p)
            if not byh:
                continue
            print("[%s曜]  時 件数     合計       平均    勝率" % WD[d])
            for h in sorted(byh):
                v = byh[h]
                wins = len([x for x in v if x > 0])
                flag = "  ←損失集中" if sum(v) < 0 and len(v) >= 3 else ""
                print("       %2d時 %4d %+10.0f %+9.0f  %5.1f%%%s"
                      % (h, len(v), sum(v), sum(v) / len(v),
                         100.0 * wins / len(v), flag))


def main():
    cands = glob.glob(os.path.join(COMMON, "*_deals.csv"))
    # GOLD2枠のFULL/ISに相当する大きめのログを優先
    cands.sort(key=os.path.getsize, reverse=True)
    picked = []
    for p in cands[:40]:
        d = load(p)
        if len(d) >= 100:
            picked.append((p, d))
        if len(picked) >= 2:
            break
    if not picked:
        print("GOLD枠を含むdealログが見つかりません")
        return 1
    for p, d in picked:
        report(d, os.path.basename(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
