# -*- coding: utf-8 -*-
"""SCA_EA 3銘柄の本番構成でTradeLogFile付きバックテストを実行し、取引ログを回収"""
import shutil
import subprocess
import time
from pathlib import Path

ML = Path(__file__).parent
REPO = Path(r"C:\Users\f\source\repos\mt5_backtester")
FILES = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D\Agent-127.0.0.1-3000\MQL5\Files")

SYMS = ["gold", "usdjpy", "gbpjpy"]


def kill_mt5():
    for exe in ("terminal64.exe", "metatester64.exe"):
        subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)


for sym in SYMS:
    kill_mt5()
    time.sleep(2)
    # 本番configをベースにTradeLogFileを注入した一時configを生成
    base = (REPO / "configs" / f"sca_{sym}_m15.yaml").read_text(encoding="utf-8")
    y = base.replace("  ResultFileName:", f'  TradeLogFile:      "trades_{sym}.csv"\n  ResultFileName:')
    y = y.replace('report_name: "SCA_', 'report_name: "SCA_TL_')
    cfg = ML / f"sca_{sym}_tl.yaml"
    cfg.write_text(y, encoding="utf-8")
    try:
        subprocess.run(["cmd", "/c", str(REPO / "mt5bt.bat"), "run", str(cfg)],
                       capture_output=True, cwd=str(REPO), timeout=900)
    except subprocess.TimeoutExpired:
        print(f"{sym}: TIMEOUT", flush=True)
        kill_mt5()
        continue
    src = FILES / f"trades_{sym}.csv"
    if src.exists():
        shutil.copy2(src, ML / f"trades_{sym}.csv")
        nrows = sum(1 for _ in open(ML / f"trades_{sym}.csv")) - 1
        print(f"{sym}: {nrows} trades", flush=True)
    else:
        print(f"{sym}: trades CSV MISSING", flush=True)

kill_mt5()
print("COLLECT DONE", flush=True)
