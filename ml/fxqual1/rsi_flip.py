"""RSI枠の「設計にない終わり方」の正体を特定する（段階2）。

`exit_mix.py` は RSI 3枠の「他」（SLでもTPでもない決済）が **両窓・3枠すべてで負け**
であることを示した。RSI枠を決済しうる経路は `ProcRSI()` の中で1つしかない——
反対シグナルが立ったときの `CloseType(i, 反対)` である（ドテン）。

ここではそれを取引ログで確かめる。「他」で終わった取引の決済時刻に、
**同じ枠・反対方向の建玉が立っているか**を見る。立っていればドテンである。

そのうえで「ドテンをやめたら得か」を素朴に見積もる。
現状のドテンは平均 -0.5R 前後で確定している。やめた場合の行き先は SL(-1R) か TP(+rr) の
どちらかで、ログからは分からない。**過去の TP到達率をそのまま当てはめた粗い期待値**を
併記する。これは **採用の根拠にはならない**（段階2）。MT5 で測るための優先度付けに使う。
"""
from __future__ import annotations

from collections import defaultdict

from trade_stats import load_trades, find_base_deals, window_of
from exit_mix import kind, RR


def main():
    trades = load_trades(find_base_deals())
    # 枠ごとに「建玉時刻 -> 方向」の索引を作る
    by_sleeve = defaultdict(list)
    for t in trades:
        by_sleeve[t["sleeve"]].append(t)

    print("=== RSI枠の『他』決済がドテンかどうか ===")
    for name in ("RSI_UJ", "RSI_EU", "RSI_GU"):
        ts = sorted(by_sleeve[name], key=lambda t: t["t_in"])
        entries = defaultdict(list)
        for t in ts:
            entries[t["t_in"]].append(t)
        for win in ("OOS", "IS"):
            sub = [t for t in ts if window_of(t["t_in"]) == win]
            others = [t for t in sub if kind(t) == "other"]
            flips = 0
            for t in others:
                # 決済時刻ちょうどに反対方向の建玉があればドテン
                for u in entries.get(t["t_out"], []):
                    if u["is_buy"] != t["is_buy"]:
                        flips += 1
                        break
            print(f"  {name:<8}{win:<5}他={len(others):>4}  "
                  f"うち同時刻に反対建玉あり={flips:>4}  "
                  f"({100.0*flips/max(1,len(others)):>5.1f}%)")

    print("\n=== ドテンをやめた場合の粗い期待値（段階2・採用根拠にしない）===")
    print(f"{'枠':<8}{'窓':<5}{'他n':>5}{'現状の平均R':>12}"
          f"{'TP到達率':>9}{'やめた場合の平均R':>18}{'差(ΣR)':>10}")
    for name in ("RSI_UJ", "RSI_EU", "RSI_GU"):
        ts = by_sleeve[name]
        for win in ("OOS", "IS"):
            sub = [t for t in ts if window_of(t["t_in"]) == win]
            others = [t for t in sub if kind(t) == "other"]
            decided = [t for t in sub if kind(t) in ("SL", "TP")]
            if not others or not decided:
                continue
            p_tp = len([t for t in decided if kind(t) == "TP"]) / len(decided)
            now = sum(t["r"] for t in others) / len(others)
            rr = RR[name]
            alt = p_tp * rr + (1 - p_tp) * (-1.0)
            print(f"{name:<8}{win:<5}{len(others):>5}{now:>12.3f}"
                  f"{100*p_tp:>9.1f}{alt:>18.3f}{(alt-now)*len(others):>10.1f}")


if __name__ == "__main__":
    main()
