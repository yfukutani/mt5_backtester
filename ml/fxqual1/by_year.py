"""枠 x 年の純益と平均R（段階2）。

「どの枠が**いまの市場**で効いているか」を見る。ユーザーの方針は
「利益 vs 頑健性のトレードオフでは現状市場(IS)の利益を優先」なので、
2024〜2026 の並びを特に見る。**採用の根拠にはならない。**
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from trade_stats import load_trades, find_base_deals

ORDER = ("PB_UJ", "PB_GJ", "RSI_UJ", "RSI_EU", "RSI_GU",
         "PAIR", "CARRY", "SCA_UJ", "SCA_GJ")


def main():
    trades = load_trades(find_base_deals())
    years = sorted({datetime.fromtimestamp(t["t_in"], timezone.utc).year
                    for t in trades})
    cell = defaultdict(list)
    for t in trades:
        y = datetime.fromtimestamp(t["t_in"], timezone.utc).year
        cell[(t["sleeve"], y)].append(t)

    print("=== 枠 x 年 純益（円・本番現行サイジング）===")
    print("枠      " + "".join(f"{y:>9}" for y in years) + f"{'合計':>10}")
    for name in ORDER:
        row = ""
        tot = 0.0
        for y in years:
            v = sum(t["pnl"] for t in cell[(name, y)])
            tot += v
            row += f"{v:>9,.0f}" if cell[(name, y)] else f"{'—':>9}"
        print(f"{name:<8}{row}{tot:>10,.0f}")

    print("\n=== 枠 x 年 平均R（SLのある枠のみ）===")
    print("枠      " + "".join(f"{y:>9}" for y in years))
    for name in ORDER:
        row = ""
        for y in years:
            rs = [t["r"] for t in cell[(name, y)] if t["r"] is not None]
            row += f"{sum(rs)/len(rs):>9.3f}" if rs else f"{'—':>9}"
        print(f"{name:<8}{row}")

    print("\n=== 枠 x 年 取引数 ===")
    print("枠      " + "".join(f"{y:>9}" for y in years))
    for name in ORDER:
        print(f"{name:<8}" + "".join(f"{len(cell[(name, y)]):>9}" for y in years))


if __name__ == "__main__":
    main()
