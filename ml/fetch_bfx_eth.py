# -*- coding: utf-8 -*-
"""Bitfinex ETHUSD マージン建玉（long/short）を取得する。

fetch_btc_alt_data3.py の fetch_bitfinex_side() をそのまま再利用（tETHUSD向けに未使用のまま
残されていた経路）。btc_backlog4.md で「ETHはデータ取得後」として保留されたBF(Bitfinexマージン)
ファミリーのETH移植（M002: 新データ_BfxRevのETH移植）向け。
レジューム対応済みなのでレート制限で中断しても再実行で続きから取得する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_btc_alt_data3 import fetch_bitfinex_side, save  # noqa

for side in ("long", "short"):
    print("Bitfinex ETHUSD マージン %s..." % side, flush=True)
    rows = fetch_bitfinex_side("tETHUSD", side, "bfx_eth_%s.csv" % side)
    save(rows, ["time", "size"], "bfx_eth_%s.csv" % side)
