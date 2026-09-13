"""V052：新たな軸——**金のボラティリティに条件づけたサイジング**。

【動機（V051の発見）】
GOLD枠の優位性は**金のボラティリティに条件づけられている**ことが分かった。

| 期間 | 値幅の標準偏差 | GOLD枠シャープ |
|---|---:|---:|
| A: 2016-2019（静か） | 8.69 | **0.0248** |
| B: 2020-2021.06（大相場） | 19.06 | **0.2298** |
| C: 2021.06-2026（大相場） | 38.02 | **0.1796** |

**ボラが低いときは優位性がほぼ無い。** ならば**ボラが低いときは張らず、高いときに張る**
という条件付きサイジングで、破綻確率を下げつつ到達を早められるかもしれない。

【なぜこれは「新たな軸」なのか】
これまで却下された軸（V026共分散配分・V031枠の取捨選択・V041ブック構成）は、
すべて**枠の静的な重み付け**だった。本案は**時間方向の条件付け**であり、
かつ**外部データを使わず、dealログの約定価格だけで計算できる。**

V028（残存機会数サイジング）も時間方向だったが、あれは「取引頻度の予測」であり、
予測が単純平均を0.8%しか改善せず却下された。**本案が使うのは頻度ではなく
ボラティリティであり、V051でシャープとの明確な関係が確認されている。**

【先読みを避ける設計】
時点tでの倍率は、**tより前の直近N取引の値幅**だけから決める。
未来の値幅は一切見ない。

    vol_t   = 直近N取引の |値幅| の標準偏差（GOLD枠の約定から計算）
    ratio_t = vol_t / 基準ボラ（IS窓の全期間の値幅標準偏差・**IS窓からのみ推定**）
    k_t     = k0 × clip(ratio_t^p, lo, hi)

p（感応度）と clip 範囲は**IS窓で選ぶ**。OOSを見て選び直さない。

【事前登録：報告する条件を先に固定する】
- p ∈ {0.0（＝条件付けなし・基準）, 0.5, 1.0}
- clip ∈ {(0.5, 2.0)}
- k0 は定数kと同じ格子から IS窓で選ぶ
- **すべての p を報告する。良かったものだけを選ばない。**
- 継続基準：OOS到達率が p=0.0（条件付けなし）比 +2pt以上、かつ破綻確率が悪化しないこと

【限界】
- ボラは GOLD枠の約定価格からしか計算していない（FX枠のボラは見ていない）
- 最小ロット制約（V047）は本測定に入れている
- 年ブロック再標本化（V045）は入れていない（L=20で測る）
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
VOL_WINDOW = 40          # 直近40件のGOLD取引で測る
RUIN = 0.10
LONG_MONTHS = 240.0
L = 20
MONTHS = cc.MONTHS


def load(window):
    """窓の (profit, volume, |値幅|, is_gold) を決済順に返す。"""
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


def run(pp, vv, mm, gg, k0, p, base_vol):
    """ボラ条件付きサイジング。倍率は t より前の情報だけから決める。"""
    n_paths, H = pp.shape
    eq = np.full(n_paths, cc.CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    # 直近VOL_WINDOW件のGOLD値幅の二乗和と件数を持ち回る
    buf_sq = np.zeros(n_paths)
    buf_n = np.zeros(n_paths)
    hist = np.zeros((n_paths, VOL_WINDOW))
    hpos = np.zeros(n_paths, dtype=np.int32)
    k_sum = 0.0
    k_cnt = 0
    for step in range(H):
        if not alive.any():
            break
        x = eq / cc.CAPITAL
        if p == 0.0:
            kt = np.full(n_paths, k0)
        else:
            cur = np.where(buf_n >= 10, np.sqrt(buf_sq / np.maximum(buf_n, 1)),
                           base_vol)
            ratio = np.clip((cur / base_vol) ** p, CLIP[0], CLIP[1])
            kt = k0 * ratio
        if step % 50 == 0:
            sub = kt[alive]
            if sub.size:
                k_sum += float(sub.sum()); k_cnt += sub.size
        v = vv[:, step]
        actual = np.maximum(MIN_LOT, np.floor(v * kt * x / STEP + 1e-9) * STEP)
        mult = actual / v
        eq = np.where(alive, eq + pp[:, step] * mult, eq)
        hit = alive & (eq >= cc.CAPITAL * 2.0)
        ruin = alive & (eq <= cc.CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
        # --- ボラ履歴を更新（この取引が終わってから＝次stepで使う） ---
        isg = gg[:, step] > 0
        if isg.any():
            pos = hpos % VOL_WINDOW
            old = hist[np.arange(n_paths), pos]
            newv = mm[:, step]
            buf_sq = np.where(isg, buf_sq - old ** 2 + newv ** 2, buf_sq)
            buf_n = np.where(isg, np.minimum(buf_n + 1, VOL_WINDOW), buf_n)
            hist[np.arange(n_paths), pos] = np.where(isg, newv, old)
            hpos = np.where(isg, hpos + 1, hpos)
    return state, stop, (k_sum / k_cnt if k_cnt else k0)


def main():
    pr_i, vo_i, mv_i, gd_i = load("IS")
    pr_o, vo_o, mv_o, gd_o = load("OOS")
    base_vol = float(np.sqrt((mv_i[gd_i > 0] ** 2).mean()))   # IS窓からのみ推定

    print("=" * 116)
    print("V052：新たな軸——金のボラティリティに条件づけたサイジング")
    print("=" * 116)
    print(f"基準ボラ（IS窓のGOLD値幅RMS・IS窓からのみ推定）= {base_vol:.2f} USD")
    print(f"直近{VOL_WINDOW}件のGOLD取引でボラを測り、k = k0 × clip((vol/基準)^p, "
          f"{CLIP[0]}, {CLIP[1]})")
    print("倍率は t より前の情報だけから決める。最小ロット制約(V047)を織り込み済み。")
    print("**すべてのpを報告する。良かったものだけを選ばない。**\n")

    rate_i = len(pr_i) / MONTHS["IS"]
    rate_o = len(pr_o) / MONTHS["OOS"]
    H_i = int(round(rate_i * LONG_MONTHS))
    H_o = int(round(rate_o * LONG_MONTHS))

    results = {}
    for p in P_GRID:
        # --- IS窓で k0 を選ぶ ---
        best, bp = None, -1.0
        is_rec = {}
        for k0 in K_GRID:
            hs, rs = [], []
            for sd in SEEDS:
                pp, vv, mm, gg = gen(pr_i, vo_i, mv_i, gd_i, H_i, N_PATHS,
                                     seed=170000 + sd)
                st, stp, km = run(pp, vv, mm, gg, k0, p, base_vol)
                hs.append(float((st == 1).mean())); rs.append(float((st == 2).mean()))
            mh = float(np.mean(hs))
            is_rec[k0] = (mh, float(np.mean(rs)))
            if mh > bp:
                best, bp = k0, mh
        # --- OOS適用 ---
        hs, rs, steps, kms = [], [], [], []
        for sd in SEEDS:
            pp, vv, mm, gg = gen(pr_o, vo_o, mv_o, gd_o, H_o, N_PATHS,
                                 seed=180000 + sd)
            st, stp, km = run(pp, vv, mm, gg, best, p, base_vol)
            hs.append(float((st == 1).mean())); rs.append(float((st == 2).mean()))
            steps.append(stp[st == 1]); kms.append(km)
        s = np.concatenate(steps)
        q = np.percentile(s, [50, 90]) / rate_o if s.size else [np.nan, np.nan]
        results[p] = dict(k0=best, is_hit=is_rec[best][0], is_ruin=is_rec[best][1],
                          oos_hit=float(np.mean(hs)), oos_ruin=float(np.mean(rs)),
                          med=q[0], p90=q[1], kmean=float(np.mean(kms)))

    print(f"{'p':>6}{'IS選択k0':>10}{'実現k平均':>11}"
          f"{'IS到達':>9}{'IS破綻':>9}│{'OOS到達':>9}{'OOS破綻':>9}"
          f"{'中央値':>9}{'90%点':>9}{'基準比':>10}")
    base = results.get(0.0)
    for p in P_GRID:
        r = results[p]
        d = (r["oos_hit"] - base["oos_hit"]) * 100 if base else 0.0
        tag = "（基準）" if p == 0.0 else f"{d:+.2f}pt"
        print(f"{p:>6}{r['k0']:>10}{r['kmean']:>11.2f}"
              f"{100*r['is_hit']:>8.1f}%{100*r['is_ruin']:>8.1f}%"
              f"│{100*r['oos_hit']:>8.1f}%{100*r['oos_ruin']:>8.1f}%"
              f"{r['med']:>8.1f}月{r['p90']:>8.1f}月{tag:>10}")

    print("\n" + "=" * 116)
    print("【継続基準】OOS到達率が p=0.0 比 +2pt以上、かつ破綻確率が悪化しないこと")
    print("=" * 116)
    ok = False
    for p in P_GRID:
        if p == 0.0:
            continue
        r = results[p]
        d = (r["oos_hit"] - base["oos_hit"]) * 100
        dr = (r["oos_ruin"] - base["oos_ruin"]) * 100
        v = "✅ 満たす" if (d >= 2.0 and dr <= 0.0) else "❌ 満たさない"
        ok = ok or (d >= 2.0 and dr <= 0.0)
        print(f"  p={p}: 到達 {d:+.2f}pt / 破綻 {dr:+.2f}pt → {v}")
    print(f"\n判定: {'この軸は有望' if ok else '**この軸は却下**'}")
    print("\n完了。")


if __name__ == "__main__":
    main()
