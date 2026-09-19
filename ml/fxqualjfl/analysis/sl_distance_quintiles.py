# -*- coding: utf-8 -*-
"""枠ごとに「SL距離比 = |entry-sl|/entry」の分位で往復損益を割る。【複利の時間交絡を除いた版】

なぜ正規化が要るか:
  複利構成の deal ログの損益を単純に合計すると、**後半の取引が桁で支配する**。
  分位別の合計を並べても「その分位に後半の取引が多く入ったか」を見ているだけになりうる。
  そこで各往復を **entry時点の残高に対する比率（R = profit / balance_at_entry）** に
  直してから分位に割る。これなら「1回あたり何%動かしたか」の比較になる。

⚠️ **deal ログの `profit_jpy` 列は使わないこと。** 累積しても最終残高に合わない
  （OOS G000 で 109,684,856 になり、実際の 1,489,367 と合わない。JPY建て銘柄で
  二重に換算されている）。口座通貨は JPY なので `profit` がそのまま正しく、
  `ml/fxmargin3/measure.py` の枠別集計も `profit` を使っている。
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

MAGIC = {
    20260622: "pb_uj", 20260627: "pb_gj",
    20260610: "rsi_uj", 20260605: "rsi_eu", 20260774: "rsi_gu",
    20260629: "pair", 20260650: "carry",
    20261000: "sca_uj", 20261001: "sca_gj",
}
DEPOSIT = 500000.0
ORDER = ("pb_uj", "pb_gj", "rsi_uj", "rsi_eu", "rsi_gu",
         "pair", "carry", "sca_uj", "sca_gj")


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "time": int(r["time"]), "magic": int(r["magic"]),
                    "entry": r["entry"], "pid": r["position_id"],
                    "price": float(r["price"]), "sl": float(r["sl"]),
                    "volume": float(r["volume"]),
                    "pnl": float(r["profit"]),
                })
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda x: x["time"])

    # 残高の経路を時系列で作る（約定の発生順に積む）
    bal = DEPOSIT
    ins, bal_at_entry = {}, {}
    closed = defaultdict(float)
    for r in rows:
        if r["entry"] == "0":
            ins[r["pid"]] = r
            bal_at_entry[r["pid"]] = bal
        else:
            closed[r["pid"]] += r["pnl"]
        bal += r["pnl"]

    trades = []
    for pid, i in ins.items():
        if pid not in closed:
            continue
        name = MAGIC.get(i["magic"])
        if name is None:
            continue
        ratio = None
        if i["sl"] > 0 and i["price"] > 0:
            ratio = abs(i["price"] - i["sl"]) / i["price"]
        b = bal_at_entry[pid]
        trades.append((name, ratio, closed[pid], closed[pid] / b if b > 0 else 0.0,
                       i["volume"]))
    return trades


def cuts_of(vals):
    s = sorted(vals)
    n = len(s)
    return [s[max(0, min(n - 1, int(n * k / 5)))] for k in (1, 2, 3, 4)]


def report(path, label):
    bys = defaultdict(list)
    for name, ratio, pnl, r, vol in load(path):
        bys[name].append((ratio, pnl, r, vol))
    print(f"\n===== {label} ({Path(path).name}) =====")
    print("  R = 残高比の往復損益（%）。合計Rは単純和（複利の積ではない）")
    for name in ORDER:
        rows = bys.get(name, [])
        if not rows:
            print(f"{name:8s} 取引なし")
            continue
        withsl = [x for x in rows if x[0] is not None]
        nosl = len(rows) - len(withsl)
        if not withsl:
            print(f"{name:8s} n={len(rows):4d} SL無し{nosl} → この軸は存在しない")
            continue
        ratios = [x[0] for x in withsl]
        lo, hi = min(ratios), max(ratios)
        spread = hi / lo if lo > 0 else float("inf")
        cuts = cuts_of(ratios)

        def bucket(x):
            for k, c in enumerate(cuts):
                if x < c:
                    return k
            return 4

        agg = [[0.0, 0, 0.0, 0] for _ in range(5)]   # sumR, n, vol, wins
        for ratio, pnl, r, vol in withsl:
            b = bucket(ratio)
            agg[b][0] += r
            agg[b][1] += 1
            agg[b][2] += vol
            agg[b][3] += 1 if pnl > 0 else 0
        totR = sum(a[0] for a in agg) * 100
        print(f"{name:8s} n={len(withsl):4d} SL無し{nosl:3d} "
              f"比 {lo:.5f}〜{hi:.5f}（広がり {spread:.1f}倍） 合計R {totR:+.1f}%")
        if spread < 1.02:
            print("         → SL距離はほぼ定数。この軸は存在しない")
            continue
        for k in range(5):
            sR, n, vol, w = agg[k]
            edge = "最狭" if k == 0 else ("最広" if k == 4 else "")
            print(f"         Q{k+1}{edge:4s} n={n:4d} 合計R {sR*100:>+9.1f}% "
                  f"1回平均R {sR/n*100 if n else 0:>+7.3f}% "
                  f"勝率 {w/n*100 if n else 0:>5.1f}% 平均lot {vol/n if n else 0:>7.3f}")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        lbl, p = a.split("=", 1)
        report(p, lbl)
