"""V053：V052の修正版——**尺度不変なボラ比**で条件づける（事前登録済み）。

【V052の欠陥】
V052は基準ボラを**IS窓からのみ推定**（38.64 USD）して `vol_t / 38.64` を使った。
ところがOOS窓の金のボラはそれよりはるかに低い（V051：A期 8.69 / B期 19.06）ため、
OOSでは比がほぼ常に下限クリップ0.5に張り付き、**条件付けとして機能せず、
単に「k0を半分にした」のとほぼ同じ**になった（実現k平均 0.50 → 0.32）。

**この欠陥はOOSを見る前に気づけたはずだったが、見落とした。**
V052は却下として確定させ、修正版を**別の検証として事前登録**する。

【事前登録した設計（結果を見る前に固定する）】
固定基準をやめ、**同じ系列から取った2つの移動窓の比**にする。
窓ごとのボラ水準に依存しないため、V052の欠陥は構造的に起こらない。

    vol_short = 直近40件のGOLD値幅のRMS      ← t より前の情報のみ
    vol_long  = 直近400件のGOLD値幅のRMS     ← t より前の情報のみ
    ratio_t   = clip((vol_short / vol_long)^p, 0.5, 2.0)
    k_t       = k0 × ratio_t

- p ∈ {0.0（条件付けなし・基準）, 0.5, 1.0} を**すべて報告する**
- k0 は IS窓で選ぶ。OOSを見て選び直さない
- 継続基準：OOS到達率が p=0.0 比 **+2pt以上**、かつ破綻確率が悪化しないこと
- 最小ロット制約（V047）を織り込む
- **vol_long が貯まるまで（400件未満）は ratio=1.0 とする**

【限界】
- ボラはGOLD枠の約定からのみ計算（FX枠のボラは見ていない）
- 年ブロック再標本化（V045）は入れていない（L=20で測定）
- 窓長（40/400）とクリップ範囲(0.5, 2.0)は設計上の選択である
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl
from sleeve_time_trend import SYMBOL_OF

MIN_LOT = 0.01
STEP = 0.01
CONTRACT = 100.0
N_PATHS = 20000
SEEDS = (101, 202, 303)
K_GRID = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
P_GRID = [0.0, 0.5, 1.0]
CLIP = (0.5, 2.0)
W_SHORT, W_LONG = 40, 400
RUIN = 0.10
LONG_MONTHS = 240.0
L = 20
MONTHS = cc.MONTHS


def load(window):
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        raw = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            if m == 0:
                continue
            raw.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                        float(r["profit"]), float(r["volume"]),
                        float(r.get("usdjpy") or 0.0), m))
        raw.sort()
        opened = {}
        for t, entry, pid, profit, vol, uj, m in raw:
            if entry == 0:
                opened[pid] = (vol, uj, m)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[0] <= 0:
                    continue
                g = 1.0 if SYMBOL_OF.get(o[2]) == "GOLD" else 0.0
                move = (abs(profit) / o[1] / (o[0] * CONTRACT)
                        if (g and o[1] > 0) else 0.0)
                rec.append((t, profit, o[0], move, g))
    rec.sort()
    return (np.array([x[1] for x in rec], dtype=float),
            np.array([x[2] for x in rec], dtype=float),
            np.array([x[3] for x in rec], dtype=float),
            np.array([x[4] for x in rec], dtype=float))


def gen(pr, vo, mv, gd, H, n_paths, seed):
    rng = np.random.default_rng(seed)
    n = len(pr)
    nb = H // L + 2
    starts = rng.integers(0, n, size=(n_paths, nb))
    off = np.arange(L)
    idx = (starts[:, :, None] + off[None, None, :]) % n
    idx = idx.reshape(n_paths, -1)[:, :H]
    return pr[idx], vo[idx], mv[idx], gd[idx]


def run(pp, vv, mm, gg, k0, p):
    """2つの移動窓の比で条件づける。倍率は t より前の情報だけから決める。"""
    n_paths, H = pp.shape
    eq = np.full(n_paths, cc.CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    hs = np.zeros((n_paths, W_SHORT))
    hl = np.zeros((n_paths, W_LONG))
    ps = np.zeros(n_paths, dtype=np.int64)
    pl = np.zeros(n_paths, dtype=np.int64)
    ss = np.zeros(n_paths)      # 短期窓の二乗和
    sl = np.zeros(n_paths)      # 長期窓の二乗和
    ns = np.zeros(n_paths)
    nl = np.zeros(n_paths)
    rows = np.arange(n_paths)
    k_sum = k_cnt = 0.0
    r_sum = r_cnt = 0.0
    for step in range(H):
        if not alive.any():
            break
        x = eq / cc.CAPITAL
        if p == 0.0:
            kt = np.full(n_paths, k0)
        else:
            ready = nl >= W_LONG
            vs = np.sqrt(np.where(ns > 0, ss / np.maximum(ns, 1), 1.0))
            vl = np.sqrt(np.where(nl > 0, sl / np.maximum(nl, 1), 1.0))
            ratio = np.where(ready & (vl > 0),
                             np.clip((vs / np.maximum(vl, 1e-9)) ** p,
                                     CLIP[0], CLIP[1]), 1.0)
            kt = k0 * ratio
            if step % 50 == 0:
                sub = ratio[alive]
                if sub.size:
                    r_sum += float(sub.sum()); r_cnt += sub.size
        if step % 50 == 0:
            sub = kt[alive]
            if sub.size:
                k_sum += float(sub.sum()); k_cnt += sub.size
        v = vv[:, step]
        actual = np.maximum(MIN_LOT, np.floor(v * kt * x / STEP + 1e-9) * STEP)
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= cc.CAPITAL * 2.0)
        ruin = alive & (eq <= cc.CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
        # --- ボラ履歴を更新（この取引の後＝次stepから使う） ---
        isg = gg[:, step] > 0
        if isg.any():
            newv = mm[:, step]
            i_s = (ps % W_SHORT).astype(np.int64)
            old_s = hs[rows, i_s]
            ss = np.where(isg, ss - old_s ** 2 + newv ** 2, ss)
            hs[rows, i_s] = np.where(isg, newv, old_s)
            ns = np.where(isg, np.minimum(ns + 1, W_SHORT), ns)
            ps = np.where(isg, ps + 1, ps)
            i_l = (pl % W_LONG).astype(np.int64)
            old_l = hl[rows, i_l]
            sl = np.where(isg, sl - old_l ** 2 + newv ** 2, sl)
            hl[rows, i_l] = np.where(isg, newv, old_l)
            nl = np.where(isg, np.minimum(nl + 1, W_LONG), nl)
            pl = np.where(isg, pl + 1, pl)
    return (state, stop, (k_sum / k_cnt if k_cnt else k0),
            (r_sum / r_cnt if r_cnt else 1.0))


def main():
    pr_i, vo_i, mv_i, gd_i = load("IS")
    pr_o, vo_o, mv_o, gd_o = load("OOS")
    print("=" * 120)
    print("V053：尺度不変なボラ比で条件づける（V052の修正版・事前登録済み）")
    print("=" * 120)
    print(f"k = k0 × clip((直近{W_SHORT}件のRMS / 直近{W_LONG}件のRMS)^p, "
          f"{CLIP[0]}, {CLIP[1]})")
    print("窓ごとのボラ水準に依存しない。倍率は t より前の情報だけから決める。")
    print("最小ロット制約(V047)を織り込み済み。**すべてのpを報告する。**\n")

    rate_i = len(pr_i) / MONTHS["IS"]
    rate_o = len(pr_o) / MONTHS["OOS"]
    H_i = int(round(rate_i * LONG_MONTHS))
    H_o = int(round(rate_o * LONG_MONTHS))

    res = {}
    for p in P_GRID:
        best, bp, isr = None, -1.0, {}
        for k0 in K_GRID:
            hh, rr = [], []
            for sd in SEEDS:
                pp, vv, mm, gg = gen(pr_i, vo_i, mv_i, gd_i, H_i, N_PATHS,
                                     seed=190000 + sd)
                st, stp, km, rm = run(pp, vv, mm, gg, k0, p)
                hh.append(float((st == 1).mean())); rr.append(float((st == 2).mean()))
            mh = float(np.mean(hh))
            isr[k0] = (mh, float(np.mean(rr)))
            if mh > bp:
                best, bp = k0, mh
        hh, rr, steps, kms, rms = [], [], [], [], []
        for sd in SEEDS:
            pp, vv, mm, gg = gen(pr_o, vo_o, mv_o, gd_o, H_o, N_PATHS,
                                 seed=200000 + sd)
            st, stp, km, rm = run(pp, vv, mm, gg, best, p)
            hh.append(float((st == 1).mean())); rr.append(float((st == 2).mean()))
            steps.append(stp[st == 1]); kms.append(km); rms.append(rm)
        s = np.concatenate(steps)
        q = np.percentile(s, [50, 90]) / rate_o if s.size else [np.nan, np.nan]
        res[p] = dict(k0=best, is_hit=isr[best][0], is_ruin=isr[best][1],
                      oos_hit=float(np.mean(hh)), oos_ruin=float(np.mean(rr)),
                      med=q[0], p90=q[1], kmean=float(np.mean(kms)),
                      rmean=float(np.mean(rms)))

    print(f"{'p':>6}{'IS選択k0':>10}{'実現k平均':>11}{'ボラ比の平均':>13}"
          f"{'IS到達':>9}{'IS破綻':>9}│{'OOS到達':>9}{'OOS破綻':>9}"
          f"{'中央値':>9}{'90%点':>9}{'基準比':>10}")
    base = res[0.0]
    for p in P_GRID:
        r = res[p]
        d = (r["oos_hit"] - base["oos_hit"]) * 100
        tag = "（基準）" if p == 0.0 else f"{d:+.2f}pt"
        print(f"{p:>6}{r['k0']:>10}{r['kmean']:>11.2f}{r['rmean']:>13.3f}"
              f"{100*r['is_hit']:>8.1f}%{100*r['is_ruin']:>8.1f}%"
              f"│{100*r['oos_hit']:>8.1f}%{100*r['oos_ruin']:>8.1f}%"
              f"{r['med']:>8.1f}月{r['p90']:>8.1f}月{tag:>10}")

    print("\n" + "=" * 120)
    print("【継続基準】OOS到達率が p=0.0 比 +2pt以上、かつ破綻確率が悪化しないこと")
    print("=" * 120)
    ok = False
    for p in P_GRID:
        if p == 0.0:
            continue
        r = res[p]
        d = (r["oos_hit"] - base["oos_hit"]) * 100
        dr = (r["oos_ruin"] - base["oos_ruin"]) * 100
        good = (d >= 2.0 and dr <= 0.0)
        ok = ok or good
        print(f"  p={p}: 到達 {d:+.2f}pt / 破綻 {dr:+.2f}pt → "
              f"{'✅ 満たす' if good else '❌ 満たさない'}")
    print(f"\n判定: {'**この軸は有望**' if ok else '**この軸は却下**'}")
    print("\n【診断】ボラ比の平均が1.0付近なら条件付けが両方向に働いている。")
    print("       0.5や2.0に張り付いていればクリップに当たり続けている（V052の欠陥）。")
    print("\n完了。")


if __name__ == "__main__":
    main()
