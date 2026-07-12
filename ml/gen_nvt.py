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
# 注: pandas 2.xはto_datetime(unit="s")がdatetime64[s]を返すことがあり、
# astype("int64")//10**9 だと秒をさらに10^9で割って壊れる。Timedelta割りで単位非依存に。
epoch = (nvt.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
out = pd.DataFrame({
    "time": epoch,
    "nvt": nvt.round(4).values,
})
out.to_csv(ML / "nvt_btc.csv", index=False)
print(f"{len(out)}件 {nvt.index[0].date()}..{nvt.index[-1].date()} -> nvt_btc.csv")
