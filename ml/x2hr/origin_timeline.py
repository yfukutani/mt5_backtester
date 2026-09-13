"""V071：実履歴評価の**起点別の内訳**と、1.2倍・3ヶ月の**頑健性**。

【V070で分かったこと】
実履歴（暦の連続した期間・週次起点）で測ると、OOS到達率は
2倍・3ヶ月で37.3%、期限を18ヶ月に延ばしても36.8%とほぼ変わらない。
**70%を満たすのは「1.2倍・3ヶ月」（74.1%）だけ。**

【本スクリプトで確かめること】

**1. 起点別の内訳**——37.3%という数字は「どの時期でも一様に4割」なのか、
   「特定の時期だけ成功して他は全滅」なのか。
   後者なら、**結果は相場環境に強く依存している**ことになる。

**2. 1.2倍・3ヶ月の頑健性**——唯一70%を超えた選択肢なので、
   起点の刻み・k選択規則・破綻ラインを振っても維持されるかを確認する。
   **維持されないなら、それも報告する。**

【限界】V070と同じ。測っているのは「含み損益・証拠金制約を無視した、
確定損益残高の期限内到達確率」であり、実現可能な到達確率の上限でも下限でもない。
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co

K_GRID = co.K_GRID
FLAT_TOL = co.FLAT_TOL


def timeline(rec, ti, w, k, mult, months, step_days=7):
    a, b = co.WINDOW_RANGE[w]
    span = timedelta(days=months * 30.4375)
    out = []
    d = a
    while d + span <= b:
        r = co.simulate(rec, ti, int(d.timestamp()),
                        int((d + span).timestamp()), k, mult)
        out.append((d, r))
        d += timedelta(days=step_days)
    return out


def select_k(rec, ti, mult, months, ruin):
    old = co.RUIN
    co.RUIN = ruin
    hits = {}
    for k in K_GRID:
        h, _, _, _ = co.evaluate(rec, ti, "IS", k, mult, months)
        hits[k] = h
    co.RUIN = old
    best = max(hits.values())
    flat = [k for k in K_GRID if hits[k] >= best - FLAT_TOL]
    return flat[len(flat) // 2], hits


def main():
    print("=" * 108)
    print("V071：実履歴評価の起点別の内訳と、1.2倍・3ヶ月の頑健性")
    print("=" * 108)
    data = {w: co.load_events(w) for w in ("IS", "OOS")}

    # ---------- 1. 起点別の内訳（2倍・3ヶ月） ----------
    print("\n【1. 起点別の内訳】2倍・3ヶ月（IS選択 k=8.0）")
    print("  年ごとに、その年に始まった起点の成否を数える\n")
    print(f"{'窓':>5}{'年':>7}{'起点':>7}{'到達':>7}{'破綻':>7}{'期限切れ':>9}"
          f"{'到達率':>9}")
    for w in ("IS", "OOS"):
        rec, ti = data[w]
        tl = timeline(rec, ti, w, 8.0, 2.0, 3)
        by = {}
        for d, r in tl:
            by.setdefault(d.year, []).append(r)
        for y in sorted(by):
            v = np.array(by[y])
            print(f"{w:>5}{y:>7}{len(v):>7}{int((v==1).sum()):>7}"
                  f"{int((v==2).sum()):>7}{int((v==0).sum()):>9}"
                  f"{100*(v==1).mean():>8.1f}%")
        print()

    # ---------- 2. 1.2倍・3ヶ月の頑健性 ----------
    print("=" * 108)
    print("【2. 1.2倍・3ヶ月の頑健性】唯一70%を超えた選択肢")
    print("=" * 108)

    print("\n  (a) 起点の刻みを振る（k=6.0固定）")
    print(f"{'刻み':>8}{'IS起点':>8}{'IS到達':>9}│{'OOS起点':>9}{'OOS到達':>9}{'70%':>6}")
    for sd in (1, 3, 7, 14, 30):
        res = {}
        for w in ("IS", "OOS"):
            rec, ti = data[w]
            tl = timeline(rec, ti, w, 6.0, 1.2, 3, step_days=sd)
            v = np.array([r for _, r in tl])
            res[w] = (len(v), float((v == 1).mean()))
        print(f"{sd:>7}日{res['IS'][0]:>8}{100*res['IS'][1]:>8.1f}%"
              f"│{res['OOS'][0]:>9}{100*res['OOS'][1]:>8.1f}%"
              f"{'✅' if res['OOS'][1] >= 0.70 else '❌':>6}")

    print("\n  (b) kを振る（起点7日刻み）")
    print(f"{'k':>8}{'IS到達':>9}│{'OOS到達':>9}{'OOS破綻':>9}{'70%':>6}")
    for k in K_GRID:
        ih, _, _, _ = co.evaluate(*data["IS"], "IS", k, 1.2, 3)
        oh, orr, _, _ = co.evaluate(*data["OOS"], "OOS", k, 1.2, 3)
        print(f"{k:>8}{100*ih:>8.1f}%│{100*oh:>8.1f}%{100*orr:>8.1f}%"
              f"{'✅' if oh >= 0.70 else '❌':>6}")

    print("\n  (c) 破綻ラインを振る（k選択も各水準でやり直す）")
    print(f"{'破綻ライン':>11}{'IS選択k':>9}{'IS到達':>9}│{'OOS到達':>9}{'OOS破綻':>9}{'70%':>6}")
    for ruin in (0.05, 0.10, 0.20, 0.50):
        k_sel, _ = select_k(*data["IS"], 1.2, 3, ruin)
        old = co.RUIN
        co.RUIN = ruin
        ih, _, _, _ = co.evaluate(*data["IS"], "IS", k_sel, 1.2, 3)
        oh, orr, _, _ = co.evaluate(*data["OOS"], "OOS", k_sel, 1.2, 3)
        co.RUIN = old
        print(f"{100*ruin:>10.0f}%{k_sel:>9}{100*ih:>8.1f}%"
              f"│{100*oh:>8.1f}%{100*orr:>8.1f}%"
              f"{'✅' if oh >= 0.70 else '❌':>6}")

    print("\n  (d) 1.2倍・3ヶ月の起点別内訳（k=6.0）")
    print(f"{'窓':>5}{'年':>7}{'起点':>7}{'到達':>7}{'到達率':>9}")
    for w in ("IS", "OOS"):
        rec, ti = data[w]
        tl = timeline(rec, ti, w, 6.0, 1.2, 3)
        by = {}
        for d, r in tl:
            by.setdefault(d.year, []).append(r)
        for y in sorted(by):
            v = np.array(by[y])
            print(f"{w:>5}{y:>7}{len(v):>7}{int((v==1).sum()):>7}"
                  f"{100*(v==1).mean():>8.1f}%")
        print()

    print("=" * 108)
    print("【限界】V070と同じ")
    print("=" * 108)
    print("  ・測っているのは『含み損益・証拠金制約を無視した、確定損益残高の")
    print("    期限内到達確率』であり、実現可能な到達確率の上限でも下限でもない")
    print("  ・起点が重なるため、刻みを細かくしても独立な情報量は増えない")
    print("  ・OOS 55ヶ月で重ならない3ヶ月区間は約18個")
    print("\n完了。")


if __name__ == "__main__":
    main()
