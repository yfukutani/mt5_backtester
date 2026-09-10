"""FX 9枠 と GOLDブック（GOLD2枠＋暗号3枠）を1口座にまとめた場合を評価する。

【なぜこれを見るか】前回の測定で最大の弱点は **FX OOS の t値 1.58**（優位が統計的に
確認できない）だった。t値 = 平均 ÷ (標準偏差/√n) なので、上げる道は2つある。

  1. 取引数 n を増やす      → t値は √n に比例
  2. 1取引あたりの分散を下げる

**枠を合算すると両方が同時に効く。** 取引数は単純に足し合わされ、
相関の低い枠を混ぜれば1取引あたりの分散は個々の枠より小さくなる（分散効果）。

【合算してよい根拠】どちらも同じXM端末・同じ入金50万・GlobalLotMult=1 で測っている。
枠が純粋に加算的である（枠を足しても既存枠の損益が動かない）ことは、
これまでのラウンドで繰り返し実測して確認済み。

【運用上の意味】XMは FXペア・GOLD・暗号のすべてを扱えるので、
14枠を1口座で回すことは実際に可能。現在はOANDA FXとXMに分かれている。
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
    """(時刻, 損益) の列。magic=0（期間終了時の強制決済）は除く。"""
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0 or int(r["magic"]) == 0:
            continue
        out.append((int(r["time"]), p))
    out.sort()
    return out


def load():
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
        books[("fx", w)] = ea_deals(p)
    for r in csv.DictReader(open(GOLD / "results.csv", encoding="utf-8")):
        if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
            books[("gold", r["window"])] = ea_deals(GOLD / "run_deals" / r["deals"])
    # 合算：時刻順にマージするだけ。枠は加算的なので損益はそのまま足せる。
    for w in ("OOS", "FULL"):
        if ("fx", w) in books and ("gold", w) in books:
            books[("both", w)] = sorted(books[("fx", w)] + books[("gold", w)])
    return books


def stats(series):
    t = [p for _, p in series]
    n = len(t)
    m = sum(t) / n
    v = sum((x - m) ** 2 for x in t) / (n - 1)
    sd = math.sqrt(v)
    se = sd / math.sqrt(n)
    return n, m, sd, se, (m / se if se else float("inf"))


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


def main():
    books = load()

    print("【t値の比較】合算で優位の確からしさが上がるか")
    print(f"  {'ブック':<8}{'窓':>6}{'取引数':>8}{'平均/取引':>11}"
          f"{'標準偏差':>10}{'標準誤差':>10}{'t値':>7}")
    for key in (("fx", "IS"), ("fx", "OOS"), ("fx", "FULL"),
                ("gold", "OOS"), ("gold", "FULL"),
                ("both", "OOS"), ("both", "FULL")):
        if key not in books:
            print(f"  {key[0]:<8}{key[1]:>6}  データなし")
            continue
        n, m, sd, se, tv = stats(books[key])
        mark = "  ← 合算" if key[0] == "both" else ""
        print(f"  {key[0]:<8}{key[1]:>6}{n:>8}{m:>11,.1f}{sd:>10,.0f}"
              f"{se:>10,.1f}{tv:>7.2f}{mark}")

    print("\n  t値2.0以上で「優位がゼロである可能性を否定できる」水準。")

    print(f"\n{'='*96}")
    print("合算ブックの2倍化確率（点推定 / −1SE）")
    print(f"{'='*96}")
    for rf in (0.35, 0.5, 0.7):
        base = (0 - math.log(rf)) / (math.log(2.0) - math.log(rf))
        print(f"\n破綻ライン＝初期の{100*rf:.0f}%（{100*(1-rf):.0f}%のDDに耐える）"
              f"/ 優位ゼロなら {100*base:.1f}%")
        wins = [w for w in ("OOS", "FULL") if ("both", w) in books]
        print(f"  {'k':>3}｜" + "".join(f"{'合算 '+w:^30}｜" for w in wins))
        print(f"  {'':>3}｜" + "".join(f"{'点推定':>9}{'−1SE':>9}{'月数':>10}｜"
                                      for _ in wins))
        for k in (2, 4, 8, 16):
            line = f"  {k:>3}｜"
            for w in wins:
                s = books[("both", w)]
                t = [p for _, p in s]
                _, _, _, se, _ = stats(s)
                h, r, med = simulate(t, k, rf)
                h2, _, _ = simulate([x - se for x in t], k, rf)
                mo = med / len(t) * MONTHS[w] if med else None
                line += (f"{100*h:>8.1f}%{'*' if h >= .85 else ' '}"
                         f"{100*h2:>7.1f}%{'*' if h2 >= .85 else ' '}"
                         f"{(f'{mo:.0f}' if mo else '—'):>10}｜")
            print(line)

    print("\n* は85%到達。点推定と−1SEの両方に * が付く条件が、"
          "推定誤差を織り込んでも目標を満たす。")


if __name__ == "__main__":
    main()
