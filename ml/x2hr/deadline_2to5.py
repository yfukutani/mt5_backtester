"""期限を2/3/4/5か月とした場合の到達確率を詳しく検証する（ユーザー指示・2026-09-12）。

V009では1/2/3/6/12/24か月を粗く見た。今回は**2〜5か月をより細かい倍率刻みで**測り、
「期限を1か月延ばすと到達確率がどれだけ上がるか」を定量化する。3窓（IS/OOS/FULL）で実施。
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc

RUIN = 0.10
MONTHS = cc.MONTHS
LIMITS = (2, 3, 4, 5)
KS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)


def main() -> None:
    books = cc.load()
    print("=" * 90)
    print("期限2〜5か月：最良kでの到達確率（破綻ライン10%・20,000パス・block bootstrap L=20）")
    print("=" * 90)
    print(f"{'窓':>5}{'期限':>6}{'最良k':>7}{'P(2倍)':>9}{'P(破綻)':>9}"
          f"{'P(期限切れ)':>12}{'到達中央値':>12}{'閉形式(参考)':>13}")

    summary: dict[str, dict[int, tuple[float, float, float, float]]] = {}

    for w in ("IS", "OOS", "FULL"):
        t = [p for _, p in books[("both", w)]]
        n = len(t)
        mean = sum(t) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in t) / (n - 1))
        mr, sr = mean / cc.CAPITAL, sd / cc.CAPITAL
        rate = n / MONTHS[w]
        summary[w] = {}
        for limit in LIMITS:
            hs = int(round(rate * limit))
            best = None
            for k in KS:
                h, r, med = cc.simulate(t, k, RUIN, hs, seed=20260912 + limit)
                if best is None or h > best[1]:
                    best = (k, h, r, med)
            k, h, r, med = best
            mo = f"{med / rate:.2f}か月" if med else "—"
            closed = cc.closed_form(mr, sr, k, RUIN)
            summary[w][limit] = (k, h, r, med)
            print(f"{w:>5}{limit:>5}月{k:>7.2f}{100*h:>8.1f}%{100*r:>8.1f}%"
                  f"{100*(1-h-r):>11.1f}%{mo:>12}{100*closed:>12.1f}%")
        print()

    print("=" * 90)
    print("期限を1か月延ばすごとの到達確率の伸び（OOS基準・最も保守的な窓）")
    print("=" * 90)
    prev = None
    for limit in LIMITS:
        k, h, r, med = summary["OOS"][limit]
        gain = f"(+{100*(h-prev):.1f}pt)" if prev is not None else ""
        print(f"  {limit}か月: {100*h:.1f}% {gain}")
        prev = h

    print()
    print("=" * 90)
    print("R3(85%)達成まであと何ポイントか（3窓）")
    print("=" * 90)
    for w in ("IS", "OOS", "FULL"):
        print(f"  {w}:")
        for limit in LIMITS:
            k, h, r, med = summary[w][limit]
            gap = 85.0 - 100 * h
            tag = "  ★達成" if gap <= 0 else f"  あと{gap:.1f}pt"
            print(f"    {limit}か月: {100*h:.1f}%{tag}")


if __name__ == "__main__":
    main()
