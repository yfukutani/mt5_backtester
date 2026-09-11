"""複利前提の評価。非複利ラウンドとは指標の定義が根本的に違う。

【なぜ指標を変えるか】

非複利（固定ロット）では「純益 ÷ 入金 ÷ 月数」で月利を出し、DDは入金に対する
円建ての落ち込みで見てきた（docs/lot_multiplier_recheck_20260906.md）。
ロットが一定なので、この算術平均が実際の体感と一致する。

複利ではこれが成り立たない。

- 月利は**幾何平均**で見る必要がある。115か月で16倍になるのと、毎月一定額を
  積むのとでは、同じ「純益÷月数」でも意味がまったく違う。
- DDは**入金比ではなく直近ピーク比**で見る。資産が10倍に育った後の
  30%の落ち込みは、入金比では300%になってしまい解釈できない。
  MT5の「最大相対DD%」は残高基準なので、**複利ではむしろこちらが正しい**
  （非複利では残高が育つぶんリスクを過小評価するので使わなかった）。
- **口座破綻の有無が最重要**。複利はドローダウンも増幅する。過去に RefCap=0 の
  x8 で24取引で破綻した実測がある。破綻したrunを「純益が小さい案」として
  順位づけると致命的な誤りになる。

【資産曲線の作り方】deal ログの決済損益を時刻順に累積し、入金を足したものを
equity とする。建玉中の含み損益は含まないので、実際の最大DDはこれより深い。
つまり**ここで出るDDは下限**である。
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
DEPOSIT = 500000
MONTHS = {"FULL": 115.0, "OOS": 55.0, "IS": 60.0}
TARGET_MONTHLY = 5.0     # ユーザー指定の目標（%/月）


def equity_curve(path):
    """決済損益から equity 曲線を作る。建玉中の含み損は含まないのでDDは下限。"""
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])          # profit_jpy はJPY建てでは使えない
        if p == 0.0:
            continue                    # IN約定は損益0
        rows.append((int(r["time"]), p))
    rows.sort()
    eq = DEPOSIT
    peak = DEPOSIT
    worst_rel = 0.0          # ピーク比の最大落ち込み（複利ではこちらが正しい）
    worst_yen = 0.0          # 円建ての最大落ち込み（入金比の目安）
    min_eq = DEPOSIT
    for _, p in rows:
        eq += p
        min_eq = min(min_eq, eq)
        if eq > peak:
            peak = eq
        dd = peak - eq
        worst_yen = max(worst_yen, dd)
        if peak > 0:
            worst_rel = max(worst_rel, dd / peak)
    return eq, worst_rel, worst_yen, min_eq, len(rows)


def monthly_compound(final_eq, months):
    """幾何平均の月利（%）。元本割れは負の月利として返す。"""
    if final_eq <= 0 or months <= 0:
        return float("-inf")
    return (math.pow(final_eq / DEPOSIT, 1.0 / months) - 1.0) * 100.0


def main():
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["status"] == "OK" and r.get("deals")]
    by = defaultdict(dict)
    for r in rows:
        by[r["proposal_id"]][r["window"]] = r

    print(f"OANDA FX 9枠 / 入金 {DEPOSIT:,}円 / 目標 月利{TARGET_MONTHLY:.0f}%")
    print("複利は risk%枠の3つ（PB USDJPY / PB GBPJPY / Carry）にしか効かない。")
    print("残り6枠は固定ロット0.01。equityは決済損益のみで作るのでDDは下限。\n")

    recs = []
    for pid, w in sorted(by.items()):
        rec = {"pid": pid, "desc": w[list(w)[0]]["description"]}
        for win in ("FULL", "OOS"):
            if win not in w:
                continue
            r = w[win]
            eq, rel, yen, min_eq, n = equity_curve(DEAL_DIR / r["deals"])
            rec[win] = {
                "eq": eq, "mo": monthly_compound(eq, MONTHS[win]),
                "rel": 100 * rel, "yen": yen, "yen_pct": 100 * yen / DEPOSIT,
                "min_eq": min_eq, "n": n,
                "blown": str(r.get("blown", "")).lower() in ("true", "1"),
                "tester_dd": float(r["dd_pct"]) if r.get("dd_pct") else None,
            }
        recs.append(rec)

    base = next((x for x in recs if x["pid"] == "C001"), None)

    for win in ("FULL", "OOS"):
        avail = [x for x in recs if win in x]
        if not avail:
            continue
        print(f"{'='*104}\n{win}窓（{MONTHS[win]:.0f}か月・複利）\n{'='*104}")
        print(f"{'案':<6}{'最終資産':>13}{'月利(複利)':>11}{'最大DD':>9}"
              f"{'(円)':>11}{'最低資産':>12}{'取引':>7}{'破綻':>6}  設定")
        for x in sorted(avail, key=lambda y: -y[win]["mo"]):
            v = x[win]
            blow = "★" if (v["blown"] or v["min_eq"] < DEPOSIT * 0.2) else ""
            print(f"{x['pid']:<6}{v['eq']:>13,.0f}{v['mo']:>10.2f}%{v['rel']:>8.1f}%"
                  f"{v['yen']:>11,.0f}{v['min_eq']:>12,.0f}{v['n']:>7}{blow:>6}  "
                  f"{x['desc'][:44]}")
        print()

    # 目標到達の判定。破綻した案は候補にしない。
    print(f"{'='*104}\n月利{TARGET_MONTHLY:.0f}%に到達し、かつ破綻していない案\n{'='*104}")
    for win in ("FULL", "OOS"):
        ok = [x for x in recs if win in x
              and x[win]["mo"] >= TARGET_MONTHLY
              and not x[win]["blown"]
              and x[win]["min_eq"] >= DEPOSIT * 0.2]
        if not ok:
            best = max((x for x in recs if win in x),
                       key=lambda y: y[win]["mo"], default=None)
            if best:
                b = best[win]
                print(f"{win}: 到達なし。最良は {best['pid']} {b['mo']:.2f}%/月 "
                      f"（最大DD {b['rel']:.1f}% / 最低資産 {b['min_eq']:,.0f}円）"
                      f" {best['desc'][:44]}")
            continue
        for x in sorted(ok, key=lambda y: y[win]["rel"]):
            v = x[win]
            print(f"{win}: {x['pid']} {v['mo']:.2f}%/月 / 最大DD {v['rel']:.1f}% "
                  f"/ 最低資産 {v['min_eq']:,.0f}円  {x['desc'][:44]}")

    # 両窓で到達しているか。FULLだけならIS期間に依存している。
    print(f"\n{'='*104}\n両窓とも到達し破綻もない案（これが採用候補）\n{'='*104}")
    both = [x for x in recs
            if all(w in x and x[w]["mo"] >= TARGET_MONTHLY and not x[w]["blown"]
                   and x[w]["min_eq"] >= DEPOSIT * 0.2 for w in ("FULL", "OOS"))]
    if both:
        for x in sorted(both, key=lambda y: max(y["FULL"]["rel"], y["OOS"]["rel"])):
            print(f"  {x['pid']}  FULL {x['FULL']['mo']:.2f}%/月 (DD {x['FULL']['rel']:.1f}%) "
                  f"/ OOS {x['OOS']['mo']:.2f}%/月 (DD {x['OOS']['rel']:.1f}%)  {x['desc'][:44]}")
    else:
        print("  なし")

    if base and "FULL" in base:
        print(f"\n現行 C001: FULL {base['FULL']['mo']:.2f}%/月 "
              f"(最大DD {base['FULL']['rel']:.1f}%) / "
              f"OOS {base['OOS']['mo']:.2f}%/月 (最大DD {base['OOS']['rel']:.1f}%)"
              if "OOS" in base else "")

    print("\n注: equityは決済損益のみで構成。建玉中の含み損を含まないため、"
          "実際の最大DDはここで出た値より深い。")


if __name__ == "__main__":
    main()
