"""確認ラウンドの判定表（**幾何月利**で出す）。

【なぜ専用のスクリプトが要るか】
第3〜7ラウンドの `monthly_pct` は**単利**（純益 ÷ 初期資金 ÷ 月数）である。
固定ロットの構成ではそれで比較できるが、**目標（月利6%）は幾何・複利で定義されている**し、
本ラウンドは **R036 / R037 の複利構成**も測るので、**単利では並べられない。**

幾何月利 = (最終資産 / 初期資金) ** (1 / 月数) − 1

`docs/oanda_fx_risk_sizing_20260915.md` の R001「0.39%/月」も、
純益 119,537 / 初期 500,000 / 55か月 から
(1 + 0.2391) ** (1/55) − 1 = 0.39% として出ている（単利なら 0.435%）。
**本ラウンドの数字は、その系列と並べられる。**

【最優先の合否は口座破綻の有無】
`CLAUDE.md` の運用ルールどおり、**元本割れ（最終資産 < 初期資金）があれば
月利がいくら高くても不合格**として先に出す。
最大DD は残高ベースと equity ベースの両方を出す（第16報）。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

DEPOSIT = 500_000.0
MONTHS = {"OOS": 55.0, "IS": 60.0, "FULL": 115.0}


def geo(final: float, months: float) -> float:
    """幾何月利（%）。最終資産が0以下なら破綻としてNaN相当を返す。"""
    if final <= 0 or months <= 0:
        return float("nan")
    return ((final / DEPOSIT) ** (1.0 / months) - 1.0) * 100.0


def eq_dd(deals: str) -> str:
    p = Path(deals.replace("_deals.csv", "_cap.csv"))
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("equity_dd_pct"):
                return f"{float(line.split(',')[5]):.2f}"
    except (OSError, ValueError, IndexError):
        pass
    return "-"


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    rows = list(csv.DictReader((root / "results.csv").open(encoding="utf-8")))
    by = {(r["proposal_id"], r["window"]): r for r in rows}
    ids = []
    for r in rows:
        if r["proposal_id"] not in ids:
            ids.append(r["proposal_id"])

    print(f"# {root.name} — 判定（幾何月利）\n")
    print("| 案 | 窓 | 純益 | 最終資産 | **幾何月利** | 単利月利 | 残高DD | equityDD | 取引 | **口座破綻** |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for pid in ids:
        for w in ("OOS", "IS", "FULL"):
            r = by.get((pid, w))
            if r is None:
                continue
            final = float(r["final_balance"])
            m = MONTHS[w]
            bust = "**あり**" if final < DEPOSIT else "なし"
            print(f"| {pid} | {w} | {float(r['net']):+,.0f} | {final:,.0f} | "
                  f"**{geo(final, m):.3f}%** | {float(r['monthly_pct']):.3f}% | "
                  f"{float(r['dd_pct']):.2f}% | {eq_dd(r['deals'])}% | {r['trades']} | {bust} |")

    print("\n## 対照との差（幾何月利のポイント）\n")
    print("| 比較 | 窓 | 対照 | 候補 | **Δpt** | DD 対照→候補 |")
    print("|---|---|---:|---:|---:|---|")
    for ctrl, cand, label in (("F000", "F001", "本番現行・候補2件"),
                              ("F002", "F003", "R036（全複利・倍率1）・候補2件"),
                              ("F004", "F005", "R037（全複利・倍率2）・候補2件"),
                              ("F000", "F006", "本番現行・SCA UJ レンジ幅下限のみ"),
                              ("F000", "F007", "本番現行・候補3件")):
        for w in ("OOS", "IS", "FULL"):
            a, b = by.get((ctrl, w)), by.get((cand, w))
            if a is None or b is None:
                continue
            ga = geo(float(a["final_balance"]), MONTHS[w])
            gb = geo(float(b["final_balance"]), MONTHS[w])
            print(f"| {label} | {w} | {ga:.3f}% | {gb:.3f}% | **{gb - ga:+.3f}pt** | "
                  f"{float(a['dd_pct']):.2f}% → {float(b['dd_pct']):.2f}% |")


if __name__ == "__main__":
    main()
