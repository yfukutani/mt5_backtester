"""破綻ラインを厳しくして、2倍化確率が「実力」なのか「破綻ラインの遠さ」なのかを分ける。

【なぜ必要か】前回の測定で、破綻ライン＝初期資金の20%（＝80%のドローダウンに耐える）
なら、**期待値がまったくゼロのゲームでも 69.9% は2倍に到達する**ことが分かった。
目標の85%は、優位がほぼ無くても届いてしまう水準である。

破綻ラインを2倍ライン（+100%）に近づけていくと、優位ゼロの到達確率は 50% に近づく。
そこで85%を保てるなら、それは破綻ラインの遠さではなく**優位そのもの**が効いている。

【推定誤差の織り込み】ブートストラップは標本平均を真の優位として扱う。
FX OOS は t値 1.58 で優位がゼロである可能性を否定できないため、
**各取引の損益を一律に標準誤差ぶん下げた系列**でも測る。
これは「優位の推定が1標準誤差ぶん楽観的だった場合」に相当する。
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


def ea_trades(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0 or int(r["magic"]) == 0:   # magic=0 は期間終了時の強制決済
            continue
        out.append((int(r["time"]), p))
    out.sort()
    return [p for _, p in out]


def load_books():
    books = {}
    runs = {}
    for f in ("results.csv", "results_grid.csv"):
        p = FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                runs[r["window"]] = FX / "run_deals" / r["deals"]
    for w, p in runs.items():
        books[("fx", w)] = ea_trades(p)
    for r in csv.DictReader(open(GOLD / "results.csv", encoding="utf-8")):
        if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
            books[("gold", r["window"])] = ea_trades(GOLD / "run_deals" / r["deals"])
    return books


def se_of_mean(t):
    n = len(t)
    m = sum(t) / n
    v = sum((x - m) ** 2 for x in t) / (n - 1)
    return math.sqrt(v / n)


def simulate(trades, k, ruin_frac, n_paths=20000, L=20,
             max_horizon=5, seed=20260911):
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
                eq += trades[(start + j) % n] * (eq / INIT) * k
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


def zero_edge_baseline(ruin_frac):
    """優位ゼロのときの到達確率（比較の基準線）。"""
    a, b = math.log(ruin_frac), math.log(2.0)
    return (0 - a) / (b - a)


def main():
    books = load_books()
    RUINS = (0.2, 0.35, 0.5, 0.7)
    KS = (2, 4, 8, 16)

    print("破綻ラインを厳しくしたときの2倍化確率（EA由来のみ / L=20 / 最大5履歴 / 2万経路）")
    print("「優位ゼロ」は期待値ゼロのゲームでの到達確率＝実力の下限線。\n")

    for b in ("fx", "gold"):
        wins = [w for w in ("IS", "OOS", "FULL") if (b, w) in books]
        if not wins:
            continue
        for rf in RUINS:
            base = zero_edge_baseline(rf)
            print(f"{'='*94}")
            print(f"{b.upper()} / 破綻ライン＝初期資金の{100*rf:.0f}%"
                  f"（{100*(1-rf):.0f}%のDDに耐える）/ 優位ゼロの到達確率 {100*base:.1f}%")
            print(f"{'='*94}")
            print(f"  {'k':>3}｜" + "".join(f"{w:^30}｜" for w in wins))
            print(f"  {'':>3}｜" + "".join(f"{'点推定':>9}{'−1SE':>9}{'月数':>10}｜"
                                          for _ in wins))
            for k in KS:
                line = f"  {k:>3}｜"
                for w in wins:
                    t = books[(b, w)]
                    se = se_of_mean(t)
                    t_dn = [x - se for x in t]      # 優位を1SEぶん下げた系列
                    h, r, med = simulate(t, k, rf)
                    h2, r2, _ = simulate(t_dn, k, rf)
                    mo = med / len(t) * MONTHS[w] if med else None
                    mark = "*" if h >= 0.85 else " "
                    mark2 = "*" if h2 >= 0.85 else " "
                    line += (f"{100*h:>8.1f}%{mark}{100*h2:>7.1f}%{mark2}"
                             f"{(f'{mo:.0f}' if mo else '—'):>10}｜")
                print(line)
            print()

    print("* は85%到達。点推定と−1SEの両方に * が付く条件だけが、"
          "推定誤差を織り込んでも目標を満たす。")
    print("優位ゼロの到達確率を大きく超えていなければ、"
          "勝因は優位ではなく破綻ラインの遠さである。")


if __name__ == "__main__":
    main()
