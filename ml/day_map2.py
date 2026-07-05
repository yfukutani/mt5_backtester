# -*- coding: utf-8 -*-
"""DAY_EA フェーズ0第2弾: GOLD 1時基準修正 + シグナル強度3分位の条件付き期待値"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
MULT = {"gold": 150.0, "usdjpy": 1000.0, "gbpjpy": 1000.0}
COST = {"gold": 52.0, "usdjpy": 16.0, "gbpjpy": 25.0}
IS_START = pd.Timestamp("2021-06-21", tz="UTC")


def load(sym):
    m1 = pd.read_csv(BASE / f"m1_{sym}.csv")
    m1["dt"] = pd.to_datetime(m1["time"], unit="s", utc=True)
    m1 = m1.set_index("dt")
    h = m1.resample("1h").agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last")).dropna()
    h["date"] = h.index.date
    h["hour"] = h.index.hour
    piv_c = h.pivot_table(index="date", columns="hour", values="close")
    piv_o = h.pivot_table(index="date", columns="hour", values="open")
    day_rng = h.groupby("date").agg(hi=("high", "max"), lo=("low", "min"))
    adr = (day_rng["hi"] - day_rng["lo"]).rolling(14).mean().shift(1)
    return piv_o, piv_c, adr


def cond_table(sym, sig, fwd, label, flip=False):
    """シグナル強度3分位別の条件付き期待値（sig方向にfwdを取る。flip=Trueで逆張り）"""
    mult = MULT[sym]
    df = pd.DataFrame({"s": sig, "f": fwd}).dropna()
    df = df[df["s"] != 0]
    dates = pd.to_datetime(df.index).tz_localize("UTC")
    ism = dates >= IS_START
    dirn = -np.sign(df["s"]) if flip else np.sign(df["s"])
    df["pnl"] = dirn * df["f"] * mult
    df["mag"] = df["s"].abs()
    q1, q2 = df["mag"].quantile([0.33, 0.67])
    print(f"  {label}:")
    for name, m in (("弱", df["mag"] <= q1), ("中", (df["mag"] > q1) & (df["mag"] < q2)),
                    ("強", df["mag"] >= q2)):
        x = df[m]
        xi = x[ism[m.to_numpy()]]
        xo = x[~ism[m.to_numpy()]]
        print(f"    {name}(n={len(x)}): 全={x['pnl'].mean():+7.1f}円  "
              f"IS={xi['pnl'].mean():+7.1f}  OOS={xo['pnl'].mean():+7.1f}")


for sym in ("gold", "usdjpy", "gbpjpy"):
    po, pc, adr = load(sym)
    base_h = 1 if sym == "gold" else 0   # GOLDは1時開始
    print("=" * 78)
    print(f"[{sym.upper()}] 基準時={base_h}時（コスト目安{COST[sym]:.0f}円/0.01lot）")

    def seg(h1, h2):
        if h1 not in po.columns or (h2 - 1) not in pc.columns:
            return None
        return pc[h2 - 1] - po[h1]

    # A10: 午前(base-13)方向 → 午後(13-20)追随・強度別
    e = seg(base_h, 13); l = seg(13, 20)
    if e is not None and l is not None:
        cond_table(sym, e, l, "A10 午前→午後追随（強度=午前の動き幅）")
    # A5: 欧州(9-15)→NY(16-20)・強度別
    e = seg(9, 15); l = seg(16, 20)
    if e is not None and l is not None:
        cond_table(sym, e, l, "A5 欧州→NY持続")
    # D2: ロンドンクローズ反転(15-18→18-21)・強度別・逆張り
    e = seg(15, 18); l = seg(18, 21)
    if e is not None and l is not None:
        cond_table(sym, e, l, "D2 ロンドンクローズ反転（逆張り）", flip=True)
    # D5G: GOLD用 1-9時（アジア）方向→9-20時（＝SCAドリフトの逆張りが良かった知見の順張り側確認）
    e = seg(base_h, 9); l = seg(9, 20)
    if e is not None and l is not None:
        cond_table(sym, e, l, "D5 アジア方向→日中追随")
        cond_table(sym, e, l, "D5R アジア方向→日中逆張り", flip=True)
