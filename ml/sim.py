# -*- coding: utf-8 -*-
"""
SCA_MLの理論P&Lシミュレーター（EAと同一ロジックをベクトル化せず忠実に再現）。
目的: EA実測(-55,866/PF0.55/465取引 @GOLD0.45)が「実装バグ」か「戦略の期待値」かの切り分け。
- train.pyと同一の特徴量・係数（raw変換）でp_long/p_shortを計算
- テスト期間(2025-01-01以降)のみ・1ポジション制・TP=2ATR/タイムアウト10本/災害SL=4ATR
- スプレッド実費: エントリーバーのspread列で往復コスト（point換算）を控除
使い方: python sim.py gold 0.45
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

SYM = sys.argv[1] if len(sys.argv) > 1 else "gold"
TH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.45
LOOKBACK, HORIZON, TP_ATR, ATR_N = 30, 10, 2.0, 14
SL_ATR = 4.0
TEST_START = pd.Timestamp("2025-01-01", tz="UTC")
TRAIN_END = pd.Timestamp("2024-01-01", tz="UTC")
VALID_END = pd.Timestamp("2025-01-01", tz="UTC")
L2, EPOCHS, LR = 1.0, 40, 0.3
POINT = {"gold": 0.01, "usdjpy": 0.001, "gbpjpy": 0.001}[SYM]

BASE = Path(__file__).parent
df = pd.read_csv(BASE / f"m1_{SYM}.csv")
df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
tv = df["tickvol"].to_numpy(float); sp = df["spread"].to_numpy(float)
n = len(df)

tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
atr = np.full(n, np.nan)
a = tr[:ATR_N].mean(); atr[ATR_N] = a
for i in range(ATR_N + 1, n):
    a = (a * (ATR_N - 1) + tr[i - 1]) / ATR_N
    atr[i] = a

feats = {}
ret1 = np.diff(c, prepend=c[0])
for k in (1, 3, 5, 10, 30):
    r = np.full(n, np.nan); r[k:] = (c[k:] - c[:-k]); feats[f"mom{k}"] = r / atr
body = (c - o) / np.where(atr > 0, atr, np.nan)
upw = (h - np.maximum(c, o)) / np.where(atr > 0, atr, np.nan)
dnw = (np.minimum(c, o) - l) / np.where(atr > 0, atr, np.nan)
feats["body0"] = body; feats["upw0"] = upw; feats["dnw0"] = dnw
feats["body1"] = np.roll(body, 1); feats["body2"] = np.roll(body, 2)
hh = pd.Series(h).rolling(LOOKBACK).max().to_numpy()
ll = pd.Series(l).rolling(LOOKBACK).min().to_numpy()
rng = hh - ll
feats["rangepos"] = np.where(rng > 0, (c - ll) / rng, 0.5)
feats["rangew"] = rng / atr / LOOKBACK * 10
rv10 = pd.Series(ret1).rolling(10).std().to_numpy()
rv30 = pd.Series(ret1).rolling(30).std().to_numpy()
feats["volratio"] = np.where(rv30 > 0, rv10 / rv30, 1.0)
up = (c > o).astype(float)
feats["upshare10"] = pd.Series(up).rolling(10).mean().to_numpy()
feats["upshare30"] = pd.Series(up).rolling(30).mean().to_numpy()
tvm = pd.Series(tv).rolling(30).mean().to_numpy()
feats["tvr"] = np.where(tvm > 0, tv / tvm, 1.0)
hr = df["dt"].dt.hour.to_numpy() + df["dt"].dt.minute.to_numpy() / 60.0
feats["hsin"] = np.sin(2 * np.pi * hr / 24); feats["hcos"] = np.cos(2 * np.pi * hr / 24)
X = pd.DataFrame(feats)
FEATS = list(X.columns)

# ラベル（学習の再現用）: ファーストパッセージ（train.pyと同一）
SL_ATR_LABEL = 2.0
tp_line = c + TP_ATR * atr
sl_line = c - SL_ATR_LABEL * atr
tp_line_s = c - TP_ATR * atr
sl_line_s = c + SL_ATR_LABEL * atr
K = HORIZON
tp_hit = np.zeros((n, K), dtype=bool); sl_hit = np.zeros((n, K), dtype=bool)
tp_hit_s = np.zeros((n, K), dtype=bool); sl_hit_s = np.zeros((n, K), dtype=bool)
for k in range(1, K + 1):
    hh_k = np.roll(h, -k); ll_k = np.roll(l, -k)
    tp_hit[:, k - 1] = hh_k >= tp_line
    sl_hit[:, k - 1] = ll_k <= sl_line
    tp_hit_s[:, k - 1] = ll_k <= tp_line_s
    sl_hit_s[:, k - 1] = hh_k >= sl_line_s
first_tp = np.where(tp_hit.any(1), tp_hit.argmax(1), K + 1)
first_sl = np.where(sl_hit.any(1), sl_hit.argmax(1), K + 1)
y_long = (first_tp < first_sl).astype(float)
first_tp_s = np.where(tp_hit_s.any(1), tp_hit_s.argmax(1), K + 1)
first_sl_s = np.where(sl_hit_s.any(1), sl_hit_s.argmax(1), K + 1)
y_short = (first_tp_s < first_sl_s).astype(float)

valid = (~X.isna().any(axis=1)).to_numpy() & ~np.isnan(atr) & (atr > 0)
valid[-HORIZON - 1:] = False
valid[:LOOKBACK + ATR_N] = False

SIGN_FLIP = ["mom1","mom3","mom5","mom10","mom30","body0","body1","body2"]
SWAP = [("upw0","dnw0")]
INVERT01 = ["rangepos","upshare10","upshare30"]

Xl = X[valid].copy(); yl = y_long[valid]
Xs = X[valid].copy(); ys = y_short[valid]
for f in SIGN_FLIP: Xs[f] = -Xs[f]
for a_, b_ in SWAP: Xs[a_], Xs[b_] = Xs[b_].copy(), Xs[a_].copy()
for f in INVERT01: Xs[f] = 1.0 - Xs[f]
dts = df["dt"][valid]
Xall = pd.concat([Xl, Xs]); yall = np.concatenate([yl, ys]); dtall = pd.concat([dts, dts])
tr_m = (dtall < TRAIN_END).to_numpy()

mu = Xall[tr_m].mean().to_numpy(); sd = Xall[tr_m].std().replace(0, 1).to_numpy()
Z = ((Xall - mu) / sd).to_numpy()

def train_logistic(Zt, yt):
    w = np.zeros(Zt.shape[1]); b = float(np.log(max(yt.mean(),1e-6)/(1-min(yt.mean(),1-1e-6))))
    m = len(yt)
    for ep in range(EPOCHS):
        p = 1/(1+np.exp(-(Zt@w + b)))
        g = Zt.T@(p-yt)/m + L2*w/m
        gb = float(np.mean(p-yt))
        w -= LR*g; b -= LR*gb
    return w, b

w, b = train_logistic(Z[tr_m], yall[tr_m])
w_raw = w / sd
b_raw = b - float((w * (mu / sd)).sum())

# raw係数で全バーのp_long/p_shortを計算（EAと同じ経路）
Xn = X.to_numpy()
Xn_s = X.copy()
for f in SIGN_FLIP: Xn_s[f] = -Xn_s[f]
for a_, b_ in SWAP: Xn_s[a_], Xn_s[b_] = Xn_s[b_].copy(), Xn_s[a_].copy()
for f in INVERT01: Xn_s[f] = 1.0 - Xn_s[f]
Xn_s = Xn_s.to_numpy()
pL = 1/(1+np.exp(-(Xn @ w_raw + b_raw)))
pS = 1/(1+np.exp(-(Xn_s @ w_raw + b_raw)))
pL[~valid] = np.nan; pS[~valid] = np.nan

test_m = (df["dt"] >= TEST_START).to_numpy()


def simulate(th, sl_atr, timeout=HORIZON, label="", counter_th=1.0):
    # counter_th<1.0: 方向純度フィルター＝反対方向の確率が低いバーのみ
    # （両方向とも高確率＝「ボラだけ高い」バーを除外する）
    sig_long = (pL >= th) & (pS <= counter_th)
    sig_short = (pS >= th) & (pL <= counter_th)
    sig = test_m & valid & (sig_long | sig_short)
    idx = np.where(sig)[0]
    trades = []
    kinds = []
    i_busy_until = -1
    for t in idx:
        if t <= i_busy_until: continue
        if t + 1 >= n: break
        is_long = bool(sig_long[t])
        A = atr[t]; entry_ref = c[t]
        spread_cost = sp[t] * POINT
        end = min(t + timeout, n - 1)
        pnl = None; kind = "TO"; j = end
        if is_long:
            tp = entry_ref + TP_ATR * A; slp = entry_ref - sl_atr * A
            for j in range(t + 1, end + 1):
                if l[j] <= slp: pnl = -sl_atr * A - spread_cost; kind = "SL"; break
                if h[j] >= tp: pnl = TP_ATR * A - spread_cost; kind = "TP"; break
            if pnl is None: pnl = (c[end] - entry_ref) - spread_cost; j = end
        else:
            tp = entry_ref - TP_ATR * A; slp = entry_ref + sl_atr * A
            for j in range(t + 1, end + 1):
                if h[j] >= slp: pnl = -sl_atr * A - spread_cost; kind = "SL"; break
                if l[j] <= tp: pnl = TP_ATR * A - spread_cost; kind = "TP"; break
            if pnl is None: pnl = (entry_ref - c[end]) - spread_cost; j = end
        trades.append((pnl, pnl / A))
        kinds.append(kind)
        i_busy_until = j
    if not trades:
        print(f"  th={th} SL={sl_atr}: 取引なし")
        return
    tr_arr = np.array([x[0] for x in trades])
    tra = np.array([x[1] for x in trades])
    wins = tr_arr > 0
    gp = tr_arr[wins].sum(); gl = -tr_arr[~wins].sum()
    mult = 150.0 if SYM == "gold" else 1000.0
    nTP = kinds.count("TP"); nSL = kinds.count("SL"); nTO = kinds.count("TO")
    to_avg = np.mean([x[1] for x, k in zip(trades, kinds) if k == "TO"]) if nTO else 0.0
    print(f"  {label}th={th} cth={counter_th} SL={sl_atr}: 取引={len(trades):,} 勝率={wins.mean()*100:.1f}% "
          f"PF={gp/gl if gl>0 else float('inf'):.3f} 平均={tra.mean():+.4f}A "
          f"損益={tr_arr.sum()*mult:+,.0f}円 [TP={nTP} SL={nSL} TO={nTO} TO平均={to_avg:+.3f}A]")


print(f"[{SYM}] テスト期間バー数={test_m.sum():,}")
print("-- ファーストパッセージ版（決済もSL=2.0Aの対称ブラケット） --")
for th_ in (0.48, 0.50, 0.52, 0.55):
    simulate(th_, SL_ATR_LABEL)
print("-- 方向純度フィルター併用 --")
for th_ in (0.48, 0.50):
    for cth_ in (0.42, 0.38):
        simulate(th_, SL_ATR_LABEL, counter_th=cth_)
