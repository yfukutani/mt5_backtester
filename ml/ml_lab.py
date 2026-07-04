# -*- coding: utf-8 -*-
"""
ml_lab.py — SCA_ML改善実験基盤（改善案⑳: P&L主指標・キャッシュ高速反復）

使い方:
  python ml_lab.py build gold      # CSV→特徴量30種+全ラベル群を dataset_<sym>.npz にキャッシュ
  python ml_lab.py run gold        # 実験バッチを実行しP&L評価表を出力

評価原則: AUCは参考値。主指標は test期間(2025.01-2026.06)の1ポジション制P&Lシミュ
（スプレッド実費・TP/SL/タイムアウト/BE移動対応）。
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
ATR_N = 14
LOOKBACK = 30
HORIZON = 10
TRAIN_END = pd.Timestamp("2024-01-01", tz="UTC")
VALID_END = pd.Timestamp("2025-01-01", tz="UTC")
POINT = {"gold": 0.01, "usdjpy": 0.001, "gbpjpy": 0.001}
MULT = {"gold": 150.0, "usdjpy": 1000.0, "gbpjpy": 1000.0}   # 0.01lot円換算係数

# 特徴量30種（先頭18は既存EA互換の順序を厳守）
FEATS = ["mom1","mom3","mom5","mom10","mom30","body0","upw0","dnw0","body1","body2",
         "rangepos","rangew","volratio","upshare10","upshare30","tvr","hsin","hcos",
         # 新規12種（⑪方向性 ⑫MA乖離 ⑬セッション ⑭ボラレジーム ⑮コスト効率）
         "mom60","mom120","hhstreak","llstreak","swingpos60","madev60","madev240",
         "atrratio","daypos","dowsin","dowcos","spratr"]
# ショート対称化ルール
SIGN_FLIP = ["mom1","mom3","mom5","mom10","mom30","body0","body1","body2",
             "mom60","mom120","madev60","madev240"]
SWAP = [("upw0","dnw0"), ("hhstreak","llstreak")]
INVERT01 = ["rangepos","upshare10","upshare30","swingpos60","daypos"]


def wilder_atr(h, l, c, n, period):
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr = np.full(n, np.nan)
    a = tr[:period].mean()
    atr[period] = a
    for i in range(period + 1, n):
        a = (a * (period - 1) + tr[i - 1]) / period
        atr[i] = a
    return atr


def streak(cond):
    """連続True本数（現在バー含む）"""
    s = pd.Series(cond.astype(np.int8))
    grp = (s != s.shift()).cumsum()
    return (s.groupby(grp).cumcount() + 1).to_numpy() * cond


def build(sym):
    df = pd.read_csv(BASE / f"m1_{sym}.csv")
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
    tv = df["tickvol"].to_numpy(float); sp = df["spread"].to_numpy(float)
    n = len(df)
    print(f"rows={n:,} range={df.dt.iloc[0]} .. {df.dt.iloc[-1]}")

    atr = wilder_atr(h, l, c, n, ATR_N)
    atr60 = wilder_atr(h, l, c, n, 60)

    f = {}
    ret1 = np.diff(c, prepend=c[0])
    for k in (1, 3, 5, 10, 30, 60, 120):
        r = np.full(n, np.nan); r[k:] = c[k:] - c[:-k]
        f[f"mom{k}"] = r / atr
    body = (c - o) / np.where(atr > 0, atr, np.nan)
    f["body0"] = body
    f["upw0"] = (h - np.maximum(c, o)) / np.where(atr > 0, atr, np.nan)
    f["dnw0"] = (np.minimum(c, o) - l) / np.where(atr > 0, atr, np.nan)
    f["body1"] = np.roll(body, 1); f["body2"] = np.roll(body, 2)
    hh30 = pd.Series(h).rolling(LOOKBACK).max().to_numpy()
    ll30 = pd.Series(l).rolling(LOOKBACK).min().to_numpy()
    rng = hh30 - ll30
    f["rangepos"] = np.where(rng > 0, (c - ll30) / rng, 0.5)
    f["rangew"] = rng / atr / LOOKBACK * 10
    rv10 = pd.Series(ret1).rolling(10).std().to_numpy()
    rv30 = pd.Series(ret1).rolling(30).std().to_numpy()
    f["volratio"] = np.where(rv30 > 0, rv10 / rv30, 1.0)
    up = (c > o).astype(float)
    f["upshare10"] = pd.Series(up).rolling(10).mean().to_numpy()
    f["upshare30"] = pd.Series(up).rolling(30).mean().to_numpy()
    tvm = pd.Series(tv).rolling(30).mean().to_numpy()
    f["tvr"] = np.where(tvm > 0, tv / tvm, 1.0)
    hr = df["dt"].dt.hour.to_numpy() + df["dt"].dt.minute.to_numpy() / 60.0
    f["hsin"] = np.sin(2 * np.pi * hr / 24); f["hcos"] = np.cos(2 * np.pi * hr / 24)
    # --- 新特徴量 ---
    f["hhstreak"] = np.minimum(streak(h > np.roll(h, 1)), 10) / 5.0
    f["llstreak"] = np.minimum(streak(l < np.roll(l, 1)), 10) / 5.0
    hh60 = pd.Series(h).rolling(60).max().to_numpy()
    ll60 = pd.Series(l).rolling(60).min().to_numpy()
    rng60 = hh60 - ll60
    f["swingpos60"] = np.where(rng60 > 0, (c - ll60) / rng60, 0.5)
    sma60 = pd.Series(c).rolling(60).mean().to_numpy()
    sma240 = pd.Series(c).rolling(240).mean().to_numpy()
    f["madev60"] = (c - sma60) / atr
    f["madev240"] = (c - sma240) / atr
    f["atrratio"] = np.where(atr60 > 0, atr / atr60, 1.0)
    dates = df["dt"].dt.date
    day_hh = df.groupby(dates)["high"].cummax().to_numpy()
    day_ll = df.groupby(dates)["low"].cummin().to_numpy()
    drng = day_hh - day_ll
    f["daypos"] = np.where(drng > 0, (c - day_ll) / drng, 0.5)
    dow = df["dt"].dt.dayofweek.to_numpy()
    f["dowsin"] = np.sin(2 * np.pi * dow / 5); f["dowcos"] = np.cos(2 * np.pi * dow / 5)
    f["spratr"] = np.where(atr > 0, sp * POINT[sym] / atr, np.nan)

    X = pd.DataFrame({k: f[k] for k in FEATS})

    # --- ラベル群 ---
    labels = {}
    def reach(tp_mult, horizon):
        tpl = c + tp_mult * atr
        fh = pd.Series(h[::-1]).rolling(horizon).max().to_numpy()[::-1]
        fh = np.roll(fh, -1)
        yl = (fh >= tpl).astype(np.float32)
        tps = c - tp_mult * atr
        fl = pd.Series(l[::-1]).rolling(horizon).min().to_numpy()[::-1]
        fl = np.roll(fl, -1)
        ys = (fl <= tps).astype(np.float32)
        return yl, ys
    labels["reach2_10_L"], labels["reach2_10_S"] = reach(2.0, 10)
    labels["reach15_10_L"], labels["reach15_10_S"] = reach(1.5, 10)
    labels["reach3_20_L"], labels["reach3_20_S"] = reach(3.0, 20)
    # リターン回帰ラベル
    ret10 = np.full(n, np.nan)
    ret10[:-10] = (c[10:] - c[:-10])
    labels["ret10"] = (ret10 / atr).astype(np.float32)
    # ファーストパッセージ TP2A vs SL4A（緩和版）
    K = 10
    tpl = c + 2.0 * atr; sll = c - 4.0 * atr
    tps = c - 2.0 * atr; sls = c + 4.0 * atr
    tp_hit = np.zeros((n, K), dtype=bool); sl_hit = np.zeros((n, K), dtype=bool)
    tp_hit_s = np.zeros((n, K), dtype=bool); sl_hit_s = np.zeros((n, K), dtype=bool)
    for k in range(1, K + 1):
        hh_k = np.roll(h, -k); ll_k = np.roll(l, -k)
        tp_hit[:, k-1] = hh_k >= tpl;  sl_hit[:, k-1] = ll_k <= sll
        tp_hit_s[:, k-1] = ll_k <= tps; sl_hit_s[:, k-1] = hh_k >= sls
    ftp = np.where(tp_hit.any(1), tp_hit.argmax(1), K+1)
    fsl = np.where(sl_hit.any(1), sl_hit.argmax(1), K+1)
    labels["fp24_L"] = (ftp < fsl).astype(np.float32)
    ftp = np.where(tp_hit_s.any(1), tp_hit_s.argmax(1), K+1)
    fsl = np.where(sl_hit_s.any(1), sl_hit_s.argmax(1), K+1)
    labels["fp24_S"] = (ftp < fsl).astype(np.float32)

    valid = (~X.isna().any(axis=1)).to_numpy() & ~np.isnan(atr) & (atr > 0) & ~np.isnan(labels["ret10"])
    valid[:240] = False           # 最長ルックバック(SMA240)
    valid[-25:] = False           # 最長ホライズン(20)+余裕
    dt64 = df["time"].to_numpy(np.int64)
    tr_m = (df["dt"] < TRAIN_END).to_numpy() & valid
    va_m = ((df["dt"] >= TRAIN_END) & (df["dt"] < VALID_END)).to_numpy() & valid
    te_m = (df["dt"] >= VALID_END).to_numpy() & valid
    hour = df["dt"].dt.hour.to_numpy(np.int8)

    np.savez_compressed(
        BASE / f"dataset_{sym}.npz",
        X=X.to_numpy(np.float32), o=o.astype(np.float32), h=h.astype(np.float32),
        l=l.astype(np.float32), c=c.astype(np.float32), sp=sp.astype(np.float32),
        atr=atr.astype(np.float32), time=dt64, hour=hour,
        valid=valid, tr_m=tr_m, va_m=va_m, te_m=te_m,
        **{k: v for k, v in labels.items()})
    print(f"train={tr_m.sum():,} valid={va_m.sum():,} test={te_m.sum():,}")
    print("saved ->", BASE / f"dataset_{sym}.npz")


# ==================== 実験ランナー ====================

def symmetrize(X):
    Xs = X.copy()
    idx = {k: i for i, k in enumerate(FEATS)}
    for k in SIGN_FLIP: Xs[:, idx[k]] = -Xs[:, idx[k]]
    for a, b in SWAP:
        tmp = Xs[:, idx[a]].copy(); Xs[:, idx[a]] = Xs[:, idx[b]]; Xs[:, idx[b]] = tmp
    for k in INVERT01: Xs[:, idx[k]] = 1.0 - Xs[:, idx[k]]
    return Xs


def fit_logistic(Z, y, w=None, l2=1.0, epochs=60, lr=0.3):
    """L2ロジスティック回帰（重み付き対応・GD）"""
    if w is None: w = np.ones(len(y), dtype=np.float32)
    w = w / w.mean()
    ww = np.zeros(Z.shape[1], dtype=np.float64)
    p0 = float(np.average(y, weights=w))
    b = np.log(max(p0, 1e-6) / max(1 - p0, 1e-6))
    m = len(y)
    for _ in range(epochs):
        p = 1 / (1 + np.exp(-(Z @ ww + b)))
        g = Z.T @ ((p - y) * w) / m + l2 * ww / m
        gb = float(np.mean((p - y) * w))
        ww -= lr * g; b -= lr * gb
    return ww, b


def fit_linreg(Z, y, l2=1.0, epochs=100, lr=0.1):
    """L2線形回帰（GD）"""
    ww = np.zeros(Z.shape[1], dtype=np.float64)
    b = float(y.mean())
    m = len(y)
    for _ in range(epochs):
        r = Z @ ww + b - y
        g = Z.T @ r / m + l2 * ww / m
        ww -= lr * g; b -= lr * float(r.mean())
    return ww, b


def auc(y, p):
    order = np.argsort(p)
    r = np.empty(len(p)); r[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    np_, nn = pos.sum(), (~pos).sum()
    if np_ == 0 or nn == 0: return float("nan")
    return (r[pos].sum() - np_ * (np_ + 1) / 2) / (np_ * nn)


# ⑦交差項: 方向(SIGN_FLIP)×レジーム(不変)の積のみ（対称化が符号反転で閉じる組合せ）
CROSS = [("mom5", "hsin"), ("mom5", "hcos"), ("mom5", "atrratio"), ("mom5", "tvr"),
         ("mom30", "hsin"), ("mom30", "atrratio"), ("madev60", "hsin"), ("madev60", "atrratio")]


class Lab:
    def __init__(self, sym, cross=False):
        d = np.load(BASE / f"dataset_{sym}.npz")
        self.sym = sym
        self.d = d
        self.X = d["X"].astype(np.float64)
        self.Xs = symmetrize(self.X)
        if cross:
            idx = {k: i for i, k in enumerate(FEATS)}
            xc = np.column_stack([self.X[:, idx[a]] * self.X[:, idx[b]] for a, b in CROSS])
            xcs = np.column_stack([self.Xs[:, idx[a]] * self.Xs[:, idx[b]] for a, b in CROSS])
            self.X = np.hstack([self.X, xc])
            self.Xs = np.hstack([self.Xs, xcs])
        self.n = len(self.X)
        self.valid = d["valid"]; self.tr_m = d["tr_m"]
        self.va_m = d["va_m"]; self.te_m = d["te_m"]
        self.h = d["h"].astype(float); self.l = d["l"].astype(float)
        self.c = d["c"].astype(float); self.sp = d["sp"].astype(float)
        self.atr = d["atr"].astype(float); self.hour = d["hour"]
        # 標準化統計（train・ロング/ショートスタック）
        st = np.vstack([self.X[self.tr_m], self.Xs[self.tr_m]])
        self.mu = st.mean(0); self.sd = st.std(0); self.sd[self.sd == 0] = 1.0
        self.results = []

    def z(self, X): return (X - self.mu) / self.sd

    def train_cls(self, ylabel_L, ylabel_S, sel_mask=None, w_mode=None,
                  feats=None, l2=1.0, epochs=60):
        """ロング+ショート統合の分類学習 → 全バーの(pL,pS)を返す"""
        yl = self.d[ylabel_L]; ys = self.d[ylabel_S]
        m = self.tr_m if sel_mask is None else (self.tr_m & sel_mask)
        Zl = self.z(self.X[m]); Zs = self.z(self.Xs[m])
        Z = np.vstack([Zl, Zs]); y = np.concatenate([yl[m], ys[m]])
        w = None
        if w_mode == "pnl":   # ⑤P&L加重: 当たれば+2A、外れ時は|ret10|+α を重みに
            r = np.abs(self.d["ret10"][m])
            wl = np.where(yl[m] == 1, 2.0, np.clip(r, 0.2, 4.0))
            ws = np.where(ys[m] == 1, 2.0, np.clip(r, 0.2, 4.0))
            w = np.concatenate([wl, ws])
        cols = slice(None) if feats is None else [FEATS.index(k) for k in feats]
        ww, b = fit_logistic(Z[:, cols], y, w=w, l2=l2, epochs=epochs)
        pL = np.full(self.n, np.nan); pS = np.full(self.n, np.nan)
        Zf = self.z(self.X)[:, cols]; Zfs = self.z(self.Xs)[:, cols]
        pL[self.valid] = 1 / (1 + np.exp(-(Zf[self.valid] @ ww + b)))
        pS[self.valid] = 1 / (1 + np.exp(-(Zfs[self.valid] @ ww + b)))
        # test AUC（ロング側・参考値）
        a = auc(yl[self.te_m], pL[self.te_m])
        return pL, pS, a

    def train_dir(self, reach_L="reach2_10_L", reach_S="reach2_10_S", feats=None,
                  l2=1.0, epochs=60):
        """①方向専用モデル: 排他到達バー（上のみvs下のみ）だけで学習"""
        yl = self.d[reach_L]; ys = self.d[reach_S]
        excl = (yl + ys == 1)                     # 排他到達のみ
        m = self.tr_m & excl
        y = yl[m]                                 # 1=上のみ到達
        cols = slice(None) if feats is None else [FEATS.index(k) for k in feats]
        Z = self.z(self.X[m])[:, cols]
        ww, b = fit_logistic(Z, y, l2=l2, epochs=epochs)
        pD = np.full(self.n, np.nan)
        Zf = self.z(self.X)[:, cols]
        pD[self.valid] = 1 / (1 + np.exp(-(Zf[self.valid] @ ww + b)))
        a = auc(yl[self.te_m & excl], pD[self.te_m & excl])
        return pD, a

    def train_ret(self, feats=None, l2=1.0, epochs=100):
        """②リターン回帰（ロング視点のみ・対称なので符号反転でショート）"""
        y = self.d["ret10"]
        m = self.tr_m
        cols = slice(None) if feats is None else [FEATS.index(k) for k in feats]
        Z = self.z(self.X[m])[:, cols]
        ww, b = fit_linreg(Z, np.clip(y[m], -6, 6), l2=l2, epochs=epochs)
        pr = np.full(self.n, np.nan)
        Zf = self.z(self.X)[:, cols]
        pr[self.valid] = Zf[self.valid] @ ww + b
        # 参考: test期間の予測とretの相関
        te = self.te_m
        corr = np.corrcoef(pr[te], y[te])[0, 1]
        return pr, corr

    def simulate(self, name, sigL, sigS, tp=2.0, sl=4.0, timeout=10,
                 be=None, spread_max_atr=None, hours=None, note="", period="test"):
        """1ポジション制・スプレッド実費のP&Lシミュ（period: valid/test）"""
        h, l, c, sp, atr = self.h, self.l, self.c, self.sp, self.atr
        pt = POINT[self.sym]; mult = MULT[self.sym]
        pm = self.va_m if period == "valid" else self.te_m
        sig = (sigL | sigS) & pm
        if spread_max_atr is not None:
            sig &= (sp * pt / np.where(atr > 0, atr, np.inf)) <= spread_max_atr
        if hours is not None:
            hm = np.isin(self.hour, hours)
            sig &= hm
        idx = np.where(sig)[0]
        trades = []; kinds = []
        busy = -1
        n = self.n
        for t in idx:
            if t <= busy: continue
            if t + 1 >= n: break
            lng = bool(sigL[t])
            A = atr[t]; e = c[t]; cost = sp[t] * pt
            end = min(t + timeout, n - 1)
            pnl = None; kind = "TO"; j = end
            be_armed = False
            if lng:
                tpp = e + tp * A; slp = e - sl * A
                for j in range(t + 1, end + 1):
                    if be is not None and not be_armed and h[j] >= e + be * A:
                        be_armed = True; slp = max(slp, e)
                    if l[j] <= slp:
                        pnl = (slp - e) - cost; kind = "SL" if slp < e else "BE"; break
                    if h[j] >= tpp:
                        pnl = tp * A - cost; kind = "TP"; break
                if pnl is None: pnl = (c[end] - e) - cost; j = end
            else:
                tpp = e - tp * A; slp = e + sl * A
                for j in range(t + 1, end + 1):
                    if be is not None and not be_armed and l[j] <= e - be * A:
                        be_armed = True; slp = min(slp, e)
                    if h[j] >= slp:
                        pnl = (e - slp) - cost; kind = "SL" if slp > e else "BE"; break
                    if l[j] <= tpp:
                        pnl = tp * A - cost; kind = "TP"; break
                if pnl is None: pnl = (e - c[end]) - cost; j = end
            trades.append(pnl); kinds.append(kind)
            busy = j
        if not trades:
            line = f"{name:<30} [{period[:2]}] 取引=0 {note}"
            print(line, flush=True)
            self.results.append((name, period, 0, 0, 0, 0, note)); return
        a = np.array(trades)
        wins = a > 0
        gp = a[wins].sum(); gl = -a[~wins].sum()
        pf = gp / gl if gl > 0 else float("inf")
        jpy = a.sum() * mult
        line = (f"{name:<30} [{period[:2]}] 取引={len(a):>5,} 勝率={wins.mean()*100:5.1f}% PF={pf:6.3f} "
                f"損益={jpy:>+10,.0f}円 [TP={kinds.count('TP')} SL={kinds.count('SL')} "
                f"BE={kinds.count('BE')} TO={kinds.count('TO')}] {note}")
        print(line, flush=True)
        self.results.append((name, period, len(a), pf, jpy, wins.mean(), note))


def run(sym):
    lab = Lab(sym)
    print(f"=== {sym} 改善実験バッチ1 (test 2025.01-2026.06 / 0.01lot) ===", flush=True)

    # E01 ベースライン再現（18特徴量・reachラベル）
    pL0, pS0, a0 = lab.train_cls("reach2_10_L", "reach2_10_S", feats=FEATS[:18])
    print(f"[E01] reach18 testAUC={a0:.4f}", flush=True)
    lab.simulate("E01 reach18 th.45", pL0 >= 0.45, (pS0 >= 0.45) & (pL0 < 0.45))

    # E02 拡張30特徴量（⑪-⑮）
    pL1, pS1, a1 = lab.train_cls("reach2_10_L", "reach2_10_S")
    print(f"[E02] reach30 testAUC={a1:.4f}", flush=True)
    lab.simulate("E02 reach30 th.45", pL1 >= 0.45, (pS1 >= 0.45) & (pL1 < 0.45))
    lab.simulate("E02 reach30 th.48", pL1 >= 0.48, (pS1 >= 0.48) & (pL1 < 0.48))

    # E03 ①方向専用モデル（排他到達）
    pD, aD = lab.train_dir()
    print(f"[E03] dir30 testAUC(排他到達バー)={aD:.4f}", flush=True)
    for th in (0.55, 0.60, 0.65):
        lab.simulate(f"E03 dir th{th:.2f}", pD >= th, pD <= 1 - th)

    # E04 ⑥2段: ボラゲート(reach)×方向
    volgate = np.nan_to_num(np.maximum(pL1, pS1)) >= 0.40
    lab.simulate("E04 dir.55+volgate.40", (pD >= 0.55) & volgate, (pD <= 0.45) & volgate)
    lab.simulate("E04 dir.60+volgate.40", (pD >= 0.60) & volgate, (pD <= 0.40) & volgate)

    # E05 ②リターン回帰
    pr, corr = lab.train_ret()
    print(f"[E05] ret回帰 test相関={corr:.4f}", flush=True)
    for k in (0.3, 0.5, 0.8):
        lab.simulate(f"E05 ret th{k}", pr >= k, pr <= -k)

    # E06 ⑯時間帯制限（ロンドン+NY序盤: サーバー9-17時）
    lab.simulate("E06 dir.55 h9-17", pD >= 0.55, pD <= 0.45, hours=list(range(9, 18)))

    # E07 ⑰スプレッドフィルター
    lab.simulate("E07 dir.55 spr<=.12", pD >= 0.55, pD <= 0.45, spread_max_atr=0.12)

    # E08 ⑱BE移動（+1Aで建値）
    lab.simulate("E08 dir.55 BE1.0", pD >= 0.55, pD <= 0.45, be=1.0)

    # E09 ④執行TP/TO再設計（方向モデルのまま）
    lab.simulate("E09 dir.55 tp1.5", pD >= 0.55, pD <= 0.45, tp=1.5)
    lab.simulate("E09 dir.55 tp3/to20", pD >= 0.55, pD <= 0.45, tp=3.0, timeout=20)

    # E10 ⑩確率差分（reach30）
    diff = np.nan_to_num(pL1 - pS1)
    for k in (0.05, 0.08):
        lab.simulate(f"E10 diff{k}", diff >= k, diff <= -k)

    # E12 ⑤P&L加重
    pLw, pSw, aw = lab.train_cls("reach2_10_L", "reach2_10_S", w_mode="pnl")
    print(f"[E12] reach30+P&L加重 testAUC={aw:.4f}", flush=True)
    lab.simulate("E12 pnl加重 th.45", pLw >= 0.45, (pSw >= 0.45) & (pLw < 0.45))

    # E13 ⑧収束改善（エポック3倍）
    pLe, pSe, ae = lab.train_cls("reach2_10_L", "reach2_10_S", epochs=180)
    print(f"[E13] reach30 ep180 testAUC={ae:.4f}", flush=True)
    lab.simulate("E13 ep180 th.45", pLe >= 0.45, (pSe >= 0.45) & (pLe < 0.45))

    # E15 ③FP緩和版（TP2A vs SL4A先着）
    pLf, pSf, af = lab.train_cls("fp24_L", "fp24_S")
    print(f"[E15] fp24 testAUC={af:.4f}", flush=True)
    for th in (0.42, 0.45, 0.48):
        lab.simulate(f"E15 fp24 th{th}", pLf >= th, (pSf >= th) & (pLf < th))

    # E18 ラベル別ホライズン: reach1.5A/10, reach3A/20
    pLa, pSa, aa = lab.train_cls("reach15_10_L", "reach15_10_S")
    print(f"[E18a] reach1.5/10 testAUC={aa:.4f}", flush=True)
    lab.simulate("E18a r15 th.55 tp1.5", pLa >= 0.55, (pSa >= 0.55) & (pLa < 0.55), tp=1.5)
    pLb, pSb, ab = lab.train_cls("reach3_20_L", "reach3_20_S")
    print(f"[E18b] reach3/20 testAUC={ab:.4f}", flush=True)
    lab.simulate("E18b r3 th.35 tp3/to20", pLb >= 0.35, (pSb >= 0.35) & (pLb < 0.35),
                 tp=3.0, timeout=20)

    print("\n=== バッチ1完了 ===", flush=True)


def run2(sym):
    """バッチ2: 勝ち筋（ret回帰・dir×時間帯）の組合せ+交差項。
    方法論: valid(2024)で構成選択→test(2025-26)は確認のみ。"""
    lab = Lab(sym)
    print(f"=== {sym} バッチ2 (valid選択→test確認 / 0.01lot) ===", flush=True)
    pr, corr = lab.train_ret()
    pD, aD = lab.train_dir()
    print(f"ret相関={corr:.4f} dirAUC={aD:.4f}", flush=True)

    H917 = list(range(9, 18))

    def both(name, sigL, sigS, **kw):
        lab.simulate(name, sigL, sigS, period="valid", **kw)
        lab.simulate(name, sigL, sigS, period="test", **kw)

    # B2-1 ②ret閾値プラトー
    for k in (0.25, 0.30, 0.35):
        both(f"B2-1 ret{k}", pr >= k, pr <= -k)
    # B2-2 ②×⑯
    for k in (0.25, 0.30):
        both(f"B2-2 ret{k}+h9-17", pr >= k, pr <= -k, hours=H917)
    # B2-3 ②×①合意
    both("B2-3 ret.3&dir.53", (pr >= 0.3) & (pD >= 0.53), (pr <= -0.3) & (pD <= 0.47))
    # B2-4 ②×⑰
    both("B2-4 ret.3+spr.12", pr >= 0.3, pr <= -0.3, spread_max_atr=0.12)
    # B2-5 ①×⑯閾値スイープ
    for th in (0.53, 0.55, 0.57):
        both(f"B2-5 dir{th}+h9-17", pD >= th, pD <= 1 - th, hours=H917)
    # B2-8 ②×⑯×④執行変形
    both("B2-8 ret.3+h917 tp1.5", pr >= 0.3, pr <= -0.3, hours=H917, tp=1.5)
    both("B2-8 ret.3+h917 tp3to20", pr >= 0.3, pr <= -0.3, hours=H917, tp=3.0, timeout=20)

    # B2-6/7 ⑦交差項
    labx = Lab(sym, cross=True)
    prx, corrx = labx.train_ret()
    pDx, aDx = labx.train_dir()
    print(f"[cross] ret相関={corrx:.4f} dirAUC={aDx:.4f}", flush=True)

    def bothx(name, sigL, sigS, **kw):
        labx.simulate(name, sigL, sigS, period="valid", **kw)
        labx.simulate(name, sigL, sigS, period="test", **kw)

    for k in (0.25, 0.30):
        bothx(f"B2-6 retX{k}", prx >= k, prx <= -k)
    bothx("B2-6 retX.3+h9-17", prx >= 0.3, prx <= -0.3, hours=H917)
    for th in (0.55, 0.57):
        bothx(f"B2-7 dirX{th}+h9-17", pDx >= th, pDx <= 1 - th, hours=H917)

    print("\n=== バッチ2完了 ===", flush=True)


def run3():
    """⑨3銘柄統合学習: trainを3銘柄結合して学習し、各銘柄のvalid/testで評価"""
    print("=== バッチ3: 3銘柄統合学習 ===", flush=True)
    labs = {s: Lab(s) for s in ("gold", "usdjpy", "gbpjpy")}

    # 統合ret回帰
    Z = np.vstack([lb.z(lb.X[lb.tr_m]) for lb in labs.values()])
    y = np.concatenate([np.clip(lb.d["ret10"][lb.tr_m], -6, 6) for lb in labs.values()])
    ww, b = fit_linreg(Z, y)
    # 統合dir（排他到達）
    Zd_parts = []; yd_parts = []
    for lb in labs.values():
        yl = lb.d["reach2_10_L"]; ys = lb.d["reach2_10_S"]
        m = lb.tr_m & ((yl + ys) == 1)
        Zd_parts.append(lb.z(lb.X[m])); yd_parts.append(yl[m])
    wd, bd = fit_logistic(np.vstack(Zd_parts), np.concatenate(yd_parts))

    H917 = list(range(9, 18))
    for s, lb in labs.items():
        Zf = lb.z(lb.X)
        pr = np.full(lb.n, np.nan); pr[lb.valid] = Zf[lb.valid] @ ww + b
        pD = np.full(lb.n, np.nan)
        pD[lb.valid] = 1 / (1 + np.exp(-(Zf[lb.valid] @ wd + bd)))
        for period in ("valid", "test"):
            lb.simulate(f"B3 {s} ret.3", pr >= 0.3, pr <= -0.3, period=period)
            lb.simulate(f"B3 {s} ret.3+h917", pr >= 0.3, pr <= -0.3, hours=H917, period=period)
            lb.simulate(f"B3 {s} dir.55+h917", pD >= 0.55, pD <= 0.45, hours=H917, period=period)
    print("\n=== バッチ3完了 ===", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    sym = sys.argv[2] if len(sys.argv) > 2 else "gold"
    if cmd == "build":
        build(sym)
    elif cmd == "run":
        run(sym)
    elif cmd == "run2":
        run2(sym)
    elif cmd == "run3":
        run3()
