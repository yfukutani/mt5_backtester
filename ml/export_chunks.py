# -*- coding: utf-8 -*-
"""
GOLD+GBPJPY M1全期間回収スクリプト。
原理: テスターは参照銘柄のヒストリーを「テスト開始前年の1月1日」から事前ロードし、
      テスト開始前のデータもCopyRatesで取得できる（実証済み）。
      テスト期間を数日に絞った年次マイクロテスト×11本で全期間を回収する。
各runの完了直後にテスターFilesからchunks/へコピーする（次runの開始時にワイプされるため）。
"""
import shutil
import subprocess
import time
from pathlib import Path

ML = Path(__file__).parent          # 出力先（m1_*.csv / chunks/ はgit管理外）
REPO = Path(__file__).parent.parent
FILES = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D\Agent-127.0.0.1-3000\MQL5\Files")
CHUNKS = ML / "chunks"
CHUNKS.mkdir(exist_ok=True)

# (from, to, tag): テスト開始年の前年1月1日から参照銘柄がロードされる
RUNS = [
    ("2016.01.06", "2016.01.09", "y2015"),
    ("2017.01.06", "2017.01.09", "y2016"),
    ("2018.01.06", "2018.01.09", "y2017"),
    ("2019.01.06", "2019.01.09", "y2018"),
    ("2020.01.06", "2020.01.09", "y2019"),
    ("2021.01.06", "2021.01.09", "y2020"),
    ("2022.01.06", "2022.01.09", "y2021"),
    ("2023.01.06", "2023.01.09", "y2022"),
    ("2024.01.06", "2024.01.09", "y2023"),
    ("2025.01.06", "2025.01.09", "y2024"),
    ("2026.06.17", "2026.06.20", "y2025"),  # 2025.01.01以降の1.5年分
]

TPL = """mt5_path: "C:\\\\Users\\\\f\\\\AppData\\\\Roaming\\\\XMTrading MT5\\\\terminal64.exe"

expert:    "DataExport"
symbol:    "USDJPY"
period:    "H1"
from_date: "{frm}"
to_date:   "{to}"

deposit:  100000
currency: "JPY"
leverage: 25

model: "open_prices"

parameters:
  ExportSymbols:   "GOLD,GBPJPY"
  ExportTag:       "{tag}"
  ResultFileName:  "dataexport_chunk_result.csv"

report_dir:  "results"
report_name: "DataExport_Chunk"
"""


def kill_mt5():
    for exe in ("terminal64.exe", "metatester64.exe"):
        subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)


for frm, to, tag in RUNS:
    kill_mt5()
    time.sleep(2)
    (ML / "export_chunk.yaml").write_text(TPL.format(frm=frm, to=to, tag=tag), encoding="utf-8")
    try:
        subprocess.run(["cmd", "/c", str(REPO / "mt5bt.bat"), "run", str(ML / "export_chunk.yaml")],
                       capture_output=True, cwd=str(REPO), timeout=1500)
    except subprocess.TimeoutExpired:
        print(f"{tag}: mt5bt TIMEOUT", flush=True)
        kill_mt5()
        continue
    line = f"{tag}:"
    for sym in ("gold", "gbpjpy"):
        src = FILES / f"m1_{sym}_{tag}.csv"
        if src.exists():
            shutil.copy2(src, CHUNKS)
            line += f" {sym}={src.stat().st_size:,}B"
        else:
            line += f" {sym}=MISSING"
    print(line, flush=True)

kill_mt5()
print("ALL DONE", flush=True)
