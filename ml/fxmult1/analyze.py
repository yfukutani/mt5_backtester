"""OANDA FX 9枠の倍率余力を、円建てDDで評価する。

【x1のスケーリングが使えない】XM側（ml/mult1）は全枠固定ロットで円建て損益が倍率に
厳密比例した（実測ずれ0.0%）ので x1 の deal ログを n 倍すれば足りた。
FX側は PB USDJPY / PB GBPJPY / Carry が risk sizing で、RefCap=78000 に対する
リスク額からロットを出し、そこにロットステップの丸めが入る。x1 では丸めで落ちる割合が
大きく、倍率を上げるほど相対的な取りこぼしが減るため **超線形**になる
（実測: IS x4 で +15.3% / x8 で +17.2% / OOS x4 で +7.5%）。

したがって倍率ごとに実測が要る。ここでは測れている倍率だけを並べ、
間は内挿せずに「測った点」として示す。

【なぜ%ではなく円で見るか】MT5の最大相対DD%は残高基準なので、残高が増えると
同じ落ち込みでも%が小さく出る（docs/lot_multiplier_recheck_20260906.md）。
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
DEPOSIT = 500000
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}

NAMES = {
    "pb_uj": "PB USDJPY", "pb_gj": "PB GBPJPY", "rsi_uj": "RSI USDJPY",
    "rsi_eu": "RSI EURUSD", "rsi_gu": "RSI GBPUSD", "pair": "Pair",
    "carry": "Carry AUDJPY", "sca_uj": "SCA USDJPY", "sca_gj": "SCA GBPJPY",
}


def curve(path):
    """決済損益の時系列から、円建ての最大落ち込みと最終純益、その期間を返す。"""
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])          # profit_jpy はJPY建てでは使えない
        if p == 0.0:
            continue                    # IN約定は損益0
        rows.append((datetime.fromtimestamp(int(r["time"]), timezone.utc),
                     int(r["magic"]), p))
    rows.sort()
    peak = cum = worst = 0.0
    peak_at = rows[0][0] if rows else None
    span = None
    for t, _, p in rows:
        cum += p
        if cum > peak:
            peak, peak_at = cum, t
        if peak - cum > worst:
            worst, span = peak - cum, (peak_at, t)
    return cum, worst, span, rows


def main():
    res = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
           if r["status"] == "OK" and r["deals"]]
    by = defaultdict(dict)
    for r in res:
        by[r["window"]][int(r["mult"])] = r

    print(f"OANDA FX 9枠 / 入金{DEPOSIT:,}円 / RefCap=78,000（本番と同じ固定配分）")
    print("倍率ごとに実測。ロット丸めのため x1 のスケーリングは使えない。\n")

    for win in ("FULL", "OOS", "IS"):
        if win not in by:
            continue
        print(f"{'='*78}\n{win}窓（{MONTHS[win]:.0f}か月）\n{'='*78}")
        print(f"  {'倍率':>4}{'純益':>12}{'月利':>8}{'円建てDD':>12}{'入金比':>8}"
              f"{'相対DD%':>9}{'取引':>7}")
        base_m = None
        for mult in sorted(by[win]):
            r = by[win][mult]
            net, dd, _span, _ = curve(DEAL_DIR / r["deals"])
            mo = 100 * net / DEPOSIT / MONTHS[win]
            if mult == 1:
                base_m = mo
            print(f"  x{mult:<3}{net:>12,.0f}{mo:>7.2f}%{dd:>12,.0f}"
                  f"{100*dd/DEPOSIT:>7.1f}%{float(r['dd_pct']):>8.2f}%"
                  f"{int(r['trades']):>7}")
        if base_m is not None:
            print(f"\n  現行(x1)からの月利の伸び:")
            for mult in sorted(by[win]):
                if mult == 1:
                    continue
                r = by[win][mult]
                net, dd, _s, _ = curve(DEAL_DIR / r["deals"])
                mo = 100 * net / DEPOSIT / MONTHS[win]
                print(f"    x{mult}: {mo - base_m:+.2f}ポイント"
                      f"（DDは入金の {100*dd/DEPOSIT:.1f}%）")

    # 最悪の落ち込みを枠別に分解。倍率余力が特定の枠に縛られていないかを見る。
    print(f"\n{'='*78}\n最悪落ち込みの枠別内訳（FULL窓・x1）\n{'='*78}")
    if "FULL" in by and 1 in by["FULL"]:
        net, dd, span, rows = curve(DEAL_DIR / by["FULL"][1]["deals"])
        a, b = span
        print(f"  {dd:,.0f}円（入金の {100*dd/DEPOSIT:.1f}%） "
              f"{a:%Y-%m-%d}〜{b:%Y-%m-%d}（{(b-a).days}日）")
        MAG = {20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
               20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
               20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj"}
        seg = defaultdict(lambda: [0.0, 0])
        for t, m, p in rows:
            if a < t <= b and m in MAG:
                seg[MAG[m]][0] += p
                seg[MAG[m]][1] += 1
        loss = sum(v[0] for v in seg.values() if v[0] < 0)
        print(f"\n  {'枠':<16}{'落ち込み期間の損益':>18}{'決済数':>8}{'寄与率':>8}")
        for k, (v, n) in sorted(seg.items(), key=lambda kv: kv[1][0]):
            share = f"{100*v/loss:.0f}%" if v < 0 and loss else "—"
            print(f"  {NAMES[k]:<16}{v:>18,.0f}{n:>8}{share:>8}")


if __name__ == "__main__":
    main()
