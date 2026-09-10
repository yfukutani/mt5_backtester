"""EA由来のみで再計算し、モンテカルロを理論値で検証してから2倍化確率を出す。

【なぜ作り直すか】2つの問題が見つかった。

1. deal ログに `magic=0` の約定が混ざっている。正体は**テスト期間終了時の強制決済**
   （FULL窓では 2026-06-19 23:57 に3件、うち Carry AUDJPY の建玉が +53,233円）。
   テスト終了日にたまたま乗っていた含み益であり、戦略の実力ではない。
   期間を1日ずらせば消えるので、月利にも将来の経路にも含めてはいけない。
   これを含めた従来の報告は OOS で 27.8% 過大だった。

2. Codex版のモンテカルロと独立実装で確率が最大16ポイント乖離した。
   どちらが正しいか分からないので、**理論値で検証できる実装**を用意する。

【検証方法】ドリフト付きランダムウォークの「2倍到達 vs 破綻」には閉じた式がある。
比例サイジング（対数収益が i.i.d.）なら log(equity) が算術ブラウン運動になり、
上限 log(2)、下限 log(ruin_frac) の到達確率は

    P(上限が先) = (1 - e^(-2μa/σ²)) / (e^(-2μb/σ²) - e^(-2μa/σ²))

    ただし a = log(ruin_frac) < 0 < b = log(2)

で与えられる。合成データでこれを再現できれば実装は信用できる。
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
INIT = 500000.0

FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}


def ea_trades(path):
    """EA由来の決済損益のみ。magic=0（期間終了時の強制決済）は除く。"""
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])          # profit_jpy はJPY建てでは使えない
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


def simulate(trades, k, n_paths=20000, L=20, ruin_frac=0.2,
             max_horizon=3, seed=20260911):
    """比例サイジング。equity_next = equity + profit_x1*(equity/INIT)*k

    ブロック抽出は連敗の塊を保存するため。L=1 が独立仮定。
    """
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
    return hit / n_paths, ruin / n_paths, 1 - (hit + ruin) / n_paths, med


def theory(mu, sigma, ruin_frac=0.2):
    """log(equity) が算術ブラウン運動のときの、上限先着確率（閉形式）。"""
    a = math.log(ruin_frac)
    b = math.log(2.0)
    if abs(mu) < 1e-12:
        return (0 - a) / (b - a)
    z = -2.0 * mu / (sigma ** 2)
    return (1 - math.exp(z * a)) / (math.exp(z * b) - math.exp(z * a))


def validate():
    """合成データで理論値と突き合わせ、実装が正しいことを確かめる。"""
    print("【実装の検証】ドリフト付きランダムウォークの閉形式と突き合わせる")
    print(f"  {'μ/取引':>9}{'σ/取引':>9}{'理論値':>10}{'実装':>10}{'差':>8}")
    rng = random.Random(7)
    for mu, sigma in ((0.0005, 0.01), (0.001, 0.02), (0.002, 0.03), (0.0, 0.02)):
        # 対数収益 i.i.d. の系列を作り、それを x1 の円損益に見立てる。
        # equity += p*(eq/INIT)*k で k=1 のとき p = INIT*(e^r - 1) なら
        # equity *= e^r となり、log(equity) が算術ブラウン運動になる。
        series = [INIT * (math.exp(rng.gauss(mu, sigma)) - 1) for _ in range(4000)]
        h, r, u, _ = simulate(series, 1, n_paths=20000, L=1,
                              max_horizon=20, seed=1234)
        t = theory(mu, sigma)
        print(f"  {mu:>9.4f}{sigma:>9.3f}{100*t:>9.2f}%{100*h:>9.2f}%"
              f"{100*(h-t):>+7.2f}pt")
    print("  （差が1pt以内なら実装は信用してよい）\n")


def main():
    validate()
    books = load_books()

    print("【EA由来のみの純益】magic=0（期間終了時の強制決済）を除外")
    print(f"  {'ブック':<6}{'窓':>6}{'取引数':>8}{'EA由来純益':>13}"
          f"{'算術月利':>10}")
    for (b, w), t in sorted(books.items()):
        s = sum(t)
        print(f"  {b:<6}{w:>6}{len(t):>8}{s:>13,.0f}"
              f"{100*s/INIT/MONTHS[w]:>9.2f}%")

    KS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32)
    for b in ("fx", "gold"):
        wins = [w for w in ("IS", "OOS", "FULL") if (b, w) in books]
        if not wins:
            continue
        print(f"\n{'='*92}\n{b.upper()} — 破綻する前に2倍になる確率"
              f"（EA由来のみ / L=20 / 破綻=初期の20% / 最大3履歴 / 2万経路）\n{'='*92}")
        print(f"  {'k':>4}｜" + "".join(f"{w:^28}｜" for w in wins))
        print(f"  {'':>4}｜" + "".join(f"{'P(2倍)':>9}{'P(破綻)':>9}{'月数':>9}｜"
                                      for _ in wins))
        for k in KS:
            line = f"  {k:>4}｜"
            for w in wins:
                t = books[(b, w)]
                h, r, u, med = simulate(t, k)
                mo = med / len(t) * MONTHS[w] if med else None
                line += (f"{100*h:>8.1f}%{100*r:>8.1f}%"
                         f"{(f'{mo:.0f}' if mo else '—'):>9}｜")
            print(line)

    print(f"\n{'='*92}\n目標 P(2倍) >= 85% を満たす k\n{'='*92}")
    for b in ("fx", "gold"):
        for w in ("IS", "OOS", "FULL"):
            if (b, w) not in books:
                print(f"  {b}/{w}: データなし")
                continue
            t = books[(b, w)]
            ok = []
            for k in KS:
                h, r, u, med = simulate(t, k)
                if h >= 0.85:
                    ok.append((k, h, r, med))
            if ok:
                k, h, r, med = max(ok, key=lambda x: x[1])
                mo = med / len(t) * MONTHS[w]
                print(f"  {b}/{w}: k={[x[0] for x in ok]} が達成。"
                      f"最良 k={k} → P(2倍) {100*h:.1f}% / P(破綻) {100*r:.1f}% "
                      f"/ 所要 {mo:.0f}か月")
            else:
                best = max(((k,) + simulate(t, k)[:3] for k in KS),
                           key=lambda x: x[1])
                print(f"  {b}/{w}: 該当なし。最良 k={best[0]} → "
                      f"P(2倍) {100*best[1]:.1f}%")

    print("\n注1: この確率は「過去の優位が将来も続く」条件付き。"
          "ブートストラップは履歴より悪い相場を作れない。")
    print("注2: 最小ロット0.01の制約を無視しているため、"
          "実際の破綻確率はここで出た値より高い。")
    print("注3: 破綻＝初期資金の20%への到達。証拠金による強制ロスカットの再現ではない。")


if __name__ == "__main__":
    main()
