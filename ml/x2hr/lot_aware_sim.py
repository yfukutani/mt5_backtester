"""V047：**最小ロット制約を織り込んだ**シミュレーション（V043・V044の測り直し）。

【なぜ必要か】
V046で、dealログの入口取引の **82%がすでに最小ロット（0.01）** であることが分かった。
`MIX_EA.mq5` の `Clamp()` は最小ロット未満を切り上げるため、
**k<1 を指定しても、その枠のロットは変わらない。**

| 指定k | 実効倍率（IS窓） | 乖離 |
|---:|---:|---:|
| 0.25 | 0.653 | **2.61倍** |
| 0.5 | 0.763 | **1.53倍** |
| 0.75 | 0.826 | 1.10倍 |
| **1.0** | **1.000** | **1.00倍** |
| 1.5 | 1.226 | 0.82倍 |
| 2.0 | 2.000 | 1.00倍 |

**しかもこれは一様な縮小ではない。** 最小ロットの枠は 1.0倍のまま、
0.03ロット以上の枠だけが 0.25倍になる——**ブックの構成そのものが変わる。**
V043・V044は損益を連続的にk倍していたため、この制約を一切考慮していない。

【本スクリプトがすること】
各取引の**元のロット**を使い、実際のEAと同じ計算をする。

```
desired = 元ロット × k × (現在資金 / 初期資金)
actual  = max(最小ロット, floor(desired / ステップ) × ステップ)
損益     = 元の損益 × (actual / 元ロット)
```

**限界**：最小ロットは全銘柄0.01・ステップ0.01と仮定している。
暗号資産は銘柄により異なる可能性があるが、暗号は全取引の2%以下なので影響は小さい。
"""
from __future__ import annotations

import bisect
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl

MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
K_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
RUIN = 0.10
LONG_MONTHS = 240.0
L = 20
MONTHS = cc.MONTHS


def build_with_volume(window):
    """窓の (profit, volume) を決済順に返す。volumeは入口dealのもの。"""
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
    return (np.array([x[1] for x in rec], dtype=float),
            np.array([x[2] for x in rec], dtype=float))


def gen(profits, vols, H, n_paths, seed):
    rng = np.random.default_rng(seed)
    n = len(profits)
    nb = H // L + 2
    starts = rng.integers(0, n, size=(n_paths, nb))
    off = np.arange(L)
    idx = (starts[:, :, None] + off[None, None, :]) % n
    idx = idx.reshape(n_paths, -1)[:, :H]
    return profits[idx], vols[idx]


def run(pp, vv, k, ruin_frac, lot_aware):
    n_paths, H = pp.shape
    eq = np.full(n_paths, cc.CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    eff_sum = 0.0
    eff_cnt = 0
    for step in range(H):
        if not alive.any():
            break
        x = eq / cc.CAPITAL
        v = vv[:, step]
        if lot_aware:
            desired = v * k * x
            actual = np.maximum(MIN_LOT,
                                np.floor(desired / STEP + 1e-9) * STEP)
            mult = actual / v
        else:
            mult = k * x
        if step % 50 == 0:
            sub = mult[alive]
            if sub.size:
                eff_sum += float(sub.sum()); eff_cnt += sub.size
        eq = np.where(alive, eq + pp[:, step] * mult, eq)
        hit = alive & (eq >= cc.CAPITAL * 2.0)
        ruin = alive & (eq <= cc.CAPITAL * ruin_frac)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
    return state, stop, (eff_sum / eff_cnt if eff_cnt else 0.0)


def main():
    print("=" * 116)
    print("V047：最小ロット制約を織り込んだシミュレーション（V043・V044の測り直し）")
    print("=" * 116)
    print("各取引の元ロットを使い、実際のEAと同じ Clamp を適用する。")
    print("  desired = 元ロット × k × (現在資金/初期資金)")
    print("  actual  = max(0.01, floor(desired/0.01)×0.01)")
    print("  損益     = 元の損益 × (actual / 元ロット)\n")

    for window in ("IS", "OOS"):
        pr, vo = build_with_volume(window)
        rate = len(pr) / MONTHS[window]
        H = int(round(rate * LONG_MONTHS))
        at_min = float((vo <= MIN_LOT + 1e-9).mean())
        print("=" * 116)
        print(f"【{window}窓】{len(pr)}取引 / 月{rate:.1f}件 / "
              f"最小ロット率 {100*at_min:.1f}% / ホライズン{LONG_MONTHS:.0f}ヶ月")
        print("=" * 116)
        print(f"{'k':>6}{'方式':>14}{'実効倍率':>10}{'到達':>8}{'破綻':>8}{'打切':>7}"
              f"{'中央値':>9}{'75%点':>9}{'90%点':>9}")
        for k in K_GRID:
            for lot_aware, lab in ((False, "従来(連続)"), (True, "ロット制約あり")):
                hits, ruins, cuts, steps, effs = [], [], [], [], []
                for sd in SEEDS:
                    pp, vv = gen(pr, vo, H, N_PATHS, seed=140000 + sd)
                    st, stp, eff = run(pp, vv, k, RUIN, lot_aware)
                    hits.append(float((st == 1).mean()))
                    ruins.append(float((st == 2).mean()))
                    cuts.append(float((st == 0).mean()))
                    steps.append(stp[st == 1])
                    effs.append(eff)
                s = np.concatenate(steps) if steps else np.array([])
                if s.size:
                    q = np.percentile(s, [50, 75, 90]) / rate
                    qs = f"{q[0]:>8.1f}月{q[1]:>8.1f}月{q[2]:>8.1f}月"
                else:
                    qs = f"{'到達なし':>27}"
                print(f"{k if not lot_aware else '':>6}{lab:>14}"
                      f"{np.mean(effs):>10.3f}{100*np.mean(hits):>7.1f}%"
                      f"{100*np.mean(ruins):>7.1f}%{100*np.mean(cuts):>6.1f}%{qs}")
            print()

    print("=" * 116)
    print("【読み方】")
    print("=" * 116)
    print("  ・『実効倍率』は資金比も含めた平均のサイズ倍率。従来方式では k×(資金/初期) に")
    print("    一致するが、ロット制約ありでは最小ロットで下げ止まる")
    print("  ・k<1で両者の差が大きいなら、V043・V044の低いkの結論は実現不可能")
    print("  ・k=1.0以上で差が小さいなら、推奨点（k=1.0）は影響を受けない")
    print("\n完了。")


if __name__ == "__main__":
    main()
