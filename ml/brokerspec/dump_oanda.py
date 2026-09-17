"""OANDA証券の端末で銘柄仕様をもう一度取る — 今度は `SYMBOL_VOLUME_LIMIT` も（2026-09-17）。

【なぜもう一度取るのか】
2026-09-15 の計測は `vol_max`（**1注文あたり**の上限＝10ロット）までしか取っていなかった。
`SYMBOL_VOLUME_LIMIT` は **同一銘柄・同一方向の建玉＋待機注文の合計**の上限で、**別物**である。

    vol_max = 10   なら 1注文は 10ロットまで
    vol_limit = ?  これが 10 なら「注文を分割して天井を超える」は**不可**
                   これが 0（無制限）や十分大きければ**分割で天井は消える**

**Claude 50案 #1 と Codex #1（分割発注）の成否を決めるのはこの1値だけ**なので、
案を書く前に測る。Codex は OANDA の公開表から「USDJPY/EURUSD は各2,000万通貨＝200ロット相当」
と読んだが、**公開表と端末の値が一致する保証は無い**（同じ日に「ini の Leverage=25 が
無視されて 1:100 で走っていた」を出している）。実機の値を採る。

【発注しない】
`SymbolSpecDump.mq5` は `SymbolInfoDouble` と `OrderCalcMargin` を読むだけで1件も発注しない。
口座には触れない。

使い方: python ml/brokerspec/dump_oanda.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mt5bt.config import BacktestConfig          # noqa: E402
from mt5bt.runner import MT5Runner               # noqa: E402

# OANDA本番端末（memory: project-mt5-oanda）
OANDA_EXE = r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe"
OANDA_HASH = "EE0304F13905552AE0B5EAEFB04866EB"
OANDA_DATA = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal") / OANDA_HASH
OANDA_MED = r"C:\Program Files\OANDA MetaTrader 5\metaeditor64.exe"

EA_SRC = REPO / "experts" / "SymbolSpecDump.mq5"
OUT = Path(__file__).resolve().parent / "symbol_specs_OANDA_vollimit.csv"


def deploy_and_compile() -> bool:
    experts = OANDA_DATA / "MQL5" / "Experts"
    if not experts.exists():
        print(f"OANDA端末のExpertsフォルダが無い: {experts}")
        return False
    dst = experts / EA_SRC.name
    shutil.copy2(EA_SRC, dst)
    log = experts / "c_specdump.log"
    subprocess.run([OANDA_MED, f"/compile:{dst}", f"/log:{log}"], timeout=180)
    time.sleep(2)
    if not log.exists():
        print("コンパイルログが出ていない")
        return False
    text = log.read_bytes().decode("utf-16-le", errors="replace")
    line = [x for x in text.splitlines() if x.startswith("Result:")]
    print("COMPILE", line[0] if line else "(Result行なし)")
    return bool(line) and "0 errors" in line[0]


def main() -> int:
    if not Path(OANDA_EXE).exists():
        print(f"OANDA端末が見つからない: {OANDA_EXE}")
        return 1
    if not deploy_and_compile():
        return 1

    cfg = BacktestConfig(
        mt5_path=OANDA_EXE,
        expert="SymbolSpecDump",
        symbol="USDJPY",
        period="H1",
        # 1本だけ回れば十分。仕様は時刻に依存しない。
        from_date="2021.01.04",
        to_date="2021.01.06",
        deposit=500000.0,
        currency="JPY",
        leverage=25,
        model="open_prices",
        parameters={"OutTag": "OANDA"},
    )
    report = Path(__file__).resolve().parent / "specdump_report"
    runner = MT5Runner(cfg, report)
    ok = runner.run(timeout=900)
    print("run ok:", ok, "applied_leverage:", runner.applied_leverage)

    # EA は FILE_COMMON に書く。実体は **Terminal\Common\Files** であって
    # `MetaQuotes\Common\Files` ではない（2026-09-17 にここで一度空振りした）。
    for common in (Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files"),
                   Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Common\Files")):
        for name in ("symbol_specs_OANDA.csv", "symbol_specs.csv"):
            src = common / name
            if src.exists():
                shutil.copy2(src, OUT)
                print(f"-> {OUT}")
                print(OUT.read_text(encoding="utf-8", errors="replace"))
                return 0
    print("出力が見つからない。Terminal\\Common\\Files を確認すること")
    return 1


if __name__ == "__main__":
    sys.exit(main())
