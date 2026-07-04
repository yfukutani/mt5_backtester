# -*- coding: utf-8 -*-
"""
SCA_ML: M1×30本の特徴量から「次の10本以内にTPライン(k×ATR14)到達」の確率を学習する。
依存: pandas / numpy のみ（ロジスティック回帰は自前実装）。
出力: 検証指標(AUC/較正表) + MQL5用係数ヘッダ (ml_model_<sym>.mqh)
"""
import sys, math
import numpy as np
import pandas as pd
from pathlib import Path

SYM        = sys.argv[1] if len(sys.argv) > 1 else "usdjpy"
LOOKBACK   = 30      # 特徴量に使う過去バー数
HORIZON    = 10      # TP到達判定の先読みバー数
TP_ATR     = 2.0     # TPライン = close + TP_ATR × ATR14(M1)
ATR_N      = 14
TRAIN_END  = pd.Timestamp("2024-01-01", tz="UTC")   # 訓練 < これ
VALID_END  = pd.Timestamp("2025-01-01", tz="UTC")   # 検証 [TRAIN_END, これ) / テスト [これ, 終端)
L2         = 1.0     # L2正則化
EPOCHS     = 40
LR         = 0.3

BASE = Path(__file__).parent
df = pd.read_csv(BASE / f"m1_{SYM}.csv")
df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
print(f"rows={len(df):,}  range={df.dt.iloc[0]} .. {df.dt.iloc[-1]}")

o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
tv = df["tickvol"].to_numpy(float)
n = len(df)

# ATR14 (Wilder)
tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
atr = np.full(n, np.nan)
a = tr[:ATR_N].mean()
atr[ATR_N] = a
for i in range(ATR_N + 1, n):
    a = (a * (ATR_N - 1) + tr[i - 1]) / ATR_N
    atr[i] = a

# ---- 特徴量（バーtの確定情報のみ・全てATR正規化 or 無次元）----
def build_features():
    feats = {}
    ret1 = np.diff(c, prepend=c[0])
    for k in (1, 3, 5, 10, 30):
        r = np.full(n, np.nan)
        r[k:] = (c[k:] - c[:-k])
        feats[f"mom{k}"] = r / atr
    body = (c - o) / np.where(atr > 0, atr, np.nan)
    upw  = (h - np.maximum(c, o)) / np.where(atr > 0, atr, np.nan)
    dnw  = (np.minimum(c, o) - l) / np.where(atr > 0, atr, np.nan)
    feats["body0"] = body; feats["upw0"] = upw; feats["dnw0"] = dnw
    feats["body1"] = np.roll(body, 1); feats["body2"] = np.roll(body, 2)
    # 直近LOOKBACK本のレンジ内位置・幅
    hh = pd.Series(h).rolling(LOOKBACK).max().to_numpy()
    ll = pd.Series(l).rolling(LOOKBACK).min().to_numpy()
    rng = hh - ll
    feats["rangepos"] = np.where(rng > 0, (c - ll) / rng, 0.5)      # 0-1
    feats["rangew"]   = rng / atr / LOOKBACK * 10                    # 正規化幅
    # 実現ボラ比（直近10 vs 30）
    rv10 = pd.Series(ret1).rolling(10).std().to_numpy()
    rv30 = pd.Series(ret1).rolling(30).std().to_numpy()
    feats["volratio"] = np.where(rv30 > 0, rv10 / rv30, 1.0)
    # 陽線比率・連続方向
    up = (c > o).astype(float)
    feats["upshare10"] = pd.Series(up).rolling(10).mean().to_numpy()
    feats["upshare30"] = pd.Series(up).rolling(30).mean().to_numpy()
    # tickvol比
    tvm = pd.Series(tv).rolling(30).mean().to_numpy()
    feats["tvr"] = np.where(tvm > 0, tv / tvm, 1.0)
    # 時刻（周期エンコード, サーバー時）
    hr = df["dt"].dt.hour.to_numpy() + df["dt"].dt.minute.to_numpy() / 60.0
    feats["hsin"] = np.sin(2 * np.pi * hr / 24); feats["hcos"] = np.cos(2 * np.pi * hr / 24)
    return pd.DataFrame(feats)

X = build_features()
FEATS = list(X.columns)
print("features:", len(FEATS), FEATS)

