# -*- coding: utf-8 -*-
"""NVT日次系列の生成（NvtCross_EA用）。
NVT = market-cap / 推定オンチェーン取引額(USD)の7日移動平均。
入力: chain_mcap.csv / chain_txvol_usd.csv（fetch_btc_alt_data2.pyで取得）
出力: nvt_btc.csv（time=UTC日エポック, nvt）→ MT5のCommon\\Filesへコピーして使う。
"""
import pandas as pd
from pathlib import Path

ML = Path(__file__).parent


def load(fname, col):
    f = pd.read_csv(ML / fname)
    f["dt"] = pd.to_datetime(f["time"], unit="s")
    return f.set_index("dt")[col]

mcap = load("chain_mcap.csv", "usd").resample("1D").last().ffill()
txvol = load("chain_txvol_usd.csv", "usd").resample("1D").mean().interpolate()
nvt = (mcap / txvol.rolling(7).mean()).dropna()
nvt = nvt[nvt.index >= "2013-01-01"]
out = pd.DataFrame({
    "time": (nvt.index.astype("int64") // 10**9),
    "nvt": nvt.round(4).values,
})
out.to_csv(ML / "nvt_btc.csv", index=False)
print(f"{len(out)}件 {nvt.index[0].date()}..{nvt.index[-1].date()} -> nvt_btc.csv")
