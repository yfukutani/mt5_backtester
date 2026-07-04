# -*- coding: utf-8 -*-
"""
メタラベリング用データセット構築。
trades_{sym}.csv（EAの実取引: entry_time, dir, profit）に、エントリー時点で既知の
D1/H4/セッション特徴量を結合して meta_dataset.csv を出力する。
特徴量はすべて「エントリー時点より前に確定した情報」のみ（リーク防止:
D1系は前日までのバー、H4系は直前の確定バー、アジアレンジは当日9時に確定済み）。
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
SYMS = ["gold", "usdjpy", "gbpjpy"]


def wilder(tr, period):
    a = np.full(len(tr), np.nan)
    if len(tr) < period + 1:
        return a
    x = tr[1:period + 1].mean()
    a[period] = x
    for i in range(period + 1, len(tr)):
        x = (x * (period - 1) + tr[i]) / period
        a[i] = x
    return a


rows = []
for sym in SYMS:
    tf = BASE / f"trades_{sym}.csv"
    if not tf.exists():
        print(f"{sym}: trades無し・スキップ")
        continue
    tr = pd.read_csv(tf)
    m1 = pd.read_csv(BASE / f"m1_{sym}.csv")
    m1["dt"] = pd.to_datetime(m1["time"], unit="s", utc=True)
    m1 = m1.set_index("dt")

    # --- D1バー（サーバー日区切り＝アジアレンジ定義と同一） ---
    d1 = m1.resample("1D").agg(open=("open", "first"), high=("high", "max"),
                               low=("low", "min"), close=("close", "last")).dropna()
    trd = np.maximum(d1["high"] - d1["low"],
                     np.maximum((d1["high"] - d1["close"].shift()).abs(),
                                (d1["low"] - d1["close"].shift()).abs())).to_numpy()
    d1["atr14"] = wilder(trd, 14)
    d1["atr50"] = wilder(trd, 50)
    d1["sma200"] = d1["close"].rolling(200).mean()
    d1["ret"] = d1["close"].diff()
    d1["rng"] = d1["high"] - d1["low"]
    # 前日までの確定値として当日に付与（shift 1）
    d1f = pd.DataFrame({
        "d1_trend": (d1["close"] - d1["sma200"]) / d1["atr14"],
        "d1_atr_ratio": d1["atr14"] / d1["atr50"],
        "prev_ret": d1["ret"] / d1["atr14"],
        "prev_rng": d1["rng"] / d1["atr14"],
        "atr_d1": d1["atr14"],
    }).shift(1)
    d1f["date"] = d1f.index.date

    # --- H4バー ---
    h4 = m1.resample("4h").agg(high=("high", "max"), low=("low", "min"),
                               close=("close", "last")).dropna()
    trh = np.maximum(h4["high"] - h4["low"],
                     np.maximum((h4["high"] - h4["close"].shift()).abs(),
                                (h4["low"] - h4["close"].shift()).abs())).to_numpy()
    h4["atr14"] = wilder(trh, 14)
    h4["mom6"] = h4["close"].diff(6) / h4["atr14"]
    h4["madev20"] = (h4["close"] - h4["close"].rolling(20).mean()) / h4["atr14"]
    h4f = h4[["mom6", "madev20"]].copy()
    h4f.index = h4f.index + pd.Timedelta(hours=4)   # バー確定時刻（この時刻以降に参照可能）

    # --- 当日アジアレンジ（サーバー0-9時、9時に確定） ---
    asia = m1.between_time("00:00", "08:59")
    ar = asia.groupby(asia.index.date).agg(asia_hh=("high", "max"), asia_ll=("low", "min"))
    ar["asia_w"] = ar["asia_hh"] - ar["asia_ll"]
    ar.index.name = "date"

    # --- 取引に結合 ---
    tr["dt"] = pd.to_datetime(tr["entry_time"], unit="s", utc=True).astype("datetime64[us, UTC]")
    h4f.index = h4f.index.astype("datetime64[us, UTC]")
    tr = tr.sort_values("dt").reset_index(drop=True)
    tr["date"] = tr["dt"].dt.date
    tr = tr.merge(d1f, on="date", how="left")
    tr = tr.merge(ar.reset_index(), on="date", how="left")
    tr = pd.merge_asof(tr.sort_values("dt"), h4f.sort_index(),
                       left_on="dt", right_index=True, direction="backward")
    tr["asia_w_atr"] = tr["asia_w"] / tr["atr_d1"]
    tr["entry_hour"] = tr["dt"].dt.hour + tr["dt"].dt.minute / 60.0
    tr["dow"] = tr["dt"].dt.dayofweek
    tr["dir_"] = tr["dir"]
    # トレンドとブレイク方向の一致度（方向付き特徴量）
    tr["trend_align"] = tr["d1_trend"] * tr["dir"]
    tr["mom_align"] = tr["mom6"] * tr["dir"]
    tr["madev_align"] = tr["madev20"] * tr["dir"]
    tr["prevret_align"] = tr["prev_ret"] * tr["dir"]
    # 直近実績（同銘柄・過去トレードのみ＝リーク無し）
    win = (tr["profit"] > 0).astype(float)
    tr["prev_win"] = win.shift(1).fillna(0.5)
    tr["win3"] = win.shift(1).rolling(3).mean().fillna(0.5)
    tr["sym"] = sym
    tr["y"] = win
    rows.append(tr)

df = pd.concat(rows, ignore_index=True)
FEATS = ["trend_align", "mom_align", "madev_align", "prevret_align",
         "d1_atr_ratio", "prev_rng", "asia_w_atr", "entry_hour", "dow",
         "prev_win", "win3", "dir_"]
df = df.dropna(subset=FEATS)
out = BASE / "meta_dataset.csv"
df.to_csv(out, index=False)
per = df.groupby("sym").agg(n=("y", "size"), win=("y", "mean"), pnl=("profit", "sum"))
print(per)
print(f"total={len(df)}  期間 {df.dt.min()} .. {df.dt.max()}")
print("->", out)
