# -*- coding: utf-8 -*-
"""
DAY_EA G2/G3/G12: マルチシンボル相対構造の分析。
保有3銘柄（GOLD/USDJPY/GBPJPY）で計算可能な相対シグナル:
- G3: JPYクロス同時性（UJ・GJが0-9時に同方向 = JPY主導日）→ 9-20時の追随/逆張り
- G2近似: 相対モメンタム（0-9時の動きが強いペア vs 弱いペア）の9-20時継続
- JPY強弱: (UJ+GJ)/2 のJPY方向強度別
- GOLD×USD: USDJPY 0-9時方向とGOLD 9-20時の関係（ドル逆相関）
評価: 円/0.01lot・コスト UJ16/GJ25/GOLD52円・IS/OOS分解。
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
IS_START = pd.Timestamp("2021-06-21", tz="UTC")


def hourly(sym):
    m1 = pd.read_csv(BASE / f"m1_{sym}.csv")
    m1["dt"] = pd.to_datetime(m1["time"], unit="s", utc=True)
    m1 = m1.set_index("dt")
    h = m1.resample("1h").agg(open=("open", "first"), close=("close", "last")).dropna()
    h["date"] = h.index.date
    h["hour"] = h.index.hour
    po = h.pivot_table(index="date", columns="hour", values="open")
    pc = h.pivot_table(index="date", columns="hour", values="close")
    return po, pc


po_u, pc_u = hourly("usdjpy")
po_g, pc_g = hourly("gbpjpy")
po_x, pc_x = hourly("gold")

# 0-9時リターン（%）と9-20時リターン（価格）
def seg(po, pc, h1, h2):
    return pc[h2 - 1] - po[h1]

uj_am = seg(po_u, pc_u, 0, 9) / po_u[0] * 100     # %
gj_am = seg(po_g, pc_g, 0, 9) / po_g[0] * 100
uj_pm = seg(po_u, pc_u, 9, 20)                     # 価格
gj_pm = seg(po_g, pc_g, 9, 20)
x_pm = seg(po_x, pc_x, 9, 20)

df = pd.DataFrame({"ua": uj_am, "ga": gj_am, "up": uj_pm, "gp": gj_pm, "xp": x_pm}).dropna()
df = df[(df["ua"] != 0) & (df["ga"] != 0)]
dates = pd.to_datetime(df.index).tz_localize("UTC")
ism = np.asarray(dates >= IS_START)


def rep(label, pnl, mask=None):
    x = pnl if mask is None else pnl[mask]
    i = x[ism[mask] if mask is not None else ism]
    o = x[~(ism[mask] if mask is not None else ism)]
    print(f"  {label}: n={len(x)} 全={x.mean():+7.1f}円 IS={i.mean():+7.1f} OOS={o.mean():+7.1f}")


print("=" * 76)
print("G3 JPYクロス同時性（0-9時にUJ・GJ同方向＝JPY主導日）")
agree = np.sign(df["ua"]) == np.sign(df["ga"])
# 追随: 同方向の向きへ9-20時に両ペア順張り（合成: 各0.01lot）
pnl_follow = (np.sign(df["ua"]) * df["up"] * 1000 + np.sign(df["ga"]) * df["gp"] * 1000) / 2
rep("一致日・追随(2ペア平均)", pnl_follow, agree.to_numpy())
rep("不一致日・各自追随", pnl_follow, (~agree).to_numpy())
# 強度: JPY強弱指数 = (|ua|+|ga|)/2 の3分位（一致日のみ）
mag = (df["ua"].abs() + df["ga"].abs()) / 2
sub = df[agree]
msub = mag[agree]
q2 = msub.quantile(0.67)
strong = (msub >= q2).to_numpy()
pnl_sub = pnl_follow[agree.to_numpy()]
ism_sub = ism[agree.to_numpy()]
x = pnl_sub[strong]
print(f"  一致×強(上位33%): n={len(x)} 全={x.mean():+7.1f}円 "
      f"IS={x[ism_sub[strong]].mean():+7.1f} OOS={x[~ism_sub[strong]].mean():+7.1f}")

print("\nG2 相対モメンタム（0-9時の強い方ペアを9-20時追随 / 弱い方は？）")
u_stronger = df["ua"].abs() > df["ga"].abs()
pnl_strong_leg = np.where(u_stronger, np.sign(df["ua"]) * df["up"] * 1000,
                          np.sign(df["ga"]) * df["gp"] * 1000)
pnl_weak_leg = np.where(u_stronger, np.sign(df["ga"]) * df["gp"] * 1000,
                        np.sign(df["ua"]) * df["up"] * 1000)
rep("強い方ペア追随", pd.Series(pnl_strong_leg, index=df.index))
rep("弱い方ペア追随", pd.Series(pnl_weak_leg, index=df.index))

print("\nG1/G11 ドル→GOLD（USDJPYの0-9時方向 → GOLD 9-20時逆相関）")
pnl_x = -np.sign(df["ua"]) * df["xp"] * 150   # USD強→GOLD売り
rep("USD方向の逆へGOLD", pd.Series(pnl_x, index=df.index))
uq = df["ua"].abs().quantile(0.67)
m = (df["ua"].abs() >= uq).to_numpy()
rep("  USD動意強のみ", pd.Series(pnl_x, index=df.index), m)
