"""OANDA FX 9枠・入金50万円での想定成績を、現行と推奨設定で並べる。

【指標の定義】
- 月利: 純益 ÷ 入金 ÷ 月数。**非複利**（固定ロット＋固定RefCapなので複利にならない）。
- 最大DD: 決済損益の累積曲線のピークからの最大落ち込み（**円建て**）。
  MT5の最大相対DD%は残高基準で、利益が増えると同じ落ち込みでも%が小さく出るため使わない
  （docs/lot_multiplier_recheck_20260906.md）。
- RF（リカバリーファクター）: 純益 ÷ 最大DD。**大きいほど、同じ痛みで多く稼げる。**
  倍率を上げても純益とDDが同じ比率で増えるならRFは変わらない。RFが上がるのは
  枠の組み合わせが改善したときだけなので、倍率と重みの効果を切り分けられる。

【窓の読み方】OOSはパラメータ選択に使っていない期間なので、実運用の期待値に最も近い。
ISは選択に使ったぶん楽観的に出る。FULLは両方を含む。
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500000
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}


def curve(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])          # profit_jpy はJPY建てでは使えない
        if p == 0.0:
            continue
        rows.append((int(r["time"]), p))
    rows.sort()
    peak = cum = worst = 0.0
    for _, p in rows:
        cum += p
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return cum, worst, len(rows)


def load(*csvs):
    out = {}
    for path, keyfn in csvs:
        if not path.exists():
            continue
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r["status"] == "OK" and r.get("deals"):
                out[keyfn(r)] = (path.parent / "run_deals" / r["deals"], r)
    return out


def main():
    fxm = ROOT.parent / "fxmult1"
    runs = load(
        (fxm / "results.csv", lambda r: ("mult", r["window"], int(r["mult"]))),
        (fxm / "results_grid.csv", lambda r: ("mult", r["window"], int(r["mult"]))),
        (ROOT / "results.csv", lambda r: ("w", r["window"], r["proposal_id"])),
    )

    # 現行＝全重み1・倍率1。推奨＝SCA GBPJPYとCarryの重み0.5＋倍率引き上げ。
    PLANS = [
        ("現行（倍率1・全重み1）", [("w", "IS", "W001"), ("w", "OOS", "W001")]),
        ("推奨A DD予算20%（重み0.5/0.5・倍率3）",
         [("w", "IS", "W042"), ("w", "OOS", "W042")]),
        ("推奨B DD予算25%（重み0.5/0.5・倍率4）",
         [("w", "IS", "W043"), ("w", "OOS", "W043")]),
        ("推奨C DD予算30%（重み0.5/0.5・倍率5）",
         [("w", "IS", "W044"), ("w", "OOS", "W044")]),
        ("推奨D DD予算35%（重み0.5/0.5・倍率6）",
         [("w", "IS", "W045"), ("w", "OOS", "W045")]),
        ("参考: 重みそのまま・倍率3", [("w", "IS", "W003"), ("w", "OOS", "W003")]),
        ("参考: 重みそのまま・倍率4", [("w", "IS", "W004"), ("w", "OOS", "W004")]),
    ]

    print(f"OANDA FX 9枠 / 入金 {DEPOSIT:,}円 / 非複利 / RefCap=78,000（本番と同じ）")
    print("XM端末・XM銘柄での実測。本番はOANDAなので投入前に再測定が要る。\n")
    print(f"{'構成':<34}{'窓':>5}{'純益':>11}{'月利':>8}{'最大DD':>10}"
          f"{'入金比':>8}{'RF':>7}{'取引':>7}")
    for name, keys in PLANS:
        for k in keys:
            if k not in runs:
                continue
            deals, row = runs[k]
            if not deals.exists():
                continue
            net, dd, n = curve(deals)
            win = k[1]
            mo = 100 * net / DEPOSIT / MONTHS[win]
            rf = net / dd if dd > 0 else float("inf")
            print(f"{name if k is keys[0] else '':<34}{win:>5}{net:>11,.0f}"
                  f"{mo:>7.2f}%{dd:>10,.0f}{100*dd/DEPOSIT:>7.1f}%{rf:>7.2f}{n:>7}")
        print()


if __name__ == "__main__":
    main()
