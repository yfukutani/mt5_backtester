"""V039の追試：ウォークフォワードの各区間が、どの相場局面に当たっているかを調べる。

【なぜ調べるのか】
V039（Codex設計のウォークフォワード）は3fold全てで評価到達率99%超という、
IS→OOS評価（18ヶ月88.3%）とかけ離れた結果を出した。**良すぎる。**

仮説：**FULL窓の前半（2016-2021）と後半（2021-2026）で1取引あたりの期待値が大きく違い、
ウォークフォワードの評価区間3つのうち2つが「強い後半」に入っている。**

既存記録では、1取引あたり平均損益は IS窓（2021.06-2026.06）397円 に対し
OOS窓（2016.11-2021.06）111円 で **3.6倍の差**がある。
つまり本来のOOS評価は「弱い局面」で測っており、ウォークフォワードは
「強い局面」で測っている可能性がある。

本スクリプトは各区間の1取引あたり統計を出して、この仮説を検証する。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import walk_forward as wf

TRAIN, TEST, STEP = wf.TRAIN_MONTHS, wf.TEST_MONTHS, wf.STEP_MONTHS


def month_date(m):
    return wf.FULL_START + timedelta(days=m * 30.4375)


def stats(pr):
    if len(pr) < 2:
        return None
    mu, sd = float(pr.mean()), float(pr.std(ddof=1))
    return dict(n=len(pr), mean=mu, sd=sd, sharpe=mu / sd if sd else 0.0,
                ms2=mu / sd ** 2 * cc.CAPITAL if sd else 0.0, total=float(pr.sum()))


def main():
    times, profits, lags, _ = wf.build_full()

    print("=" * 104)
    print("V039追試：ウォークフォワードの各区間が、どの相場局面に当たっているか")
    print("=" * 104)

    # --- まず年ごとの1取引あたり平均を出す ---
    print("\n【年ごとの1取引あたり損益】")
    print(f"{'年':>6}{'取引数':>8}{'平均円':>10}{'標準偏差':>10}{'シャープ/取引':>14}{'合計円':>12}")
    years = sorted({datetime.fromtimestamp(int(t), tz=timezone.utc).year for t in times})
    for y in years:
        m = np.array([datetime.fromtimestamp(int(t), tz=timezone.utc).year == y
                      for t in times])
        st = stats(profits[m])
        if st:
            print(f"{y:>6}{st['n']:>8}{st['mean']:>10.1f}{st['sd']:>10.0f}"
                  f"{st['sharpe']:>14.4f}{st['total']:>12.0f}")

    # --- IS窓 / OOS窓（既存の定義）---
    print("\n【既存の窓定義との対応】")
    is_start = datetime(2021, 6, 21, tzinfo=timezone.utc).timestamp()
    m_is = times >= is_start
    for label, mask in (("OOS窓相当（2016.11-2021.06）", ~m_is),
                        ("IS窓相当（2021.06-2026.06）", m_is)):
        st = stats(profits[mask])
        print(f"  {label}: {st['n']}取引 / 平均{st['mean']:.1f}円 / "
              f"シャープ{st['sharpe']:.4f}")

    # --- ウォークフォワードの各区間 ---
    print("\n【ウォークフォワードの学習・評価区間】")
    print(f"{'fold':>5}{'区分':>6}{'月':>12}{'暦期間':>26}"
          f"{'取引数':>8}{'平均円':>10}{'シャープ/取引':>14}{'IS窓比率':>10}")
    for i in range(3):
        tr0 = i * STEP
        tr1 = tr0 + TRAIN
        te0, te1 = tr1, tr1 + TEST
        for tag, a, b in (("学習", tr0, tr1), ("評価", te0, te1)):
            pr, lg, n = wf.slice_months(times, profits, lags, a, b)
            t0 = int(wf.FULL_START.timestamp() + a * 30.4375 * 86400)
            t1 = int(wf.FULL_START.timestamp() + b * 30.4375 * 86400)
            sel = (times >= t0) & (times < t1)
            frac_is = float((times[sel] >= is_start).mean()) if sel.any() else 0.0
            st = stats(pr)
            span = f"{month_date(a):%Y-%m} 〜 {month_date(b):%Y-%m}"
            print(f"{i+1:>5}{tag:>6}{f'{a:.0f}-{b:.0f}':>12}{span:>26}"
                  f"{n:>8}{st['mean']:>10.1f}{st['sharpe']:>14.4f}"
                  f"{100*frac_is:>9.0f}%")
        print()

    print("=" * 104)
    print("【結論の読み方】")
    print("=" * 104)
    print("  評価区間の『IS窓比率』が高いほど、**既に「強い」と分かっている局面で測っている**")
    print("  ことになる。本来のOOS評価（2016-2021の弱い局面）とは比較にならない。")
    print("\n完了。")


if __name__ == "__main__":
    main()
