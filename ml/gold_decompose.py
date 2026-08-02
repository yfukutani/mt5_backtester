# -*- coding: utf-8 -*-
"""PB GOLDの入れ子窓を差分分解して、独立な前半区間の成績を復元する。

XM GOLDはテスターが「終端2026.06.20で終わる窓」しか実行できずIS/OOSが取れない。
しかしPB GOLDは UseRiskSizing=false の固定0.01ロット＝複利が無いため、
損益・取引数は時間区間に対して加法的。よって

    前半(2021.06-2024.01) = 全期間(2021.06-2026.06) − 後半(2024.01-2026.06)

として、後半と重ならない独立区間の成績を復元できる。
これで「BEの改善が2024-26の金パラボリック相場に依存していないか」を判定する。
"""
import csv
from pathlib import Path

SRC = Path(r"C:\Users\f\AppData\Local\Temp\claude\C--project\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad\s1s3\s1s3_results.csv")
rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8")) if r["sleeve"] == "PB_GOLD"]
full = {r["variant"]: r for r in rows if r["window"] == "IS"}    # 2021.06-2026.06
late = {r["variant"]: r for r in rows if r["window"] == "OOS"}   # 2024.01-2026.06

print("PB GOLD: 入れ子窓の差分分解（固定ロットのため損益は加法的）")
print("%-10s | %9s %4s | %9s %4s | %9s %4s | 前半の判定"
      % ("variant", "全期間", "n", "後半24-26", "n", "前半21-24", "n"))
print("-" * 96)
base_early = None
for v in ("BASE", "BE40", "BE50", "BE75", "BE100"):
    if v not in full or v not in late:
        continue
    fn, ln = float(full[v]["net"]), float(late[v]["net"])
    fc, lc = int(full[v]["n"]), int(late[v]["n"])
    en, ec = fn - ln, fc - lc
    if v == "BASE":
        base_early = en
        verdict = "基準"
    else:
        verdict = ("改善 %+.0f" % (en - base_early)) if en >= base_early else ("**悪化 %+.0f**" % (en - base_early))
    print("%-10s | %+9.0f %4d | %+9.0f %4d | %+9.0f %4d | %s"
          % (v, fn, fc, ln, lc, en, ec, verdict))

print()
print("解釈: 前半(2021.06-2024.01)は後半と重ならない独立区間。")
print("      ここでBEが悪化するなら、全期間の改善は後半（金パラボリック相場）依存であり、")
print("      他5枠と同じ『期間によって符号が反転する』パターンに該当する。")
