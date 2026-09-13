"""V045：**年単位の局面変化**を織り込んだ再標本化で、V043・V044の数字を測り直す。

【なぜ必要か】
V043・V044は、これまでと同じ**ブロック長L=20取引**のブロックブートストラップで測った。
L=20はおよそ**半月分**の取引しか保持しない。

一方 V040 で、ブックの1取引あたり期待値は**年ごとに大きく変わる**ことが分かっている。

| 年 | 2018 | 2020 | 2022 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| 1取引平均 | **−48円** | 140円 | 449円 | 438円 | **1,281円** |

**L=20のブートストラップは、この年単位の構造を壊す。** 4,000取引のパスは200個の
半月ブロックの寄せ集めになり、全期間の平均へ強く収束する。結果として
**「不調な年が2〜3年続く」というパスがほとんど生成されない。**

**実運用のリスクはこれより高いはずである。** V043の「OOS到達率100.0%・破綻0.0%」も、
V044の所要期間も、この過小評価の影響を受けている可能性がある。

【本スクリプトがすること】
ブロックの取り方を3通りにして、同じ測定を繰り返す。

| 方式 | ブロック | 保持する構造 |
|---|---|---|
| **L=20**（従来） | 20取引 ≒ 半月 | 短期の連敗・連勝のみ |
| **半年ブロック** | 暦の半年ごと | 半年スケールの局面 |
| **年ブロック** | 暦年ごと | 年スケールの局面（2018年の不調など） |

年ブロックは**復元抽出**する。同じ年が連続して引かれれば「不調が2年続く」パスになる。

【限界】
- IS窓は5年、OOS窓は4.6年しかない。**年ブロックの母集団が5個程度**しかないため、
  再標本化としては粗い。これは「データが足りない」という事実そのものである
- 年をまたぐ建玉の扱いは決済時刻で切っている
- 将来の局面が過去10年のいずれかに似ているという仮定が入る
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl
import walk_forward as wf

N_PATHS = 20000
SEEDS = (101, 202, 303)
K_GRID = [0.5, 1.0, 1.5, 2.0]
RUIN = 0.10
LONG_MONTHS = 240.0


def group_blocks(times, profits, mode):
    """mode='year' / 'half' で、暦のまとまりごとに損益配列を作る。"""
    g = defaultdict(list)
    for t, p in zip(times, profits):
        d = datetime.fromtimestamp(int(t), tz=timezone.utc)
        key = d.year if mode == "year" else (d.year, 1 if d.month <= 6 else 2)
        g[key].append(float(p))
    return [np.array(v, dtype=float) for k, v in sorted(g.items()) if len(v) >= 5]


def paths_from_blocks(blocks, H, n_paths, seed):
    """暦ブロックを復元抽出して連結し、(n_paths, H) のパスを作る。"""
    rng = np.random.default_rng(seed)
    nb = len(blocks)
    lens = np.array([len(b) for b in blocks])
    avg = max(1, int(lens.mean()))
    need = H // avg + 3
    out = np.empty((n_paths, H), dtype=float)
    for i in range(n_paths):
        idx = rng.integers(0, nb, size=need)
        buf = np.concatenate([blocks[j] for j in idx])
        while buf.size < H:
            buf = np.concatenate([buf] + [blocks[j] for j in
                                          rng.integers(0, nb, size=need)])
        out[i] = buf[:H]
    return out


def run(paths, k, ruin_frac):
    n_paths, H = paths.shape
    eq = np.full(n_paths, cc.CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop = np.full(n_paths, H, dtype=np.int32)
    for step in range(H):
        if not alive.any():
            break
        eq = np.where(alive, eq + paths[:, step] * k * (eq / cc.CAPITAL), eq)
        hit = alive & (eq >= cc.CAPITAL * 2.0)
        ruin = alive & (eq <= cc.CAPITAL * ruin_frac)
        state[hit] = 1
        state[ruin] = 2
        stop[hit | ruin] = step + 1
        alive = alive & ~(hit | ruin)
    return state, stop


def main():
    times, profits, lags, _ = wf.build_full()
    is_start = datetime(2021, 6, 21, tzinfo=timezone.utc).timestamp()
    sel_is = times >= is_start
    windows = {
        "IS": (times[sel_is], profits[sel_is], cc.MONTHS["IS"]),
        "OOS": (times[~sel_is], profits[~sel_is], cc.MONTHS["OOS"]),
        "FULL": (times, profits, cc.MONTHS["FULL"]),
    }

    print("=" * 116)
    print("V045：年単位の局面変化を織り込んだ再標本化（V043・V044の測り直し）")
    print("=" * 116)
    print("L=20（従来）は半月分の構造しか保持せず、年単位の局面変化を壊す。")
    print("暦の半年・1年ごとにブロックを取って復元抽出し、同じ測定を繰り返す。\n")

    for wname, (tt, pp, months) in windows.items():
        rate = len(pp) / months
        H = int(round(rate * LONG_MONTHS))
        yb = group_blocks(tt, pp, "year")
        hb = group_blocks(tt, pp, "half")
        print("=" * 116)
        print(f"【{wname}窓】{len(pp)}取引 / {months:.0f}ヶ月 / 月{rate:.1f}件 / "
              f"ホライズン{LONG_MONTHS:.0f}ヶ月（{H}取引）")
        print(f"  年ブロック {len(yb)}個（{[len(b) for b in yb]}）")
        print(f"  半年ブロック {len(hb)}個")
        print("=" * 116)
        print(f"{'方式':>12}{'k':>6}{'到達':>8}{'破綻':>8}{'打切':>8}"
              f"{'中央値':>9}{'75%点':>9}{'90%点':>9}{'95%点':>9}")

        for mode, blocks in (("L=20(従来)", None), ("半年ブロック", hb),
                             ("年ブロック", yb)):
            if blocks is not None and len(blocks) < 3:
                print(f"{mode:>12}  ブロックが3個未満のため飛ばす")
                continue
            for k in K_GRID:
                hits, ruins, cuts, steps = [], [], [], []
                for sd in SEEDS:
                    if blocks is None:
                        paths = dk.generate_paths(pp, H, N_PATHS, dkl.L,
                                                  seed=120000 + sd)
                    else:
                        paths = paths_from_blocks(blocks, H, N_PATHS,
                                                  seed=130000 + sd)
                    st, stp = run(paths, k, RUIN)
                    hits.append(float((st == 1).mean()))
                    ruins.append(float((st == 2).mean()))
                    cuts.append(float((st == 0).mean()))
                    steps.append(stp[st == 1])
                s = np.concatenate(steps) if steps else np.array([])
                if s.size:
                    q = np.percentile(s, [50, 75, 90, 95]) / rate
                    print(f"{mode:>12}{k:>6}{100*np.mean(hits):>7.1f}%"
                          f"{100*np.mean(ruins):>7.1f}%{100*np.mean(cuts):>7.1f}%"
                          f"{q[0]:>8.1f}月{q[1]:>8.1f}月{q[2]:>8.1f}月{q[3]:>8.1f}月")
                else:
                    print(f"{mode:>12}{k:>6}{100*np.mean(hits):>7.1f}%"
                          f"{100*np.mean(ruins):>7.1f}%{100*np.mean(cuts):>7.1f}%"
                          f"{'到達なし':>36}")
            print()

    print("=" * 116)
    print("【読み方】")
    print("=" * 116)
    print("  ・年ブロックのほうが到達率が下がり破綻率が上がるなら、L=20はリスクを過小評価していた")
    print("  ・所要期間の90/95%点が大きく伸びるなら、『待てば必ず届く』という読み方は危険")
    print("  ・年ブロックの母集団はIS 5個・OOS 5個しかない。粗い推定であることを忘れない")
    print("\n完了。")


if __name__ == "__main__":
    main()
