# -*- coding: utf-8 -*-
"""
メタラベリング学習・評価（ステップ2）。
「このシグナルを取るか見送るか」を学習し、valid(2024)で見送り閾値を選択、
test(2025-26)でベースライン（全取引）との勝率/PF/純益差を確認する。
モデル: LightGBM（浅い木・早期停止）と自前ロジスティック回帰の両方（頑健性比較）。
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
df = pd.read_csv(BASE / "meta_dataset.csv", parse_dates=["dt"])

FEATS = ["trend_align", "mom_align", "madev_align", "prevret_align",
         "d1_atr_ratio", "prev_rng", "asia_w_atr", "entry_hour", "dow",
         "prev_win", "win3", "dir_"]
# 銘柄ダミー
for s in ("gold", "usdjpy", "gbpjpy"):
    df[f"is_{s}"] = (df["sym"] == s).astype(float)
FEATS += ["is_gold", "is_usdjpy", "is_gbpjpy"]

import sys
TRAIN_END = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
VALID_END = sys.argv[2] if len(sys.argv) > 2 else "2025-01-01"
TEST_END = sys.argv[3] if len(sys.argv) > 3 else "2027-01-01"
tr_m = df["dt"] < TRAIN_END
va_m = (df["dt"] >= TRAIN_END) & (df["dt"] < VALID_END)
te_m = (df["dt"] >= VALID_END) & (df["dt"] < TEST_END)
print(f"split: train<{TRAIN_END} valid<{VALID_END} test<{TEST_END}")
print(f"train={tr_m.sum()} valid={va_m.sum()} test={te_m.sum()}  "
      f"base_win: tr={df.y[tr_m].mean():.3f} va={df.y[va_m].mean():.3f} te={df.y[te_m].mean():.3f}")

X = df[FEATS].to_numpy(float)
y = df["y"].to_numpy(float)
profit = df["profit"].to_numpy(float)


def auc(yy, pp):
    o = np.argsort(pp); r = np.empty(len(pp)); r[o] = np.arange(1, len(pp) + 1)
    pos = yy == 1
    npos, nneg = pos.sum(), (~pos).sum()
    if npos == 0 or nneg == 0: return float("nan")
    return (r[pos].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def stats_line(mask):
    k = profit[mask]
    if mask.sum() == 0 or (k < 0).sum() == 0:
        return f"n={mask.sum()}"
    return (f"n={mask.sum()} 勝率={y[mask].mean()*100:.1f}% "
            f"PF={k[k>0].sum()/-k[k<0].sum():.3f} 純益={k.sum():+,.0f}円")


def evaluate(name, p):
    """valid分位点で見送り閾値を決め、valid/test両方の成績をベースライン比較で出力"""
    print(f"\n--- {name}  AUC: va={auc(y[va_m], p[va_m]):.4f} te={auc(y[te_m], p[te_m]):.4f} ---")
    print(f"  base[va]: {stats_line(va_m.to_numpy())}")
    print(f"  base[te]: {stats_line(te_m.to_numpy())}")
    bw = y[te_m].mean()
    # test期間内の前半/後半分解（期間内一貫性の確認）
    te_dt = df["dt"][te_m]
    mid = te_dt.quantile(0.5)
    y25 = (df["dt"] < mid).to_numpy()
    for cut in (0.30, 0.40):
        th = np.quantile(p[va_m], cut)          # validで下位cut%を見送る閾値
        kv = va_m.to_numpy() & (p >= th)
        keep = te_m.to_numpy() & (p >= th)
        print(f"  cut{int(cut*100)}% [va]: {stats_line(kv)}")
        k = profit[keep]
        if keep.sum() < 20:
            print(f"  cut{int(cut*100)}% [te]: 残存{keep.sum()}件（少なすぎ）")
            continue
        kw = y[keep].mean(); kpf = k[k > 0].sum() / -k[k < 0].sum()
        skipped = 1 - keep.sum() / te_m.sum()
        print(f"  cut{int(cut*100)}% [te] (th={th:.3f}): 残存={keep.sum()} (見送り{skipped*100:.0f}%) "
              f"勝率={kw*100:.1f}% ({(kw-bw)*100:+.1f}pt) PF={kpf:.3f} 純益={k.sum():+,.0f}円")
        print(f"    te前半: base {stats_line(te_m.to_numpy() & y25)} → filt {stats_line(keep & y25)}")
        print(f"    te後半: base {stats_line(te_m.to_numpy() & ~y25)} → filt {stats_line(keep & ~y25)}")
        for s in ("gold", "usdjpy", "gbpjpy"):
            m = keep & (df["sym"] == s).to_numpy()
            b = te_m.to_numpy() & (df["sym"] == s).to_numpy()
            if m.sum() >= 5:
                print(f"    {s}: {b.sum()}→{m.sum()}件 勝率 {y[b].mean()*100:.0f}→{y[m].mean()*100:.0f}% "
                      f"純益 {profit[b].sum():+,.0f}→{profit[m].sum():+,.0f}円")


# --- ロジスティック回帰（自前・標準化） ---
mu = X[tr_m].mean(0); sd = X[tr_m].std(0); sd[sd == 0] = 1
Z = (X - mu) / sd
w = np.zeros(Z.shape[1]); b = float(np.log(y[tr_m].mean() / (1 - y[tr_m].mean())))
for _ in range(300):
    pr = 1 / (1 + np.exp(-(Z[tr_m] @ w + b)))
    g = Z[tr_m].T @ (pr - y[tr_m]) / tr_m.sum() + 1.0 * w / tr_m.sum()
    w -= 0.3 * g; b -= 0.3 * float(np.mean(pr - y[tr_m]))
p_lr = 1 / (1 + np.exp(-(Z @ w + b)))
evaluate("ロジスティック回帰", p_lr)
top = np.argsort(-np.abs(w))[:6]
print("  係数上位:", [(FEATS[i], round(w[i], 3)) for i in top])

# --- LightGBM（seed3種で安定性確認） ---
try:
    import lightgbm as lgb
    dtr = lgb.Dataset(X[tr_m], label=y[tr_m], feature_name=FEATS)
    dva = lgb.Dataset(X[va_m], label=y[va_m], reference=dtr)
    preds = []
    for seed in (42, 7, 2026):
        params = dict(objective="binary", metric="auc", learning_rate=0.03,
                      num_leaves=7, max_depth=3, min_data_in_leaf=40,
                      feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=1,
                      lambda_l2=5.0, verbose=-1, seed=seed)
        mdl = lgb.train(params, dtr, num_boost_round=600, valid_sets=[dva],
                        callbacks=[lgb.early_stopping(50, verbose=False)])
        p_gb = mdl.predict(X, num_iteration=mdl.best_iteration)
        preds.append(p_gb)
        evaluate(f"LightGBM seed{seed} (iter={mdl.best_iteration})", p_gb)
        if seed == 42:
            imp = sorted(zip(FEATS, mdl.feature_importance("gain")), key=lambda t: -t[1])[:6]
            print("  重要度上位:", [(k, round(v)) for k, v in imp])
    # seedアンサンブル（平均）
    evaluate("LightGBM 3seed平均", np.mean(preds, axis=0))
except ImportError:
    print("lightgbm無し")
