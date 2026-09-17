"""各枠の取引が「どう終わっているか」を分解する（段階2）。

R倍率を見ると、枠ごとに **終わり方の構成**がまるで違う。
- R ≈ -1        → SL で切られた
- R ≈ +rr（設計値）→ TP に届いた
- それ以外        → **設計にない終わり方**（時間切れ・強制決済・反対シグナルでのドテン）

「それ以外」が多い枠は、**設計した期待値で回っていない**。ここが改良の入口になりうる。

判定に使う設計RR:
    PB_UJ 2.0 / PB_GJ 4.0 / RSI_UJ 110/50=2.2 / RSI_EU 105/25=4.2 / RSI_GU 110/50=2.2
    SCA_UJ 2.0 / SCA_GJ 2.0

段階2の道具であり、**採用の根拠にはならない。**
"""
from __future__ import annotations

from collections import defaultdict

from trade_stats import load_trades, find_base_deals, window_of, median

RR = {"PB_UJ": 2.0, "PB_GJ": 4.0, "RSI_UJ": 2.2, "RSI_EU": 4.2,
      "RSI_GU": 2.2, "SCA_UJ": 2.0, "SCA_GJ": 2.0}
TOL = 0.12          # 設計値からのずれ（スリッページ・スプレッド分）


def kind(t):
    r = t["r"]
    if r is None:
        return "noSL"
    rr = RR.get(t["sleeve"])
    if r <= -1.0 + TOL:
        return "SL"
    if rr is not None and abs(r - rr) <= max(TOL, 0.06 * rr):
        return "TP"
    return "other"


def main():
    trades = load_trades(find_base_deals())
    print(f"{'枠':<8}{'窓':<5}{'取引':>6}  "
          f"{'SL%':>6}{'TP%':>6}{'他%':>6}   "
          f"{'SLのΣR':>9}{'TPのΣR':>9}{'他のΣR':>9}   {'他の平均R':>10}{'他の純益':>10}")
    for name in ("PB_UJ", "PB_GJ", "RSI_UJ", "RSI_EU", "RSI_GU", "SCA_UJ", "SCA_GJ"):
        for win in ("OOS", "IS"):
            sub = [t for t in trades
                   if t["sleeve"] == name and window_of(t["t_in"]) == win]
            if not sub:
                continue
            g = defaultdict(list)
            for t in sub:
                g[kind(t)].append(t)
            n = len(sub)
            def pct(k):
                return 100.0 * len(g[k]) / n
            def sr(k):
                return sum(t["r"] for t in g[k] if t["r"] is not None)
            oth = g["other"]
            om = (sum(t["r"] for t in oth) / len(oth)) if oth else float("nan")
            op = sum(t["pnl"] for t in oth)
            print(f"{name:<8}{win:<5}{n:>6}  "
                  f"{pct('SL'):>6.1f}{pct('TP'):>6.1f}{pct('other'):>6.1f}   "
                  f"{sr('SL'):>9.1f}{sr('TP'):>9.1f}{sr('other'):>9.1f}   "
                  f"{om:>10.3f}{op:>10,.0f}")

    # --- SCA の逆行ブーストを分離する ---------------------------------------
    # RevBoost はロットを倍にするだけで、R倍率には現れない。
    # ロットの大小で2群に分け、R と 円建て純益を別々に見る。
    print("\n=== SCA: ロットの大小で分けた成績（RevBoost の切り分け）===")
    for name in ("SCA_UJ", "SCA_GJ"):
        for win in ("OOS", "IS"):
            sub = [t for t in trades
                   if t["sleeve"] == name and window_of(t["t_in"]) == win]
            if not sub:
                continue
            vmin = min(t["vol"] for t in sub)
            small = [t for t in sub if t["vol"] <= vmin + 1e-9]
            big = [t for t in sub if t["vol"] > vmin + 1e-9]
            for lab, gg in (("素", small), ("ブースト", big)):
                if not gg:
                    continue
                rs = [t["r"] for t in gg if t["r"] is not None]
                print(f"  {name:<8}{win:<5}{lab:<6}"
                      f"n={len(gg):>5}  ロット={median([t['vol'] for t in gg]):.3f}  "
                      f"勝率={100.0*len([t for t in gg if t['pnl']>0])/len(gg):>5.1f}%  "
                      f"ΣR={sum(rs):>8.1f}  平均R={sum(rs)/max(1,len(rs)):>7.3f}  "
                      f"純益={sum(t['pnl'] for t in gg):>9,.0f}")


if __name__ == "__main__":
    main()
