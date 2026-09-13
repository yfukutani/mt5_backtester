"""V100b：**RSI横展開4枠をV099の新基準で判定する**（2026-09-13）。

【判定は2段階】
1. **従来の運用ルール**：IS窓・OOS窓とも純益がプラスか
2. **V099の新基準**：**既存ブックが不毛な月に稼げるか**

1を満たさなくても2を満たせば価値がある可能性はあるが、
**明確な赤字枠は救えない。**

【限界】
- 4枠を同時に有効にした1本の実行なので、枠間の相殺が混ざる（枠別に分けて集計する）
- 設定はRSI GBPUSDのテンプレート流用。銘柄ごとの最適化はしていない（意図的）
- 既存ブックの不毛月は V099 と同じ定義（ブック全体の月次損益 ≤ 0）
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import dynamic_k_lag as dkl

WEAK = (datetime(2016, 11, 9, tzinfo=timezone.utc),
        datetime(2020, 1, 1, tzinfo=timezone.utc))
IS_W = (datetime(2021, 6, 21, tzinfo=timezone.utc),
        datetime(2026, 6, 21, tzinfo=timezone.utc))
NAMES = {20260790: "RSI GOLD", 20260791: "RSI AUDUSD",
         20260792: "RSI NZDUSD", 20260793: "RSI USDCAD"}


def months_of(a, b):
    out, d = [], datetime(a.year, a.month, 1, tzinfo=timezone.utc)
    while d < b:
        out.append((d.year, d.month))
        d = (datetime(d.year + 1, 1, 1, tzinfo=timezone.utc) if d.month == 12
             else datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc))
    return out


def book_monthly(a, b):
    """既存ブック（15枠）の月次損益。"""
    fx, gold = dkl.resolve_runs()
    ms = months_of(a, b)
    idx = {k: i for i, k in enumerate(ms)}
    v = np.zeros(len(ms))
    for window in ("OOS", "IS"):
        for src in (fx.get(window), gold.get(window)):
            if src is None:
                continue
            rows = []
            for r in csv.DictReader(open(src, encoding="utf-8")):
                if int(r["magic"]) == 0:
                    continue
                rows.append((int(r["time"]), int(r["entry"]),
                             int(r["position_id"]), float(r["profit"])))
            rows.sort()
            opened = {}
            for t, entry, pid, profit in rows:
                if entry == 0:
                    opened[pid] = t
                else:
                    t_in = opened.pop(pid, None)
                    if t_in is None or profit == 0.0:
                        continue
                    d = datetime.fromtimestamp(t_in, tz=timezone.utc)
                    if a <= d < b:
                        v[idx[(d.year, d.month)]] += profit
    return ms, v


def new_monthly(deal_path, a, b):
    ms = months_of(a, b)
    idx = {k: i for i, k in enumerate(ms)}
    out = defaultdict(lambda: np.zeros(len(ms)))
    cnt = defaultdict(int)
    rows = []
    for r in csv.DictReader(open(deal_path, encoding="utf-8")):
        m = int(r["magic"])
        if m not in NAMES:
            continue
        rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                     float(r["profit"]), m))
    rows.sort()
    opened = {}
    for t, entry, pid, profit, m in rows:
        if entry == 0:
            opened[pid] = (t, m)
        else:
            o = opened.pop(pid, None)
            if o is None or profit == 0.0:
                continue
            d = datetime.fromtimestamp(o[0], tz=timezone.utc)
            if a <= d < b:
                out[m][idx[(d.year, d.month)]] += profit
                cnt[m] += 1
    return out, cnt


def main():
    print("=" * 110)
    print("V100b：RSI横展開4枠をV099の新基準で判定する")
    print("=" * 110)
    res = list(csv.DictReader(open(ROOT / "results.csv", encoding="utf-8")))
    by_w = {r["window"]: r for r in res}

    print("\n【1. 従来の運用ルール】IS窓・OOS窓とも純益がプラスか")
    print("=" * 110)
    print(f"{'枠':<14}{'OOS 純益':>12}{'OOS 件数':>10}{'IS 純益':>12}"
          f"{'IS 件数':>9}{'全期間 純益':>13}{'月あたり':>10}{'判定':>7}")
    for key, name in (("gold", "RSI GOLD"), ("audusd", "RSI AUDUSD"),
                      ("nzdusd", "RSI NZDUSD"), ("usdcad", "RSI USDCAD")):
        o = float(by_w["OOS"].get(f"{key}_net") or 0)
        i = float(by_w["IS"].get(f"{key}_net") or 0)
        f = float(by_w["FULL"].get(f"{key}_net") or 0)
        on = int(by_w["OOS"].get(f"{key}_n") or 0)
        inn = int(by_w["IS"].get(f"{key}_n") or 0)
        ok = o > 0 and i > 0
        print(f"{name:<14}{o:>12,.0f}{on:>10}{i:>12,.0f}{inn:>9}"
              f"{f:>13,.0f}{f/115.0:>10,.0f}{'OK' if ok else 'NG':>7}")
    tot = float(by_w["FULL"].get("net") or 0)
    print(f"\n  4枠合計：全期間 {tot:+,.0f}円 / PF {by_w['FULL'].get('pf')} / "
          f"取引 {by_w['FULL'].get('trades')} / 月あたり {tot/115.0:+,.0f}円")

    # ---------- 2. 不毛月の判定 ----------
    print("\n" + "=" * 110)
    print("【2. V099の新基準】既存ブックが不毛な月に稼げるか")
    print("=" * 110)
    for label, (a, b), wkey in (("OOS 弱局面（2016-11〜2019-12）", WEAK, "OOS"),
                                ("IS窓（2021-06〜2026-06）", IS_W, "IS")):
        ms, book = book_monthly(a, b)
        barren = book <= 0
        deal = ROOT / "run_deals" / by_w[wkey]["deals"]
        if not deal.exists():
            print(f"  {label}: 決済ログがない")
            continue
        new, cnt = new_monthly(deal, a, b)
        print(f"\n--- {label} ---")
        print(f"  既存ブック：{len(ms)}ヶ月 / 純益 {book.sum():+,.0f}円 / "
              f"不毛な月 {int(barren.sum())}ヶ月（不毛月の合計 {book[barren].sum():+,.0f}円）")
        print(f"{'枠':<14}{'件数':>7}{'純益':>12}{'**不毛月の損益**':>18}"
              f"{'不毛月で正':>12}{'月次相関':>11}")
        for m, name in NAMES.items():
            v = new.get(m)
            if v is None:
                continue
            corr = (float(np.corrcoef(v, book)[0, 1])
                    if v.std() > 0 and book.std() > 0 else float("nan"))
            npos = int((v[barren] > 0).sum())
            print(f"{name:<14}{cnt[m]:>7}{v.sum():>12,.0f}"
                  f"{v[barren].sum():>18,.0f}{f'{npos}/{int(barren.sum())}':>12}"
                  f"{corr:>11.3f}")
        # 参考：既存のRSI2枠
        print("  （参考・V099）RSI GBPUSD 弱局面の不毛月 +6,475円 / "
              "RSI USDJPY +6,010円")

    print("\n" + "=" * 110)
    print("【限界】")
    print("=" * 110)
    print("  ・4枠を同時に有効にした実行。枠別に分けて集計しているが相殺は残る")
    print("  ・設定はRSI GBPUSDのテンプレート流用。銘柄ごとの最適化はしていない")
    print("  ・不毛月の定義はV099と同じ（既存ブックの月次損益 ≤ 0）")
    print("\n完了。")


if __name__ == "__main__":
    main()
