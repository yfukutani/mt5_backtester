"""V103：**SCA GBPJPY の重みを変えたときの到達率**（簡易検証・2026-09-13）。

【V102で分かったこと】
弱局面の不毛月の損失の86%は SCA GBPJPY。重みを下げると——

| SCA GBPJPY | 弱局面 純益 | 12月移動 最小 | 12月マイナス窓 | IS窓 12月移動 最小 |
|---:|---:|---:|---:|---:|
| 0.00倍 | 35,129 | **−15,473** | **6/27** | **49,802** |
| **1.00倍（現状）** | 58,541 | −20,908 | 7/27 | 25,159 |
| 1.50倍 | 70,247 | −23,944 | 8/27 | 11,961 |

**重みを下げると純益は減るが、12ヶ月移動合計の最小値は改善する。**
**IS窓では 25,159 → 49,802 と大きく改善する。**

**ただし0倍にしてもマイナス窓は 7/27 → 6/27 にしかならない。**
（未来を知っている前提の〔上限〕なら0/27だが、それは実現できない）

【本スクリプトで測ること】
**最終的な判定基準は「純益」でも「移動合計」でもなく「2倍への到達率」。**
SCA GBPJPY の重みを変えて、**実際の到達率**を測る。

弱局面の実履歴（起点＋期限 ≤ 2020-01-01）・資金10万円・破綻ライン10%・倍率2倍固定。
**kは各重み・各期限でIS窓から選ぶ（OOSを見ない・R2ルール）。**

【限界】
- 重みの変更は損益を定数倍する近似。**最小ロット制約を無視している**
  （SCA GBPJPY は0.01ロット固定なので、0.5倍は実際には作れない）
- 起点が重なるため独立ではない
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_committed as dc
import target_policy_gap as tpg

QUIET_END = tpg.QUIET_END
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
WEIGHTS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5]
TARGET = 20261001            # SCA GBPJPY
DEADLINES = [3, 6, 12]


def load_with_magic(window):
    import csv
    import dynamic_k_lag as dkl
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            if m == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"]), m))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol, m in rows:
            if entry == 0:
                opened[pid] = (t, vol, m)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((o[0], t, profit, o[1], o[2]))
    rec.sort()
    return rec


def weighted(rec, w):
    """SCA GBPJPY の損益を w 倍にする（ロットを w 倍にしたのと同じ）。"""
    return [(a, b, (c * w if m == TARGET else c), d)
            for a, b, c, d, m in rec]


def evaluate(rec, k, start, end_cap, months, step_days=7):
    ti = [x[0] for x in rec]
    hit = ruin = n = 0
    d = start
    while cod.add_months(d, months) <= end_cap:
        t_end = cod.add_months(d, months)
        h, r = dc.simulate(rec, ti, int(d.timestamp()), int(t_end.timestamp()),
                           k, None, 0.0)
        hit += h
        ruin += r
        n += 1
        d += timedelta(days=step_days)
    return (hit / n if n else 0.0), (ruin / n if n else 0.0), n


def pick_k(rec_is, start, end_cap, months):
    """R2ルール：IS最大から1pt以内のkの中央値。"""
    hs = [evaluate(rec_is, k, start, end_cap, months)[0] for k in K_GRID]
    top = max(hs)
    near = [k for k, h in zip(K_GRID, hs) if h >= top - 0.01]
    best = float(np.median(near))
    return best if best in K_GRID else min(near, key=lambda k: abs(k - best))


def main():
    print("=" * 110)
    print("V103：SCA GBPJPY の重みを変えたときの到達率")
    print("=" * 110)
    print("★ **最終的な判定基準は純益でも移動合計でもなく「2倍への到達率」。**")
    print("  弱局面の不毛月の損失の86%は SCA GBPJPY。重みを変えて到達率を測る。\n")
    print("  弱局面の実履歴・資金10万円・破綻ライン10%・**倍率2倍固定**")
    print("  **kは各重み・各期限でIS窓から選ぶ（OOSを見ない・R2ルール）**\n")

    raw = {w: load_with_magic(w) for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    for D in DEADLINES:
        tgt = 0.65 if D in (3, 6) else 0.90
        print("=" * 110)
        print(f"【期限 {D}ヶ月】判定水準 {100*tgt:.0f}%")
        print("=" * 110)
        print(f"{'SCA GBPJPY':>12}{'IS選択k':>9}{'IS到達':>9}{'IS破綻':>9}"
              f"│{'**OOS到達**':>13}{'OOS破綻':>10}{'OOS起点':>9}{'判定':>7}")
        for w in WEIGHTS:
            ri = weighted(raw["IS"], w)
            ro = weighted(raw["OOS"], w)
            k = pick_k(ri, a_is, b_is, D)
            ih, ir, _ = evaluate(ri, k, a_is, b_is, D)
            oh, orr, on = evaluate(ro, k, a_oos, QUIET_END, D)
            tag = "**現状**" if w == 1.0 else f"{w:.2f}倍"
            print(f"{tag:>12}{k:>9.0f}{100*ih:>8.1f}%{100*ir:>8.1f}%"
                  f"│{100*oh:>12.1f}%{100*orr:>9.1f}%{on:>9}"
                  f"{'OK' if oh >= tgt else 'NG':>7}")
        print()

    print("=" * 110)
    print("【限界】")
    print("=" * 110)
    print("  ・重みの変更は損益を定数倍する近似。**最小ロット制約を無視している**")
    print("    （SCA GBPJPY は0.01ロット固定なので0.5倍は実際には作れない）")
    print("  ・起点が重なるため独立ではない")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
