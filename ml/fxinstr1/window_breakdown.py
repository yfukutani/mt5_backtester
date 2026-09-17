# -*- coding: utf-8 -*-
"""W2/W3 が弱い理由を**枠別**に分解する（Claude 50案 #31・run 不要）。

第7報以降、判定は「OOS窓(W1/W2/W3)の月利中央値」である。W1 は 11〜12%/月 出るのに
W2/W3 は 4〜5%/月 で、**中央値を決めているのは常に W2 か W3** である。
どの枠が W1 で稼ぎ W2/W3 で稼げないのかを、既存の `results.csv` の枠別純益列から出す。

使い方: python ml/fxinstr1/window_breakdown.py [proposal_id]
既定は I000（X005＋cap90＝Y090）。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLS = [("pb_uj", "PB USDJPY"), ("pb_gj", "PB GBPJPY"), ("rsi_uj", "RSI USDJPY"),
        ("rsi_eu", "RSI EURUSD"), ("rsi_gu", "RSI GBPUSD"), ("pair", "PairTrade"),
        ("carry", "Carry AUDJPY"), ("sca_uj", "SCA USDJPY"), ("sca_gj", "SCA GBPJPY")]
ORDER = {"W1": 0, "W2": 1, "W3": 2, "OOS": 3}
DEPOSIT = 500_000.0


def main():
    pid = sys.argv[1] if len(sys.argv) > 1 else "I000"
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["proposal_id"] == pid]
    if not rows:
        print(f"{pid} の行が無い")
        return 1
    rows.sort(key=lambda r: ORDER.get(r["window"], 9))
    wins = [r["window"] for r in rows]

    print(f"# {pid} の枠別純益（円）")
    print("")
    print("| 枠 | " + " | ".join(wins) + " |")
    print("|---" * (len(wins) + 1) + "|")
    for c, n in COLS:
        vals = [int(float(r[c + "_net"])) for r in rows]
        print("| " + n + " | " + " | ".join(f"{v:,}" for v in vals) + " |")
    tot = [int(float(r["net"])) for r in rows]
    print("| **合計** | " + " | ".join(f"{v:,}" for v in tot) + " |")
    print("")
    print("| 枠 | " + " | ".join(w + " 取引" for w in wins) + " |")
    print("|---" * (len(wins) + 1) + "|")
    for c, n in COLS:
        vals = [int(float(r[c + "_n"])) for r in rows]
        print("| " + n + " | " + " | ".join(str(v) for v in vals) + " |")
    print("")
    print("| 窓 | 純益 | 最終残高 | **月利(幾何)** | 最大DD |")
    print("|---|---:|---:|---:|---:|")
    for r in rows:
        net = float(r["net"])
        months = 24.0 if r["window"] != "OOS" else 55.0
        final = DEPOSIT + net
        m = (final / DEPOSIT) ** (1.0 / months) - 1.0 if final > 0 else float("nan")
        print(f"| {r['window']} | {int(net):,} | {int(final):,} | "
              f"**{m*100:.2f}%** | {float(r['dd_pct']):.2f}% |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
