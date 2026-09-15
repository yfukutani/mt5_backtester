"""24か月窓の実測を、採用の判定基準に当てて並べる。

【判定基準】
  ① **OOS窓の**月利の中央値が6%を超える
  ② **破綻する窓が無い**
**両方を満たしたときだけ「届いた」と書く。片方では書かない。**

> ⚠️ **①は「9窓の中央値」ではなく「OOS窓の中央値」で見る。**
> W4以降は重みを決めた IS（2021-06〜2026-06）を含む。**当てにいった期間である。**
> 9窓をまとめた中央値は IS窓に引き上げられるので、判定に使うと過学習を見逃す。
> 実際 X005 は 9窓の中央値 8.40% に対し、**OOS窓だけなら 4.82%** だった。
> このプロジェクトが `oanda_fx_cap_pathdep_20260915.md` で
> 「弱い側に偏った窓だけ見ると勝って見えていた」と撤回したのと同じ形の罠である。

【なぜ窓で見るか】
通期55か月の幾何平均は**標本1件**である。このプロジェクトは一度
`docs/oanda_fx_cap_pathdep_20260915.md` で、cap の利益増が
「期間を切ると4勝5敗＝経路依存」だったために結論を撤回している。
各窓を**新規50万円口座**として実測すれば、その物差しを実機で当てられる。

【窓の読み分け】
OOS窓は 2016.11.09〜2021.06.20。**W1〜W3 だけが完全にOOSに収まる。**
W4以降は重みを決めた IS を含むので**良く出て当然**である。
12か月刻みなので窓は重なっており、**9本は独立標本ではない**。
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500000.0
TARGET = 6.0
MONTHS = {"W1": 24.0, "W2": 24.0, "W3": 24.0, "W4": 24.0, "W5": 24.0,
          "W6": 24.0, "W7": 24.0, "W8": 24.0, "W9": 19.0, "OOS": 55.0}
OOS_ONLY = ("W1", "W2", "W3")
SPAN = {"W1": "2016-11〜2018-11", "W2": "2017-11〜2019-11", "W3": "2018-11〜2020-11",
        "W4": "2019-11〜2021-11", "W5": "2020-11〜2022-11", "W6": "2021-11〜2023-11",
        "W7": "2022-11〜2024-11", "W8": "2023-11〜2025-11", "W9": "2024-11〜2026-06",
        "OOS": "2016-11〜2021-06（通期）"}


def monthly(net, window):
    """幾何平均の月利（%）。窓の頭で入金50万円から始まる前提。"""
    final = DEPOSIT + net
    if final <= 0:
        return float("nan")          # 口座が飛んだ
    return (math.pow(final / DEPOSIT, 1.0 / MONTHS[window]) - 1.0) * 100.0


def main():
    res = ROOT / "results.csv"
    if not res.exists():
        sys.exit("results.csv がありません")
    rows = [r for r in csv.DictReader(open(res, encoding="utf-8"))]
    by = {}
    desc = {}
    for r in rows:
        by.setdefault(r["proposal_id"], {})[r["window"]] = r
        desc[r["proposal_id"]] = r["description"]

    order = [p for p in ("X005", "X002", "X001", "X006", "X000") if p in by]
    order += [p for p in sorted(by) if p not in order]

    for pid in order:
        w = by[pid]
        print(f"■ {pid}  {desc[pid][:70]}")
        hdr = "  %-4s %-20s %14s %9s %9s %8s %7s" % (
            "窓", "期間", "純益", "月利", "最大DD", "取引", "OOS")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        # 「元本割れ」（窓の終わりが入金を下回る）と
        # 「破綻」（equity が消える・DD 99%以上）は別物なので分けて数える。
        # 判定基準の②は**破綻**のほう。元本割れは併記して読み手に渡す。
        geos, ruin, under = [], [], []
        for win in ("W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9"):
            r = w.get(win)
            if not r or r.get("status") != "OK":
                continue
            net = float(r["net"])
            g = monthly(net, win)
            dd = float(r["dd_pct"])
            final = DEPOSIT + net
            is_ruin = (not math.isfinite(g)) or final <= 0 or dd >= 99.0
            is_under = final < DEPOSIT
            geos.append(g if math.isfinite(g) else -100.0)
            if is_ruin:
                ruin.append(win)
            if is_under:
                under.append(win)
            mark = "✓" if win in OOS_ONLY else ""
            flag = ("  ←破綻" if is_ruin else "  ←元本割れ" if is_under else "")
            print("  %-4s %-20s %14s %8.2f%% %8.2f%% %8s %7s%s" % (
                win, SPAN[win], format(round(net), ","), g, dd,
                r.get("trades", ""), mark, flag))
        if geos:
            med = statistics.median(geos)
            over = sum(1 for g in geos if g >= TARGET)
            oos_g = [monthly(float(w[x]["net"]), x) for x in OOS_ONLY
                     if x in w and w[x].get("status") == "OK"]
            print("  " + "-" * (len(hdr) - 2))
            print(f"  中央値 {med:.2f}%   最悪 {min(geos):.2f}%   "
                  f"{TARGET:.0f}%以上 {over}/{len(geos)}   "
                  f"破綻窓 {len(ruin)}" + (f" ({', '.join(ruin)})" if ruin else "")
                  + f"   元本割れ窓 {len(under)}"
                  + (f" ({', '.join(under)})" if under else ""))
            oos_med = statistics.median(oos_g) if oos_g else None
            if oos_g:
                print(f"  ★判定に使うのはこちら → OOS窓({len(oos_g)}本)のみ: "
                      f"中央値 {oos_med:.2f}%   最悪 {min(oos_g):.2f}%   "
                      f"{TARGET:.0f}%以上 {sum(1 for g in oos_g if g >= TARGET)}/{len(oos_g)}")
                is_g = [g for w, g in zip(
                    ("W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9"), geos)
                    if w not in OOS_ONLY]
                if is_g:
                    print(f"  （参考）IS を含む窓({len(is_g)}本): "
                          f"中央値 {statistics.median(is_g):.2f}%"
                          "  ← 重みを当てにいった期間。良く出て当然")
            if len(geos) < 9:
                verdict = f"測定中（{len(geos)}/9窓）"
            elif oos_med is None:
                verdict = "OOS窓が測れていない"
            elif oos_med >= TARGET and not ruin:
                verdict = "★ OOS窓の中央値が6%超・破綻窓なし — 両方を満たした"
            elif oos_med >= TARGET:
                verdict = f"× OOS中央値は6%超だが破綻窓が {len(ruin)} 本ある"
            elif not ruin:
                verdict = (f"× 破綻窓は無いが OOS窓の中央値 {oos_med:.2f}% が6%に届かない"
                           + (f"（元本割れ窓 {len(under)}本）" if under else ""))
            else:
                verdict = "× どちらも満たさない"
            print(f"  判定: {verdict}")
        if "OOS" in w and w["OOS"].get("status") == "OK":
            r = w["OOS"]
            print(f"  参考 通期OOS(55か月): 純益 {float(r['net']):,.0f}円 / "
                  f"月利 {monthly(float(r['net']), 'OOS'):.2f}% / "
                  f"DD {float(r['dd_pct']):.2f}% / {r.get('trades','')}取引")
        print()

    print("注: ✓ は完全にOOSに収まる窓。W4以降は重みを決めたISを含むので良く出て当然。")
    print("    12か月刻みで窓は重なっており、9本は独立標本ではない。")
    print("    判定は「中央値6%超」かつ「破綻窓なし」の両方。片方では『届いた』と書かない。")


if __name__ == "__main__":
    main()
