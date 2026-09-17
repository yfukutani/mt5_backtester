"""Codex #23 の確認：Pair は「入口も退出も同時に成立している」領域で建てているか（段階2）。

`ProcPair()` の条件はこうなっている。

    参入  |z| >= entryZ (4.0)
    退出  保有中に z が exitZ(-1.0) 側へ戻る、または |z| >= stopZ (5.0)

**`entryZ < |z| < stopZ` の外側、つまり `|z| >= 5.0` でも参入する。**
建てた瞬間に退出条件（`stopZ`）も成立している注文がありうる。
Codex #23 は「その領域では建てない」という案である。

取引ログには z が記録されていないので、**価格系列から z を再計算**して、
建玉時刻の z を復元する。これは EA の計算と完全一致しないかもしれない
（バーの取り方・スプレッド）ので、**件数の桁を見るための道具**である。
**採用の根拠にはならない。**

z の定義（`ProcPair()` と同じ）:
    spread[k] = close_EURUSD[k] - close_GBPUSD[k]   （H1・k=1..200）
    z = (spread[0] - mean) / sd
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from trade_stats import load_trades, find_base_deals, window_of

REPO = Path(__file__).resolve().parents[2]
PAIR_MAGIC = 20260629
LB = 200
ENTRY_Z, EXIT_Z, STOP_Z = 4.0, -1.0, 5.0


def find_h1(sym):
    """H1終値の系列を探す。data/ 配下の CSV を使う。"""
    for pat in (f"data/{sym}_H1.csv", f"data/{sym}/H1.csv",
                f"data/*{sym}*H1*.csv"):
        for p in REPO.glob(pat):
            return p
    return None


def main():
    trades = [t for t in load_trades(find_base_deals())
              if t["sleeve"] == "PAIR"]
    print(f"Pair の取引: {len(trades)}件"
          f"（OOS {len([t for t in trades if window_of(t['t_in'])=='OOS'])} / "
          f"IS {len([t for t in trades if window_of(t['t_in'])=='IS'])}）")

    eu, gu = find_h1("EURUSD"), find_h1("GBPUSD")
    if not (eu and gu):
        print("\nH1の価格系列がリポジトリ内に見つからない。")
        print("→ z の復元はできない。**Codex #23 は MT5 側で計装するしかない。**")
        print("   `ProcPair()` に z と発注可否を CSV へ出す計装を足すのが最短。")
        print("\n代わりに、ログだけで分かることを出す:")
        by = defaultdict(list)
        for t in trades:
            y = datetime.fromtimestamp(t["t_in"], timezone.utc).year
            by[y].append(t)
        print(f"  {'年':<6}{'取引':>5}{'純益':>10}{'保有h中央':>10}")
        for y in sorted(by):
            g = by[y]
            hs = sorted(x["hold_h"] for x in g)
            print(f"  {y:<6}{len(g):>5}{sum(x['pnl'] for x in g):>10,.0f}"
                  f"{hs[len(hs)//2]:>10.1f}")
        # 両脚が同数・同時刻に建っているかの確認（中立性の健全性）
        pos = defaultdict(list)
        for t in trades:
            pos[t["t_in"]].append(t)
        pairs = [v for v in pos.values() if len(v) == 2]
        odd = [v for v in pos.values() if len(v) != 2]
        print(f"\n  同時刻に2件（両脚そろい）: {len(pairs)}組 / "
              f"そろっていない時刻: {len(odd)}件")
        if pairs:
            same = [v for v in pairs if v[0]["is_buy"] == v[1]["is_buy"]]
            print(f"  うち両脚が同方向（中立でない）: {len(same)}組")
            vols = [(v[0]["vol"], v[1]["vol"]) for v in pairs]
            uneq = [x for x in vols if abs(x[0] - x[1]) > 1e-9]
            print(f"  両脚のロットが違う組: {len(uneq)} / {len(vols)}")
        return

    print(f"H1系列: {eu.name} / {gu.name}")


if __name__ == "__main__":
    main()
