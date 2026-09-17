"""全枠の「買い／売り」を3期間で割る（段階2）。

SCA_GJ の直近の負けが売り側に集中していることが分かった。
それが **GBPJPY の ORB 固有**なのか、**枠全体に共通する方向の非対称**なのかを見る。
枠ごとに共通なら「2022-2024 の円安トレンド」という1つの出来事の別表現に過ぎず、
方向ゲートは相場観の賭けになる。**採用の根拠にはならない。**
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from trade_stats import load_trades, find_base_deals
from sca_gj_decay import per, PERIODS

ORDER = ("PB_UJ", "PB_GJ", "RSI_UJ", "RSI_EU", "RSI_GU", "SCA_UJ", "SCA_GJ")


def main():
    ts = load_trades(find_base_deals())
    for name in ORDER:
        sub = [t for t in ts if t["sleeve"] == name]
        if not sub:
            continue
        g = defaultdict(list)
        for t in sub:
            y = datetime.fromtimestamp(t["t_in"], timezone.utc).year
            g[(per(y), t["is_buy"])].append(t)
        print(f"== {name}")
        for lab, _, _ in PERIODS:
            parts = []
            for is_buy, dname in ((True, "買"), (False, "売")):
                gg = g[(lab, is_buy)]
                if not gg:
                    parts.append(f"{dname}: —")
                    continue
                rs = [t["r"] for t in gg if t["r"] is not None]
                parts.append(f"{dname}: n={len(gg):>4} ΣR={sum(rs):>7.1f} "
                             f"平均R={sum(rs)/max(1, len(rs)):>7.3f} "
                             f"円={sum(t['pnl'] for t in gg):>9,.0f}")
            print(f"   {lab:<18}" + "   ".join(parts))


if __name__ == "__main__":
    main()
