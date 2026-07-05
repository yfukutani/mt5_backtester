# -*- coding: utf-8 -*-
"""
DAY_EA フェーズ0: 時間帯×方向×日タイプの期待値マップ（S案 D18/D5/A10/A5/D2/D17/E20）。
m1データ（3銘柄・2015-2026）から日中構造の「食べ残し」を地図化する。
評価はグロス（コスト前）。EA化判定は往復コスト（GOLD52/UJ16/GJ25円/0.01lot）超のみ。
出力は円換算/0.01lot（GOLD:×150, JPY:×1000）。
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
MULT = {"gold": 150.0, "usdjpy": 1000.0, "gbpjpy": 1000.0}
COST = {"gold": 52.0, "usdjpy": 16.0, "gbpjpy": 25.0}
IS_START = pd.Timestamp("2021-06-21", tz="UTC")


def hourly_frame(sym):
    m1 = pd.read_csv(BASE / f"m1_{sym}.csv")
    m1["dt"] = pd.to_datetime(m1["time"], unit="s", utc=True)
    m1 = m1.set_index("dt")
    h = m1.resample("1h").agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last")).dropna()
    h["date"] = h.index.date
    h["hour"] = h.index.hour
    return h


for sym in ("gold", "usdjpy", "gbpjpy"):
    h = hourly_frame(sym)
    mult = MULT[sym]
    cost = COST[sym]
    # 日次ピボット: 各日の時間別closeを列に
    piv_c = h.pivot_table(index="date", columns="hour", values="close")
    piv_o = h.pivot_table(index="date", columns="hour", values="open")
    dates = pd.to_datetime(piv_c.index).tz_localize("UTC")
    is_m = dates >= IS_START

    def seg_ret(h1, h2):
        """h1時open→h2時close のリターン（価格差）"""
        if h1 not in piv_o.columns or (h2 - 1) not in piv_c.columns:
            return None
        return (piv_c[h2 - 1] - piv_o[h1])

    print("=" * 78)
    print(f"[{sym.upper()}] （円/0.01lot・往復コスト目安{cost:.0f}円）")

    # ---- D5: デイリーオープン方向の持続（0-h時の方向 → h-20時の継続）----
    print("D5/A10 方向持続マップ: 「0時→h時の方向」に h時から20時まで順張りした場合の平均")
    print("  h  | 条件日数 | 平均(円) | IS平均 | OOS平均")
    for h0 in (9, 11, 12, 13, 14, 16):
        early = seg_ret(0, h0)
        late = seg_ret(h0, 20)
        if early is None or late is None:
            continue
        m = early.notna() & late.notna() & (early != 0)
        sgn = np.sign(early[m])
        pnl = (late[m] * sgn) * mult
        ism = is_m[m.to_numpy()] if len(is_m) == len(m) else None
        print(f"  {h0:>2} | {m.sum():>6} | {pnl.mean():>+8.1f} | "
              f"{pnl[ism].mean():>+8.1f} | {pnl[~ism].mean():>+8.1f}"
              if ism is not None else "")

    # ---- A5: 欧州(9-15)→NY(16-20)リレー ----
    eu = seg_ret(9, 15)
    ny = seg_ret(16, 20)
    m = eu.notna() & ny.notna() & (eu != 0)
    sgn = np.sign(eu[m])
    follow = (ny[m] * sgn) * mult
    ism = is_m[m.to_numpy()]
    print(f"A5 欧州→NY持続: n={m.sum()} 平均={follow.mean():+.1f}円 "
          f"IS={follow[ism].mean():+.1f} OOS={follow[~ism].mean():+.1f}")

    # ---- D2: ロンドンクローズ反転（15-18の動き → 18-21の逆行）----
    ldn = seg_ret(15, 18)
    pm = seg_ret(18, 21)
    m = ldn.notna() & pm.notna() & (ldn != 0)
    sgn = np.sign(ldn[m])
    fade = (-pm[m] * sgn) * mult   # 逆張り側の損益
    ism = is_m[m.to_numpy()]
    print(f"D2 ロンドンクローズ反転(15-18→18-21逆張り): n={m.sum()} "
          f"平均={fade.mean():+.1f}円 IS={fade[ism].mean():+.1f} OOS={fade[~ism].mean():+.1f}")

    # ---- D1: NYセッション自体の時間帯期待値（16時→h時・オープン方向）----
    ny_early = seg_ret(16, 18)
    ny_late = seg_ret(18, 22)
    m = ny_early.notna() & ny_late.notna() & (ny_early != 0)
    sgn = np.sign(ny_early[m])
    cont = (ny_late[m] * sgn) * mult
    ism = is_m[m.to_numpy()]
    print(f"D1 NY内持続(16-18方向→18-22): n={m.sum()} 平均={cont.mean():+.1f}円 "
          f"IS={cont[ism].mean():+.1f} OOS={cont[~ism].mean():+.1f}")

    # ---- D17/E20: 日タイプ分類（アジア幅/直近ADR比）→A10の条件付き ----
    # アジアレンジ幅(1-9時)
    asia_h = h[(h["hour"] >= 1) & (h["hour"] < 9)]
    aw = asia_h.groupby("date").agg(hi=("high", "max"), lo=("low", "min"))
    aw["w"] = aw["hi"] - aw["lo"]
    day_rng = h.groupby("date").agg(hi=("high", "max"), lo=("low", "min"))
    adr = (day_rng["hi"] - day_rng["lo"]).rolling(14).mean().shift(1)
    ratio = (aw["w"] / adr).dropna()
    早 = seg_ret(0, 13)
    後 = seg_ret(13, 20)
    df3 = pd.DataFrame({"r": ratio, "e": 早, "l": 後}).dropna()
    df3 = df3[df3["e"] != 0]
    df3["pnl"] = np.sign(df3["e"]) * df3["l"] * mult
    q1, q2 = df3["r"].quantile([0.33, 0.67])
    print("D17 日タイプ別のA10(0-13方向→13-20追随)平均:")
    print(f"  静かな日(アジア/ADR<{q1:.2f}): {df3[df3['r'] <= q1]['pnl'].mean():+.1f}円 (n={len(df3[df3['r'] <= q1])})")
    print(f"  中間: {df3[(df3['r'] > q1) & (df3['r'] < q2)]['pnl'].mean():+.1f}円")
    print(f"  荒れた日(>{q2:.2f}): {df3[df3['r'] >= q2]['pnl'].mean():+.1f}円 (n={len(df3[df3['r'] >= q2])})")
