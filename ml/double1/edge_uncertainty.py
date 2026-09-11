"""推定した優位（1取引あたりの期待損益）が、統計的にどれだけ確からしいかを見る。

【なぜこれが要るか】ブートストラップは履歴の**標本平均をそのまま真の優位**として
将来に当てはめる。標本平均の推定誤差は経路に反映されない。

実際、合成データでの検証中にこれが露呈した。母平均 μ=0 の系列を4000本引いて
ブートストラップしたところ、理論値 69.9% に対し 93.1% が出た。
原因は実装の誤りではなく、**その4000本の標本平均がたまたま +0.0003 だった**こと。
z = -2μ/σ² で計算し直すと理論値も 94% になり、実装と一致する。

つまり「破綻する前に2倍になる確率」は、**優位の推定誤差に対して極めて敏感**である。
優位が統計的に確認できない水準なら、確率の数字自体に意味がない。

ここでは各ブックについて
  ・1取引あたりの平均損益と、その標準誤差
  ・t値（平均 ÷ 標準誤差）
  ・優位がゼロだと仮定したときの到達確率（＝コイン投げの場合の下限）
を出す。
"""
from __future__ import annotations

import csv
import math
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
        if p == 0.0 or int(r["magic"]) == 0:
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


def theory(mu, sigma, ruin_frac=0.2):
    """log(equity) が算術ブラウン運動のときの上限先着確率。"""
    a, b = math.log(ruin_frac), math.log(2.0)
    if abs(mu) < 1e-15:
        return (0 - a) / (b - a)
    z = -2.0 * mu / (sigma ** 2)
    # オーバーフロー回避のため対数域で処理
    try:
        return (1 - math.exp(z * a)) / (math.exp(z * b) - math.exp(z * a))
    except OverflowError:
        return 1.0 if mu > 0 else 0.0


def main():
    books = load_books()
    print("1取引あたりの優位と、その推定誤差（EA由来のみ・x1）")
    print(f"  {'ブック':<6}{'窓':>6}{'取引数':>7}{'平均/取引':>11}{'標準偏差':>11}"
          f"{'標準誤差':>10}{'t値':>7}{'年あたり':>10}")
    rows = {}
    for (b, w), t in sorted(books.items()):
        n = len(t)
        mean = sum(t) / n
        var = sum((x - mean) ** 2 for x in t) / (n - 1)
        sd = math.sqrt(var)
        se = sd / math.sqrt(n)
        tval = mean / se if se > 0 else float("inf")
        per_year = n / (MONTHS[w] / 12.0)
        rows[(b, w)] = (n, mean, sd, se, tval)
        print(f"  {b:<6}{w:>6}{n:>7}{mean:>11,.1f}{sd:>11,.0f}{se:>10,.1f}"
              f"{tval:>7.2f}{per_year:>10.0f}")

    print("\n  t値の目安: 2.0未満は「優位がゼロである可能性を否定できない」。")
    print("  1取引あたりの平均が標準誤差に埋もれていれば、確率の数字は当てにならない。")

    print(f"\n{'='*96}")
    print("優位の推定誤差を確率に反映するとどうなるか（k=8・破綻=初期の20%）")
    print(f"{'='*96}")
    print(f"  {'ブック':<6}{'窓':>6}｜{'点推定':>10}{'−1SE':>10}{'−2SE':>10}"
          f"{'優位ゼロ':>10}｜  解釈")
    for (b, w), (n, mean, sd, se, tval) in sorted(rows.items()):
        k = 8
        # 1取引の対数収益に換算（比例サイジング k 倍）
        mu = mean * k / INIT
        sig = sd * k / INIT
        p0 = theory(mu, sig)
        p1 = theory((mean - se) * k / INIT, sig)
        p2 = theory((mean - 2 * se) * k / INIT, sig)
        pz = theory(0.0, sig)
        note = "優位が確認できない" if tval < 2.0 else "優位あり"
        print(f"  {b:<6}{w:>6}｜{100*p0:>9.1f}%{100*p1:>9.1f}%{100*p2:>9.1f}%"
              f"{100*pz:>9.1f}%｜  {note}")

    print("\n  「優位ゼロ」列は、期待値がゼロのゲームで初期資金の20%まで耐えた場合の")
    print("  到達確率。損益に優位が無くても、破綻ラインが遠ければこの程度は到達する。")
    print("  点推定がこれを大きく超えていなければ、勝っているのは優位ではなく")
    print("  「破綻ラインの遠さ」である。")


if __name__ == "__main__":
    main()
