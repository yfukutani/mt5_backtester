"""SCA GBPJPY はいまの市場で負けている。その中身を割る（段階2）。

`by_year.py` の実測（本番現行サイジング・FULL窓）:

    SCA_GJ 純益  2022 +83,792 / 2023 +42,684 / 2024 +329 / 2025 -29,411 / 2026 -28,664
    SCA_GJ 平均R 2022 +0.189  / 2023 +0.050  / 2024 -0.088 / 2025 -0.060 / 2026 -0.074

**直近2.5年で -57,746円。** 累計 +115,992円の枠なので、**枠の質の劣化としては
ブック全体で最大の一件**である。サイジングの話ではない。

ここでは劣化の中身を、取引ログだけで割れる軸で分解する。

    1. ブースト（ドリフト逆行）か素か
    2. 買いか売りか
    3. レンジ幅（|建値-SL| / 建値）の大小 — `ScaFilRangeMin` が触っている軸
    4. 曜日

**採用の根拠にはならない**（段階2）。どの軸を MT5 で測るかを決めるために使う。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from trade_stats import load_trades, find_base_deals, median

PERIODS = (("2016-2021(OOS)", 2016, 2021),
           ("2022-2023(IS前半)", 2022, 2023),
           ("2024-2026(直近)", 2024, 2026))


def per(y):
    for lab, a, b in PERIODS:
        if a <= y <= b:
            return lab
    return None


def show(title, groups):
    print(f"\n--- {title} ---")
    print(f"{'区分':<18}{'期間':<18}{'n':>5}{'ΣR':>9}{'平均R':>9}{'勝率%':>8}{'純益':>10}")
    for key in groups:
        for lab, _, _ in PERIODS:
            g = groups[key].get(lab, [])
            if not g:
                continue
            rs = [t["r"] for t in g if t["r"] is not None]
            print(f"{str(key):<18}{lab:<18}{len(g):>5}{sum(rs):>9.1f}"
                  f"{sum(rs)/max(1, len(rs)):>9.3f}"
                  f"{100.0*len([t for t in g if t['pnl'] > 0])/len(g):>8.1f}"
                  f"{sum(t['pnl'] for t in g):>10,.0f}")


def main():
    trades = [t for t in load_trades(find_base_deals()) if t["sleeve"] == "SCA_GJ"]
    vmin = min(t["vol"] for t in trades)
    for t in trades:
        t["year"] = datetime.fromtimestamp(t["t_in"], timezone.utc).year
        t["per"] = per(t["year"])
        t["boost"] = t["vol"] > vmin + 1e-9
        t["width"] = abs(t["entry"] - t["sl"]) / t["entry"] if t["sl"] > 0 else None
        t["dow"] = datetime.fromtimestamp(t["t_in"], timezone.utc).strftime("%a")

    g = defaultdict(lambda: defaultdict(list))
    for t in trades:
        g["ブースト" if t["boost"] else "素"][t["per"]].append(t)
    show("1. ドリフト逆行（ブースト）か素か", g)

    g = defaultdict(lambda: defaultdict(list))
    for t in trades:
        g["買い" if t["is_buy"] else "売り"][t["per"]].append(t)
    show("2. 方向", g)

    # レンジ幅は全期間の三分位で切る（期間ごとに切ると比較できない）
    ws = sorted(t["width"] for t in trades if t["width"])
    q1, q2 = ws[len(ws) // 3], ws[2 * len(ws) // 3]
    g = defaultdict(lambda: defaultdict(list))
    for t in trades:
        if t["width"] is None:
            continue
        k = "幅 小" if t["width"] < q1 else ("幅 中" if t["width"] < q2 else "幅 大")
        g[k][t["per"]].append(t)
    show(f"3. レンジ幅 |建値-SL|/建値（三分位 {q1:.5f} / {q2:.5f}）", g)

    g = defaultdict(lambda: defaultdict(list))
    for t in trades:
        g[t["dow"]][t["per"]].append(t)
    show("4. 曜日", g)

    print("\n--- 参考: レンジ幅そのものの推移（中央値）---")
    byy = defaultdict(list)
    for t in trades:
        if t["width"]:
            byy[t["year"]].append(t["width"])
    for y in sorted(byy):
        print(f"  {y}  n={len(byy[y]):>4}  幅中央値={median(byy[y]):.5f}")


if __name__ == "__main__":
    main()
