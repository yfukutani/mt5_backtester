# -*- coding: utf-8 -*-
"""再測定ランに ETH(magic 20260710) が実際に含まれたかを検証する。

EquityLogFileはテスターエージェントのMQL5\\Files配下に書かれるため、
そこから直接読んでmagicの出現を数える。
ファイル存在だけを見ていた従来ハーネスの見落とし（ETH無音欠落）への対策。
"""
import csv
import glob
import os
from collections import Counter

# EA側は FileOpen(..., FILE_COMMON) で書くため、出力先は共通Filesフォルダ
TESTER = r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files"
MAGICS = {20260710: "ETH", 20260720: "BTC_FUND", 20260724: "BFXREV"}

targets = ["cryptoRM_OFF_OOS_FIXED", "cryptoRM_D5_OOS_FIXED", "cryptoRM_D10_OOS_FIXED",
           "cryptoRM_OFF_IS", "cryptoRM_D5_IS", "cryptoRM_D10_IS"]

for t in targets:
    hits = glob.glob(os.path.join(TESTER, "**", "%s_r.csv" % t), recursive=True)
    hits += glob.glob(os.path.join(TESTER, "**", "%s_deals.csv" % t), recursive=True)
    if not hits:
        print("%-26s dealファイル未検出" % t)
        continue
    path = max(hits, key=os.path.getmtime)
    cnt = Counter()
    try:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
            for row in csv.reader(fh):
                for cell in row:
                    try:
                        v = int(float(cell))
                    except (TypeError, ValueError):
                        continue
                    if v in MAGICS:
                        cnt[MAGICS[v]] += 1
    except Exception as e:
        print("%-26s 読取失敗: %s" % (t, e))
        continue
    missing = [n for n in MAGICS.values() if cnt[n] == 0]
    print("%-26s %s %s"
          % (t, dict(cnt), ("← 欠落: " + ",".join(missing)) if missing else "← 全枠あり"))
