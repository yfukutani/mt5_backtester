"""V048：**最小ロット制約（V047）と年単位の局面持続（V045）を同時に**織り込む。

これまで2つの補正を別々に測ってきた。

| 補正 | 効果 |
|---|---|
| **最小ロット制約**（V047） | 破綻確率が2.6倍（k=1.0でOOS 2.0%→5.2%）。下落時に減量できない |
| **年ブロック再標本化**（V045） | 所要期間の中央値が+55%（k=1.0でOOS 5.6→8.7ヶ月） |

**両方を同時に織り込んだ測定はまだ行っていない。** 本スクリプトがそれを行う。
これが**現時点で最も実口座に近い評価**である。

【4条件を並べて比較する】
1. 従来（連続k・L=20ブロック）—— V043/V044の条件
2. ロット制約のみ（V047の条件）
3. 年ブロックのみ（V045の条件）
4. **両方**（本検証の主結果）

【限界】
- 年ブロックの母集団はIS/OOSとも6個しかなく、**「過去より悪い局面」は生成できない**
- 最小ロット0.01・ステップ0.01を全銘柄に仮定
- 証拠金不足で発注できない場面は考慮していない（常に0.01は出せる前提）
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl

MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
K_GRID = [0.5, 1.0, 1.5, 2.0]
RUIN = 0.10
LONG_MONTHS = 240.0
L = 20
MONTHS = cc.MONTHS


def build(window):
    """窓の (time, profit, volume) を決済順に返す。"""
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["magic"]) == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"])))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol in rows:
            if entry == 0:
                opened[pid] = vol
            else:
                v = opened.pop(pid, None)
                if v is None or profit == 0.0 or v <= 0:
                    continue
                rec.append((t, profit, v))
    rec.sort()
    return (np.array([x[0] for x in rec], dtype=np.int64),
            np.array([x[1] for x in rec], dtype=float),
            np.array([x[2] for x in rec], dtype=float))


def year_blocks(times, profits, vols):
    g = defaultdict(list)
    for t, p, v in zip(times, profits, vols):
        g[datetime.fromtimestamp(int(t), tz=timezone.utc).year].append((p, v))
    out = []
    for _, lst in sorted(g.items()):
        if len(lst) >= 5:
            out.append((np.array([a for a, _ in lst]),
                        np.array([b for _, b in lst])))
    return out


def gen_l20(profits, vols, H, n_paths, seed):
    rng = np.random.default_rng(seed)
    n = len(profits)
    nb = H // L + 2
    starts = rng.integers(0, n, size=(n_paths, nb))
    off = np.arange(L)
    idx = (starts[:, :, None] + off[None, None, :]) % n
    idx = idx.reshape(n_paths, -1)[:, :H]
    return profits[idx], vols[idx]


def gen_year(blocks, H, n_paths, seed):
    rng = np.random.default_rng(seed)
    nb = len(blocks)
    avg = max(1, int(np.mean([len(b[0]) for b in blocks])))
    need = H // avg + 3
    P = np.empty((n_paths, H), dtype=float)
    V = np.empty((n_paths, H), dtype=float)
    for i in range(n_paths):
        idx = rng.integers(0, nb, size=need)
        bp = np.concatenate([blocks[j][0] for j in idx])
        bv = np.concatenate([blocks[j][1] for j in idx])
        while bp.size < H:
            more = rng.integers(0, nb, size=need)
            bp = np.concatenate([bp] + [blocks[j][0] for j in more])
            bv = np.concatenate([bv] + [blocks[j][1] for j in more])
        P[i] = bp[:H]
        V[i] = bv[:H]
    return P, V


def run(pp, vv, k, lot_aware):
    n_paths, H = pp.shape
    eq = np.full(n_paths, cc.CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    for step in range(H):
        if not alive.any():
            break
        x = eq / cc.CAPITAL
        if lot_aware:
            v = vv[:, step]
            actual = np.maximum(MIN_LOT, np.floor(v * k * x / STEP + 1e-9) * STEP)
            mult = actual / v
        else:
            mult = k * x
        eq = np.where(alive, eq + pp[:, step] * mult, eq)
        hit = alive & (eq >= cc.CAPITAL * 2.0)
        ruin = alive & (eq <= cc.CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
    return state, stop


def main():
    print("=" * 120)
    print("V048：最小ロット制約（V047）と年単位の局面持続（V045）を同時に織り込む")
    print("=" * 120)
    print("これが現時点で最も実口座に近い評価。4条件を並べて比較する。\n")

    for window in ("IS", "OOS"):
        tt, pr, vo = build(window)
        rate = len(pr) / MONTHS[window]
        H = int(round(rate * LONG_MONTHS))
        yb = year_blocks(tt, pr, vo)
        print("=" * 120)
        print(f"【{window}窓】{len(pr)}取引 / 月{rate:.1f}件 / "
              f"最小ロット率 {100*float((vo<=MIN_LOT+1e-9).mean()):.1f}% / "
              f"年ブロック{len(yb)}個")
        print("=" * 120)
        print(f"{'k':>5}{'条件':>22}{'到達':>8}{'破綻':>8}{'打切':>7}"
              f"{'中央値':>9}{'75%点':>9}{'90%点':>9}{'95%点':>9}{'R3':>5}")
        for k in K_GRID:
            for tag, use_year, lot_aware in (
                    ("従来(連続・L=20)", False, False),
                    ("ロット制約のみ", False, True),
                    ("年ブロックのみ", True, False),
                    ("★両方", True, True)):
                hits, ruins, cuts, steps = [], [], [], []
                for sd in SEEDS:
                    if use_year:
                        pp, vv = gen_year(yb, H, N_PATHS, seed=150000 + sd)
                    else:
                        pp, vv = gen_l20(pr, vo, H, N_PATHS, seed=160000 + sd)
                    st, stp = run(pp, vv, k, lot_aware)
                    hits.append(float((st == 1).mean()))
                    ruins.append(float((st == 2).mean()))
                    cuts.append(float((st == 0).mean()))
                    steps.append(stp[st == 1])
                s = np.concatenate(steps) if steps else np.array([])
                mh = float(np.mean(hits))
                if s.size:
                    q = np.percentile(s, [50, 75, 90, 95]) / rate
                    qs = (f"{q[0]:>8.1f}月{q[1]:>8.1f}月{q[2]:>8.1f}月{q[3]:>8.1f}月")
                else:
                    qs = f"{'到達なし':>36}"
                print(f"{k if tag.startswith('従来') else '':>5}{tag:>22}"
                      f"{100*mh:>7.1f}%{100*np.mean(ruins):>7.1f}%"
                      f"{100*np.mean(cuts):>6.1f}%{qs}"
                      f"{'✅' if mh >= 0.85 else '❌':>5}")
            print()

    print("=" * 120)
    print("【限界】")
    print("=" * 120)
    print("  ・年ブロックの母集団は6個程度。『過去より悪い局面』は生成できない")
    print("  ・最小ロット0.01・ステップ0.01を全銘柄に仮定")
    print("  ・証拠金不足で発注できない場面は考慮していない（常に0.01は出せる前提）")
    print("\n完了。")


if __name__ == "__main__":
    main()
