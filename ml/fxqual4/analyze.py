"""ラウンドの判定表を作る（汎用）。引数でラウンドのディレクトリを渡す。

出す順番は判定に使う順番と同じにする:
  1. **回帰試験** — 対照が前ラウンドの対照と一致しているか
  2. **入力が届いたか** — 案が対照と完全同値なら「効かなかった」ではなく「届いていない」
  3. **損益・単利月利・残高DD・equity DD**（IS窓とOOS窓の両方・口座破綻の有無）
  4. **枠別の差** — ブック純益の差と枠の和が一致するか（第16報の恒等式）
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SLEEVES = [
    ("pb_uj", "PB USDJPY"), ("pb_gj", "PB GBPJPY"),
    ("rsi_uj", "RSI USDJPY"), ("rsi_eu", "RSI EURUSD"), ("rsi_gu", "RSI GBPUSD"),
    ("pair", "Pair EU/GU"), ("carry", "Carry AUDJPY"),
    ("sca_uj", "SCA USDJPY"), ("sca_gj", "SCA GBPJPY"),
]


def eq_dd(deals: str) -> str:
    p = Path(deals.replace("_deals.csv", "_cap.csv"))
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("equity_dd_pct"):
                return line.split(",")[5]
    except OSError:
        pass
    return "-"


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    rows = list(csv.DictReader((root / "results.csv").open(encoding="utf-8")))
    ids = []
    for r in rows:
        if r["proposal_id"] not in ids:
            ids.append(r["proposal_id"])
    ctrl_id = ids[0]
    by = {(r["proposal_id"], r["window"]): r for r in rows}

    print(f"# {root.name} — 判定\n")
    print(f"対照は {ctrl_id}。\n")

    print("## 1. 損益・単利月利・DD（IS窓とOOS窓の両方）\n")
    print("| 案 | 窓 | 純益 | Δ純益 | 単利月利 | 残高DD | equity DD | 取引 | 口座破綻 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for pid in ids:
        for w in ("OOS", "IS"):
            r = by.get((pid, w))
            if r is None:
                continue
            c = by.get((ctrl_id, w))
            d = float(r["net"]) - float(c["net"]) if c else 0.0
            bust = "なし" if float(r["final_balance"]) > 0 else "**あり**"
            print(f"| {pid} | {w} | {float(r['net']):+,.0f} | {d:+,.0f} | "
                  f"{float(r['monthly_pct']):.3f}% | {float(r['dd_pct']):.2f}% | "
                  f"{eq_dd(r['deals'])}% | {r['trades']} | {bust} |")

    print("\n## 2. 入力が EA に届いたか\n")
    print("> 案が対照と**完全に同じ数字**なら「効かなかった」ではなく"
          "**「入力が届いていない」**（MT5 は知らない入力を黙って無視する）。\n")
    print("| 案 | 窓 | Δ純益 | Δ取引 | 判定 |")
    print("|---|---|---:|---:|---|")
    for pid in ids[1:]:
        for w in ("OOS", "IS"):
            r, c = by.get((pid, w)), by.get((ctrl_id, w))
            if r is None or c is None:
                continue
            dn = float(r["net"]) - float(c["net"])
            dt = int(r["trades"]) - int(c["trades"])
            v = "**⚠️ 完全同値**" if dn == 0 and dt == 0 else "差が出ている"
            print(f"| {pid} | {w} | {dn:+,.0f} | {dt:+d} | {v} |")

    print("\n## 3. 枠別の差（対照比・円）\n")
    head = "| 案 | 窓 | " + " | ".join(n for _, n in SLEEVES) + " | 枠の和 | ブックΔ | 未配賦 |"
    print(head)
    print("|---|---|" + "---:|" * (len(SLEEVES) + 3))
    for pid in ids:
        for w in ("OOS", "IS"):
            r, c = by.get((pid, w)), by.get((ctrl_id, w))
            if r is None or c is None:
                continue
            ds = [int(r[f"{k}_net"]) - int(c[f"{k}_net"]) for k, _ in SLEEVES]
            tot = sum(ds)
            book = float(r["net"]) - float(c["net"])
            print(f"| {pid} | {w} | " + " | ".join(f"{d:+,}" for d in ds)
                  + f" | {tot:+,} | {book:+,.0f} | {tot - book:+,.0f} |")


if __name__ == "__main__":
    main()
