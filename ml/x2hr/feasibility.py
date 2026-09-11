"""X2_HIGH_RISK の成立可能性を測る。

【条件】
  ・運用資金 30,000円（従来の検証は 500,000円）
  ・目標 2倍。期間は1か月が理想、2か月まで
  ・ドローダウンは制約にしない
  ・口座は XM 想定（スタンダード or マイクロ）

【最初に押さえるべき事実】
既存の deal ログは「入金50万・0.01ロット」で測ったもの。**資金が30,000円になると、
同じ0.01ロットでも資金に対する張りは 500000/30000 = 16.7倍になる。**
つまりスタンダード口座で最小ロットを張るだけで、これまでの検証でいう k≒16.7 に相当する。

XMマイクロ口座は1ロット=1,000通貨（スタンダードの1/100）なので、
最小ロット0.01 = 10通貨。これは k≒0.167 相当で、細かく刻める。

【時間の制約が効く】これまでの測定では合算ブック k=8 で2倍まで中央値11か月。
1〜2か月に縮めるには k をさらに上げる必要があり、破綻確率が跳ね上がる。
その交換比率を実測する。
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
BASE_DEPOSIT = 500000.0      # deal ログを測ったときの入金
CAPITAL = 30000.0            # X2_HIGH_RISK の運用資金
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


def simulate(trades, k, ruin_frac, horizon_steps, n_paths=20000, L=20,
             seed=20260911):
    """期限つきの2倍到達。horizon_steps を超えたら未達扱い。

    損益は「入金50万・0.01ロット」基準なので、資金30,000円に対する張りは
    (eq/CAPITAL) * k * (CAPITAL/BASE_DEPOSIT) ... ではなく、
    k を『50万基準のロット倍率』として扱い、資金比で伸縮させる。
    equity_next = eq + profit_x1 * (eq / BASE_DEPOSIT) * k_eff
    ただし初期資金は CAPITAL なので、開始時の張りは k * (CAPITAL/BASE_DEPOSIT)。
    ここでは分かりやすさのため k を「開始時の50万基準ロット倍率」と定義し、
    比例サイジングは資金比 (eq/CAPITAL) で行う。
    """
    rng = random.Random(seed)
    n = len(trades)
    hit = ruin = 0
    steps_hit = []
    for _ in range(n_paths):
        eq = CAPITAL
        step = 0
        state = None
        while step < horizon_steps and state is None:
            start = rng.randrange(n)
            for j in range(L):
                if step >= horizon_steps:
                    break
                # k は50万基準のロット倍率。資金比で伸縮させる。
                scale = k * (eq / CAPITAL)
                eq += trades[(start + j) % n] * scale
                step += 1
                if eq <= CAPITAL * ruin_frac:
                    state = "ruin"; break
                if eq >= CAPITAL * 2.0:
                    state = "hit"; break
        if state == "hit":
            hit += 1; steps_hit.append(step)
        elif state == "ruin":
            ruin += 1
    med = sorted(steps_hit)[len(steps_hit) // 2] if steps_hit else None
    return hit / n_paths, ruin / n_paths, med


def main():
    books = load()
    print(f"運用資金 {CAPITAL:,.0f}円 / deal ログは入金{BASE_DEPOSIT:,.0f}円・0.01ロット基準")
    print()
    print("【ロットの目安】")
    ratio = BASE_DEPOSIT / CAPITAL
    print(f"  スタンダード口座で最小ロット0.01を張る = 50万基準の {ratio:.1f}倍相当")
    print(f"  マイクロ口座（1ロット=1,000通貨）の0.01 = その1/100 = {ratio/100:.3f}倍相当")
    print("  → スタンダードでは『最小ロットが既に高レバレッジ』で刻めない。")
    print("     マイクロなら k を細かく設定できる。")

    for bk in (("both", "OOS"), ("both", "FULL")):
        if bk not in books:
            continue
        s = books[bk]
        t = [p for _, p in s]
        se = se_of_mean(t)
        t_dn = [x - se for x in t]
        win = bk[1]
        per_month = len(t) / MONTHS[win]
        print(f"\n{'='*100}")
        print(f"合算ブック / {win}窓  取引{len(t)}件 = 月あたり {per_month:.1f}件")
        print(f"{'='*100}")
        for limit_months in (1, 2, 3, 6):
            hs = int(round(per_month * limit_months))
            print(f"\n  ■ 期限 {limit_months}か月（{hs}取引）"
                  f"  破綻ライン＝資金の10%")
            print(f"    {'k':>5}{'点推定':>10}{'−1SE':>9}{'P(破綻)':>10}"
                  f"{'到達中央値':>12}")
            for k in (8, 16, 24, 32, 48, 64, 96):
                h, r, med = simulate(t, k, 0.10, hs)
                h2, _, _ = simulate(t_dn, k, 0.10, hs)
                mo = med / per_month if med else None
                print(f"    {k:>5}{100*h:>9.1f}%{'*' if h >= .85 else ' '}"
                      f"{100*h2:>8.1f}%{'*' if h2 >= .85 else ' '}"
                      f"{100*r:>9.1f}%"
                      f"{(f'{mo:.2f}か月' if mo else '—'):>12}")

    print("\n* は85%到達。期限内に2倍にならなければ未達（破綻していなくても不成立）。")


if __name__ == "__main__":
    main()
