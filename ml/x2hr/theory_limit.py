"""X2_HIGH_RISK の理論上の限界を確定する。

【V006で観測した「48%の頭打ち」の正体】

比例サイジングで log(資金) は算術ブラウン運動になる。1取引あたりの
算術平均を m、標準偏差を s（いずれも資金比）、ロット倍率を k とすると

    μ_log ≈ k·m − (k·s)²/2      σ_log ≈ k·s

上限先着確率の指数は

    z = −2μ_log/σ_log² = 1 − 2m/(k·s²)

**k→∞ で z→1** となり、到達確率は

    P → (1 − ruin_frac) / (2 − ruin_frac)

に収束する。破綻ライン10%なら 0.9/1.9 = **47.4%**。
V006で測った「どの倍率でも48%前後」はこの理論値そのものだった。

つまり**倍率を上げても越えられない天井が存在する**。

【到達速度の限界】

到達までの取引数は概ね ln(2)/μ_log。μ_log = k·m − (k·s)²/2 は
k* = m/s²（ケリー基準）で最大となり、そのとき

    μ_log,max = m²/(2s²)

したがって**最短の到達取引数は ln(2)·2s²/m² = 2·ln(2)/(m/s)²**。
m/s（1取引あたりのシャープレシオ）だけで決まる。

**期限を満たすために必要な m/s を逆算できる。**
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}

# t値2.0以上の枠（PB GBPJPY / RSI GBPUSD / PB GOLD / SCA GOLD第1）
HIGH_T = {20260627, 20260774, 20260640, 20261002}


def deals(path, only=None):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        m = int(r["magic"])
        if p == 0.0 or m == 0:
            continue
        if only is not None and m not in only:
            continue
        out.append((int(r["time"]), p))
    out.sort()
    return out


def load(only=None):
    books, runs = {}, {}
    for f in ("results.csv", "results_grid.csv"):
        p = FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                runs[r["window"]] = FX / "run_deals" / r["deals"]
    for w, p in runs.items():
        books[("fx", w)] = deals(p, only)
    for r in csv.DictReader(open(GOLD / "results.csv", encoding="utf-8")):
        if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
            books[("gold", r["window"])] = deals(GOLD / "run_deals" / r["deals"], only)
    for w in ("OOS", "FULL"):
        if books.get(("fx", w)) and books.get(("gold", w)):
            books[("both", w)] = sorted(books[("fx", w)] + books[("gold", w)])
    return books


def sharpe(series):
    t = [p for _, p in series]
    n = len(t)
    if n < 2:
        return n, 0.0, 0.0, 0.0
    m = sum(t) / n
    v = sum((x - m) ** 2 for x in t) / (n - 1)
    s = math.sqrt(v)
    return n, m, s, (m / s if s else 0.0)


def ceiling(ruin_frac):
    """k→∞ での到達確率の天井。"""
    return (1 - ruin_frac) / (2 - ruin_frac)


def main():
    print("【1】倍率を上げたときの天井（k→∞ の理論値）")
    print(f"  {'破綻ライン':>10}{'天井':>10}   V006の実測（k=96）")
    obs = {0.10: 40.6}
    for rf in (0.05, 0.10, 0.20, 0.35, 0.50, 0.70):
        o = f"{obs[rf]:.1f}%" if rf in obs else ""
        print(f"  {100*rf:>9.0f}%{100*ceiling(rf):>9.1f}%   {o}")
    print("  → 倍率をいくら上げてもこの値を超えられない。")

    books = load()
    print("\n【2】1取引あたりのシャープレシオ（m/s）と、最短の到達期間")
    print("  最短到達取引数 = 2·ln(2)/(m/s)²  （ケリー基準 k*=m/s² のとき）")
    print(f"\n  {'ブック':<7}{'窓':>6}{'取引数':>7}{'m/s':>9}{'k*':>8}"
          f"{'最短取引数':>11}{'月/取引':>9}{'最短到達':>10}")
    CAP = 30000.0
    for key in (("fx", "IS"), ("fx", "OOS"), ("fx", "FULL"),
                ("gold", "OOS"), ("gold", "FULL"),
                ("both", "OOS"), ("both", "FULL")):
        if key not in books or not books[key]:
            continue
        n, m, s, sh = sharpe(books[key])
        if sh <= 0:
            continue
        per_month = n / MONTHS[key[1]]
        # 資金比に直す（deal は 0.01ロット固定。資金CAPに対する比）
        mf, sf = m / CAP, s / CAP
        kstar = mf / (sf ** 2)
        nmin = 2 * math.log(2) / (sh ** 2)
        print(f"  {key[0]:<7}{key[1]:>6}{n:>7}{sh:>9.4f}{kstar:>8.2f}"
              f"{nmin:>11,.0f}{per_month:>9.1f}{nmin/per_month:>9.1f}か月")

    print("\n【3】期限を満たすために必要なシャープレシオ")
    print("  必要 m/s = sqrt(2·ln(2)/必要取引数)")
    both = books.get(("both", "OOS"))
    if both:
        n, m, s, sh = sharpe(both)
        per_month = n / MONTHS["OOS"]
        print(f"\n  合算OOS の現状: m/s = {sh:.4f}（月{per_month:.1f}取引）")
        print(f"  {'期限':>8}{'必要取引数':>11}{'必要 m/s':>11}{'現状比':>9}")
        for lim in (1, 2, 3, 6, 12):
            need_n = per_month * lim
            need_sh = math.sqrt(2 * math.log(2) / need_n)
            print(f"  {lim:>6}か月{need_n:>11.0f}{need_sh:>11.4f}"
                  f"{need_sh/sh:>8.2f}倍")

    print("\n【4】t値2.0以上の枠だけに絞った場合")
    hb = load(only=HIGH_T)
    print(f"  {'ブック':<7}{'窓':>6}{'取引数':>7}{'m/s':>9}{'最短到達':>10}")
    for key in (("fx", "IS"), ("fx", "OOS"), ("fx", "FULL"),
                ("gold", "OOS"), ("gold", "FULL"),
                ("both", "OOS"), ("both", "FULL")):
        if key not in hb or not hb[key]:
            continue
        n, m, s, sh = sharpe(hb[key])
        if sh <= 0 or n < 10:
            continue
        per_month = n / MONTHS[key[1]]
        nmin = 2 * math.log(2) / (sh ** 2)
        print(f"  {key[0]:<7}{key[1]:>6}{n:>7}{sh:>9.4f}"
              f"{nmin/per_month:>9.1f}か月")
    print("  ※ 取引数が減るぶん、シャープが上がっても期間は短くならないことがある。")


if __name__ == "__main__":
    main()
