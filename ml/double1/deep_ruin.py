"""破綻ラインを 10% まで下げた場合を計算する。

【注意】破綻ラインを下げるほど「優位ゼロでも到達する確率」が上がり、
指標としての意味が薄くなる。

  破綻ライン   耐えるDD   優位ゼロの到達確率
      70%        30%          34.0%
      50%        50%          50.0%
      35%        65%          60.2%
      20%        80%          69.9%
      10%        90%          76.9%
       5%        95%          81.2%

**破綻ライン5%なら、期待値ゼロのゲームでも81.2%が2倍に到達する。**
目標の85%は、この水準では優位がほとんど無くても届いてしまう。

【最小ロット制約の影響】比例サイジングは資金が減ったらロットも減らす前提だが、
実際には 0.01 ロットが下限で、それ以下には落とせない。資金が初期の10%
（50,000円）まで落ちた局面では、比例配分が要求するロットは 0.01 を大きく下回る枠が
出るため、**実際には想定より大きく張り続けることになり、破綻確率は上がる**。

そこで「ロット下限あり」の経路も併せて計算する。各取引の損益に対して
  実際の倍率 = max(比例倍率, 最小倍率)
とし、最小倍率は「x1（0.01ロット基準）の張り」に相当する 1.0 を下限とする。
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INIT = 500000.0
FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}


def ea_deals(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0 or int(r["magic"]) == 0:
            continue
        out.append((int(r["time"]), p))
    out.sort()
    return out


def load():
    books, runs = {}, {}
    for f in ("results.csv", "results_grid.csv"):
        p = FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                runs[r["window"]] = FX / "run_deals" / r["deals"]
    for w, p in runs.items():
        books[("fx", w)] = ea_deals(p)
    for r in csv.DictReader(open(GOLD / "results.csv", encoding="utf-8")):
        if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
            books[("gold", r["window"])] = ea_deals(GOLD / "run_deals" / r["deals"])
    for w in ("OOS", "FULL"):
        if ("fx", w) in books and ("gold", w) in books:
            books[("both", w)] = sorted(books[("fx", w)] + books[("gold", w)])
    return books


def se_of_mean(t):
    n = len(t)
    m = sum(t) / n
    v = sum((x - m) ** 2 for x in t) / (n - 1)
    return math.sqrt(v / n)


def simulate(trades, k, ruin_frac, min_lot_floor=False,
             n_paths=20000, L=20, max_horizon=5, seed=20260911):
    """min_lot_floor=True なら、実効倍率に下限1.0（＝0.01ロット相当）を設ける。"""
    rng = random.Random(seed)
    n = len(trades)
    total = n * max_horizon
    hit = ruin = 0
    steps = []
    for _ in range(n_paths):
        eq = INIT
        step = 0
        state = None
        while step < total and state is None:
            start = rng.randrange(n)
            for j in range(L):
                if step >= total:
                    break
                scale = (eq / INIT) * k
                if min_lot_floor and scale < 1.0:
                    scale = 1.0        # 0.01ロットより小さくはできない
                eq += trades[(start + j) % n] * scale
                step += 1
                if eq <= INIT * ruin_frac:
                    state = "ruin"; break
                if eq >= INIT * 2.0:
                    state = "hit"; break
        if state == "hit":
            hit += 1; steps.append(step)
        elif state == "ruin":
            ruin += 1
    med = sorted(steps)[len(steps) // 2] if steps else None
    return hit / n_paths, ruin / n_paths, med


def zero_edge(rf):
    return (0 - math.log(rf)) / (math.log(2.0) - math.log(rf))


def main():
    books = load()
    RUINS = (0.05, 0.10, 0.20, 0.35, 0.50, 0.70)

    print("優位ゼロ（期待値がまったく無いゲーム）での到達確率＝実力の下限線")
    print(f"  {'破綻ライン':>10}{'耐えるDD':>10}{'優位ゼロの到達確率':>20}")
    for rf in RUINS:
        print(f"  {'初期の'+f'{100*rf:.0f}%':>10}{f'{100*(1-rf):.0f}%':>10}"
              f"{100*zero_edge(rf):>19.1f}%")

    for bk in (("both", "OOS"), ("both", "FULL"), ("fx", "IS")):
        if bk not in books:
            continue
        s = books[bk]
        t = [p for _, p in s]
        se = se_of_mean(t)
        t_dn = [x - se for x in t]
        print(f"\n{'='*100}")
        print(f"{bk[0].upper()} / {bk[1]}窓  取引{len(t)}件 — 破綻ライン別の2倍化確率")
        print(f"{'='*100}")
        print(f"  {'破綻':>6}{'優位ゼロ':>9}｜{'k=4':^30}｜{'k=8':^30}｜")
        print(f"  {'':>6}{'':>9}｜{'点推定':>8}{'−1SE':>8}{'下限あり':>10}｜"
              f"{'点推定':>8}{'−1SE':>8}{'下限あり':>10}｜")
        for rf in RUINS:
            line = f"  {100*rf:>5.0f}%{100*zero_edge(rf):>8.1f}%｜"
            for k in (4, 8):
                h, _, _ = simulate(t, k, rf)
                h2, _, _ = simulate(t_dn, k, rf)
                h3, _, _ = simulate(t, k, rf, min_lot_floor=True)
                line += (f"{100*h:>7.1f}%{'*' if h >= .85 else ' '}"
                         f"{100*h2:>7.1f}%{'*' if h2 >= .85 else ' '}"
                         f"{100*h3:>9.1f}%{'*' if h3 >= .85 else ' '}｜")
            print(line)

    print("\n* は85%到達。「下限あり」は最小ロット0.01の制約を入れた場合。")
    print("破綻ラインが浅いほど優位ゼロの線が上がるので、")
    print("その線をどれだけ超えているかで実力を見ること。")


if __name__ == "__main__":
    main()
