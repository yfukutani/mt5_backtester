"""ドテンで「入った側」の成績を見る（段階2・rsi_flip.py の続き）。

`rsi_flip.py` は「ドテンで**出た**側」が両窓で負けだと示した。しかしドテンをやめれば
**入った側の取引も消える**。入った側が儲かっているなら、差し引きで損になりうる。

ここでは、決済と同時刻に建った取引（＝ドテンで入った取引）だけを抜き出して成績を見る。
これも **採用の根拠にはならない**（段階2）。
"""
from __future__ import annotations

from collections import defaultdict

from trade_stats import load_trades, find_base_deals, window_of
from exit_mix import kind


def main():
    trades = load_trades(find_base_deals())
    by = defaultdict(list)
    for t in trades:
        by[t["sleeve"]].append(t)

    print(f"{'枠':<8}{'窓':<5}{'ドテンで入ったn':>14}{'ΣR':>8}{'平均R':>8}{'純益':>9}"
          f"   |{'ドテンで出たΣR':>14}{'差し引きΣR':>12}")
    tot = defaultdict(float)
    for name in ("RSI_UJ", "RSI_EU", "RSI_GU"):
        ts = by[name]
        exits_at = defaultdict(list)          # 決済時刻 -> ドテンで出た取引
        for t in ts:
            if kind(t) == "other":
                exits_at[t["t_out"]].append(t)
        for win in ("OOS", "IS"):
            ins, outs = [], []
            for t in ts:
                if window_of(t["t_in"]) != win:
                    continue
                for u in exits_at.get(t["t_in"], []):
                    if u["is_buy"] != t["is_buy"]:
                        ins.append(t)
                        break
                if kind(t) == "other":
                    outs.append(t)
            if not ins:
                continue
            sr_in = sum(t["r"] for t in ins if t["r"] is not None)
            sr_out = sum(t["r"] for t in outs if t["r"] is not None)
            # ドテンをやめると: 出た側は続行（rsi_flip.py の粗い期待値）・入った側は消える
            print(f"{name:<8}{win:<5}{len(ins):>14}{sr_in:>8.1f}"
                  f"{sr_in/len(ins):>8.3f}{sum(t['pnl'] for t in ins):>9,.0f}"
                  f"   |{sr_out:>14.1f}{'':>12}")
            tot[(win, "in")] += sr_in
            tot[(win, "out")] += sr_out
    print("\n合計:")
    for win in ("OOS", "IS"):
        print(f"  {win:<5}ドテンで入った側 ΣR={tot[(win,'in')]:>7.1f}   "
              f"ドテンで出た側 ΣR={tot[(win,'out')]:>7.1f}")


if __name__ == "__main__":
    main()
