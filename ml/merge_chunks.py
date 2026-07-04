# -*- coding: utf-8 -*-
"""年次チャンクCSVを結合して m1_<sym>.csv を生成（重複除去・時系列順・隙間チェック）"""
import glob
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent

for sym in ("gold", "gbpjpy"):
    fs = sorted(glob.glob(str(BASE / "chunks" / f"m1_{sym}_y*.csv")))
    if not fs:
        print(f"{sym}: チャンクなし")
        continue
    df = pd.concat([pd.read_csv(f) for f in fs])
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    dt = pd.to_datetime(df["time"], unit="s", utc=True)
    # 3日超の隙間を検出（週末・年末年始以外のデータ欠落を可視化）
    gaps = dt.diff().dt.total_seconds() / 86400
    big = df.index[gaps > 3]
    out = BASE / f"m1_{sym}.csv"
    df.to_csv(out, index=False)
    print(f"{sym}: files={len(fs)} rows={len(df):,} range={dt.iloc[0]} .. {dt.iloc[-1]}")
    for i in big:
        print(f"  gap: {dt.iloc[i-1]} -> {dt.iloc[i]}  ({gaps.iloc[i]:.1f}日)")