# ---- ラベル: 次HORIZON本で high が close+TP_ATR*ATR に到達（ロング側）----
# 注: ファーストパッセージ（±2Aブラケット先着）ラベルも検証したが、線形モデルの
# 方向予測力では0.5超の較正シグナルがほぼ消滅し不成立（詳細は docs/sca_ml.md）。
# 本ラベルは「方向×ボラ」の混合予測であり、スタンドアロン取引では期待値マイナス。
# ブレイクアウト等の既存シグナルの確認フィルター用途を想定する。
tp_line = c + TP_ATR * atr
fut_hh = pd.Series(h[::-1]).rolling(HORIZON).max().to_numpy()[::-1]   # t+0..t+H-1 の max(high)
fut_hh = np.roll(fut_hh, -1)                                          # t+1..t+H
y_long = (fut_hh >= tp_line).astype(float)
# ショート側（対称）
tp_line_s = c - TP_ATR * atr
fut_ll = pd.Series(l[::-1]).rolling(HORIZON).min().to_numpy()[::-1]
fut_ll = np.roll(fut_ll, -1)
y_short = (fut_ll <= tp_line_s).astype(float)

valid = (~X.isna().any(axis=1)).to_numpy() & ~np.isnan(atr) & (atr > 0)
valid[-HORIZON - 1:] = False
valid[:LOOKBACK + ATR_N] = False

# 方向対称化: ショートサンプルは方向依存特徴量の符号を反転して1モデルに統合
SIGN_FLIP = ["mom1","mom3","mom5","mom10","mom30","body0","body1","body2"]
SWAP      = [("upw0","dnw0")]
INVERT01  = ["rangepos","upshare10","upshare30"]   # x -> 1-x

Xl = X[valid].copy(); yl = y_long[valid]
Xs = X[valid].copy(); ys = y_short[valid]
for f in SIGN_FLIP: Xs[f] = -Xs[f]
for a_, b_ in SWAP: Xs[a_], Xs[b_] = Xs[b_].copy(), Xs[a_].copy()
for f in INVERT01: Xs[f] = 1.0 - Xs[f]
dts = df["dt"][valid]
Xall = pd.concat([Xl, Xs]); yall = np.concatenate([yl, ys]); dtall = pd.concat([dts, dts])

tr_m = (dtall < TRAIN_END).to_numpy()
va_m = ((dtall >= TRAIN_END) & (dtall < VALID_END)).to_numpy()
te_m = (dtall >= VALID_END).to_numpy()
print(f"train={tr_m.sum():,} valid={va_m.sum():,} test={te_m.sum():,}  base_rate(train)={yall[tr_m].mean():.4f}")

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

def auc(y, p):
    order = np.argsort(p)
    r = np.empty(len(p)); r[order] = np.arange(1, len(p)+1)
    pos = y == 1
    return (r[pos].sum() - pos.sum()*(pos.sum()+1)/2) / (pos.sum() * (len(y)-pos.sum()))

w, b = train_logistic(Z[tr_m], yall[tr_m])
for name, m_ in (("train",tr_m),("valid",va_m),("test",te_m)):
    p = 1/(1+np.exp(-(Z[m_]@w + b)))
    print(f"{name}: AUC={auc(yall[m_], p):.4f}  base={yall[m_].mean():.4f}")

# 較正表（テスト期間）: 予測確率帯ごとの実測到達率
p_te = 1/(1+np.exp(-(Z[te_m]@w + b))); y_te = yall[te_m]
print("\n[テスト期間 較正表]  P帯 : 実測到達率 (件数)")
for lo in np.arange(0.1, 0.8, 0.1):
    m_ = (p_te >= lo) & (p_te < lo+0.1)
    if m_.sum() > 100:
        print(f"  {lo:.1f}-{lo+0.1:.1f}: {y_te[m_].mean():.4f} ({m_.sum():,})")

# MQL5ヘッダ出力（標準化込み係数へ変換: p=sigmoid(sum(wi'*xi)+b') ）
# 配列名はシンボルサフィックス付き（複数銘柄のヘッダを1つのEAに#includeできる形）
w_raw = w / sd
b_raw = b - float((w * (mu / sd)).sum())
S = SYM.upper()
hdr = ["// 自動生成: train.py による SCA_ML ロジスティック回帰係数",
       f"// symbol={SYM} ラベル=ファーストパッセージ TP={TP_ATR}xATR{ATR_N} SL={SL_ATR_LABEL}xATR"
       f" horizon={HORIZON} lookback={LOOKBACK} nfeat={len(FEATS)}",
       f"double ML_W_{S}[] = {{" + ", ".join(f"{v:.10g}" for v in w_raw) + "};",
       f"double ML_B_{S} = {b_raw:.10g};",
       "// features: " + ", ".join(FEATS)]
out = BASE / f"ml_model_{SYM}.mqh"
out.write_text("\n".join(hdr), encoding="utf-8")
print("\nheader ->", out)
