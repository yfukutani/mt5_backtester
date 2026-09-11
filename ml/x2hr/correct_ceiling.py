"""V007の「47.4%は倍率によらない天井」という記述を検証し直す。

【Codexの指摘】記録自身の式 z = 1 − 2m/(k·s²) は k に依存する。
47.4% は k→∞ の極限であって、すべての k に共通する上限ではない。
ケリー値 k = m/s² を入れると z = −1 となり、破綻ライン10%での
無期限の上限先着確率は約94.7%になる。

【確認すべきこと】
1. 閉形式で k を振ったときの P の形（単調減少か）
2. V006 が k=8 から上しか振っていなかったのではないか
3. 期限を付けたときの最良の k と、そのときの P

【重要】V006 の「どの倍率でも48%前後」は**期限1か月という制約**による結果であり、
天井とは別の現象。低い k では期限内に2倍へ届かず「未達」になるため確率が下がり、
高い k では天井に張り付く。**両者を混同していた。**
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
CAPITAL = 30000.0
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
    for f in ("results.csv", "results_is.csv"):
        p = GOLD / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
                books[("gold", r["window"])] = ea_deals(GOLD / "run_deals" / r["deals"])
    for w in ("IS", "OOS", "FULL"):
        if ("fx", w) in books and ("gold", w) in books:
            books[("both", w)] = sorted(books[("fx", w)] + books[("gold", w)])
    return books


def closed_form(m, s, k, ruin_frac=0.10):
    """比例サイジング k のときの、無期限での上限先着確率（拡散近似）。"""
    a, b = math.log(ruin_frac), math.log(2.0)
    # 資金比の1取引あたり: μ_log ≈ k·m − (k·s)²/2, σ_log ≈ k·s
    mu = k * m - (k * s) ** 2 / 2.0
    sig = k * s
    if sig <= 0:
        return None
    z = -2.0 * mu / (sig ** 2)
    try:
        num = 1 - math.exp(z * a)
        den = math.exp(z * b) - math.exp(z * a)
        return num / den if den != 0 else None
    except OverflowError:
        return 1.0 if mu > 0 else 0.0


def simulate(trades, k, ruin_frac, horizon_steps, n_paths=20000, L=20,
             seed=20260912):
    rng = random.Random(seed)
    n = len(trades)
    hit = ruin = 0
    steps = []
    for _ in range(n_paths):
        eq = CAPITAL
        step = 0
        state = None
        while step < horizon_steps and state is None:
            start = rng.randrange(n)
            for j in range(L):
                if step >= horizon_steps:
                    break
                eq += trades[(start + j) % n] * k * (eq / CAPITAL)
                step += 1
                if eq <= CAPITAL * ruin_frac:
                    state = "ruin"; break
                if eq >= CAPITAL * 2.0:
                    state = "hit"; break
        if state == "hit":
            hit += 1; steps.append(step)
        elif state == "ruin":
            ruin += 1
    med = sorted(steps)[len(steps) // 2] if steps else None
    return hit / n_paths, ruin / n_paths, med


def main():
    books = load()
    print("【1】閉形式で k を振る（無期限・破綻ライン10%・合算OOS）")
    t = [p for _, p in books[("both", "OOS")]]
    n = len(t)
    mean = sum(t) / n
    var = sum((x - mean) ** 2 for x in t) / (n - 1)
    sd = math.sqrt(var)
    # 資金30,000円に対する1取引あたりの比率
    m_r = mean / CAPITAL
    s_r = sd / CAPITAL
    kelly = m_r / (s_r ** 2)
    print(f"  1取引あたり 平均 {mean:,.1f}円 / 標準偏差 {sd:,.0f}円")
    print(f"  資金比      平均 {m_r:.6f} / 標準偏差 {s_r:.6f} / ケリー k* = {kelly:.3f}")
    print(f"\n  {'k':>7}{'閉形式 P(2倍)':>16}")
    for k in (0.1, 0.2, kelly, 0.5, 1, 2, 4, 8, 16, 32, 96, 1000):
        p = closed_form(m_r, s_r, k)
        tag = "  ← ケリー" if abs(k - kelly) < 1e-9 else ""
        print(f"  {k:>7.3f}{(f'{100*p:.1f}%' if p is not None else '—'):>16}{tag}")
    print("  → k→∞ で 47.4% に収束するが、小さい k では 90%超。")
    print("     **47.4%は「すべての倍率の天井」ではなかった。V007の記述は誤り。**")

    print("\n【2】期限つきの実測（合算OOS・破綻ライン10%・月33.5取引）")
    per_month = n / MONTHS["OOS"]
    for limit in (1, 2, 6, 12, 24):
        hs = int(round(per_month * limit))
        print(f"\n  ■ 期限 {limit}か月（{hs}取引）")
        print(f"    {'k':>7}{'P(2倍)':>10}{'P(破綻)':>10}{'P(期限切れ)':>13}{'到達中央値':>12}")
        best = None
        for k in (0.25, 0.5, 1, 2, 4, 8, 16, 32):
            h, r, med = simulate(t, k, 0.10, hs)
            mo = med / per_month if med else None
            if best is None or h > best[1]:
                best = (k, h)
            print(f"    {k:>7.2f}{100*h:>9.1f}%{100*r:>9.1f}%{100*(1-h-r):>12.1f}%"
                  f"{(f'{mo:.2f}か月' if mo else '—'):>12}")
        print(f"    最良: k={best[0]} で {100*best[1]:.1f}%")


if __name__ == "__main__":
    main()
