"""SCA枠：ドリフト逆行（RevBoost条件）が「ロットの話」ではなく
「シグナルの質の話」なのかを確かめる（段階2）。

`ProcSCA()` の RevBoost は、ブレイク方向がその日のドリフトと**逆**のときロットを倍にする。
ロット倍率は R倍率に現れないので、両者を分けて見ると **条件そのものの質**が見える。

`exit_mix.py` で見えたこと（FULL窓を OOS/IS に割った値）:

    SCA_GJ OOS  素 平均R -0.067(n=462)   ブースト 平均R +0.129(n=159)
    SCA_GJ IS   素 平均R +0.005(n=522)   ブースト 平均R +0.065(n=162)
    SCA_UJ OOS  素 平均R +0.004(n=210)   ブースト 平均R -0.132(n= 56)
    SCA_UJ IS   素 平均R +0.026(n=258)   ブースト 平均R +0.028(n= 70)

SCA_GJ では両窓とも「ブースト側だけが良い」。SCA_UJ では一致しない。
ここでは **年ごとに割って**、それが一貫した構造なのか特定の年の産物なのかを見る。

併せて **決済時刻の分布**も出す。SCA の 60〜77% は SL でも TP でもなく
強制決済（22時）で終わっており、**利益はそこから出ている**。強制決済の時刻は
枠の質を決める主要パラメータのはずだが、一度も掃引していない。

段階2の道具であり、**採用の根拠にはならない。**
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from trade_stats import load_trades, find_base_deals, window_of


def main():
    trades = load_trades(find_base_deals())
    sca = [t for t in trades if t["sleeve"].startswith("SCA")]

    print("=== 年ごと: 素 vs ブースト（平均R・取引数）===")
    for name in ("SCA_UJ", "SCA_GJ"):
        ts = [t for t in sca if t["sleeve"] == name]
        vmin = min(t["vol"] for t in ts)
        rows = defaultdict(lambda: defaultdict(list))
        for t in ts:
            y = datetime.fromtimestamp(t["t_in"], timezone.utc).year
            lab = "素" if t["vol"] <= vmin + 1e-9 else "ブースト"
            rows[y][lab].append(t)
        print(f"\n  {name}")
        print(f"    {'年':<6}{'窓':<5}{'素n':>5}{'素平均R':>9}{'ブーストn':>9}{'ブースト平均R':>13}")
        for y in sorted(rows):
            g = rows[y]
            any_t = (g["素"] + g["ブースト"])[0]
            win = window_of(any_t["t_in"]) or "-"
            def mr(lab):
                rs = [t["r"] for t in g[lab] if t["r"] is not None]
                return sum(rs) / len(rs) if rs else float("nan")
            print(f"    {y:<6}{win:<5}{len(g['素']):>5}{mr('素'):>9.3f}"
                  f"{len(g['ブースト']):>9}{mr('ブースト'):>13.3f}")

    print("\n=== 決済時刻の分布（サーバー時刻・強制決済は22時）===")
    for name in ("SCA_UJ", "SCA_GJ"):
        for win in ("OOS", "IS"):
            ts = [t for t in sca if t["sleeve"] == name
                  and window_of(t["t_in"]) == win]
            if not ts:
                continue
            g = defaultdict(list)
            for t in ts:
                g[datetime.fromtimestamp(t["t_out"], timezone.utc).hour].append(t)
            print(f"\n  {name} {win}  (n={len(ts)})")
            print(f"    {'決済時':>6}{'n':>6}{'ΣR':>9}{'平均R':>9}{'純益':>9}")
            for h in sorted(g):
                gg = g[h]
                rs = [t["r"] for t in gg if t["r"] is not None]
                print(f"    {h:>6}{len(gg):>6}{sum(rs):>9.1f}"
                      f"{sum(rs)/max(1,len(rs)):>9.3f}"
                      f"{sum(t['pnl'] for t in gg):>9,.0f}")


if __name__ == "__main__":
    main()
