"""案が「狙っていない枠」をどれだけ動かしたかを出す（第14報ラウンドの交絡の確認）。

【なぜ要るか】
このラウンドは**固定サイジング**なので、「PB の閾値を変えたら RSI の損益が動く」ことは
本来ありえない。ところが判定表では、Carry の退出を変えた Q019/Q020/Q021 が
**Carry枠では両窓とも改善しているのに、ブック全体では IS が大きく悪化**している。

考えられる筋はひとつ——**証拠金の取り合い**である。Carry の建玉が増えれば
（Q019 は取引 +20、Q021 は +33）その分の証拠金が先に押さえられ、
**他の枠の注文が通らなくなる。** この EA は cap を使っていなくても、
テスターの証拠金そのものが上限として効く。

もしそうなら、**ブック全体の差は「枠の改良の良し悪し」と「証拠金の押し合い」の合計**であり、
枠の改良を評価する数字としては使えない。ここで分けて出す。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SLEEVES = ["pb_uj", "pb_gj", "rsi_uj", "rsi_eu", "rsi_gu",
           "pair", "carry", "sca_uj", "sca_gj"]
LABEL = {"pb_uj": "PB UJ", "pb_gj": "PB GJ", "rsi_uj": "RSI UJ",
         "rsi_eu": "RSI EU", "rsi_gu": "RSI GU", "pair": "Pair",
         "carry": "Carry", "sca_uj": "SCA UJ", "sca_gj": "SCA GJ"}
TARGET = {
    "Q001": ["rsi_uj", "rsi_eu", "rsi_gu"], "Q002": ["rsi_uj", "rsi_eu", "rsi_gu"],
    "Q003": ["rsi_eu"], "Q004": ["rsi_uj", "rsi_gu"],
    "Q005": ["sca_uj", "sca_gj"], "Q006": ["sca_uj", "sca_gj"],
    "Q007": ["sca_uj", "sca_gj"], "Q008": ["sca_gj"],
    "Q009": ["sca_uj", "sca_gj"], "Q010": ["sca_uj", "sca_gj"],
    "Q011": ["pb_gj"], "Q012": ["pb_gj"], "Q013": ["pb_gj"], "Q014": ["pb_gj"],
    "Q015": ["pb_uj"], "Q016": ["pb_uj"],
    "Q017": ["sca_gj"], "Q018": ["sca_uj", "sca_gj"],
    "Q019": ["carry"], "Q020": ["carry"], "Q021": ["carry"],
}


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    res = ROOT / "results.csv"
    if not res.exists():
        sys.exit("results.csv が無い")
    rows = {(r["proposal_id"], r["window"]): r
            for r in csv.DictReader(open(res, encoding="utf-8"))
            if r.get("status") == "OK"}
    base = {w: rows.get(("Q000", w)) for w in ("OOS", "IS")}
    if not all(base.values()):
        sys.exit("対照 Q000 が揃っていない")

    print("# 狙った枠の改善 vs 狙っていない枠への漏れ\n")
    print("> 固定サイジングなので、狙っていない枠は本来ゼロのはず。"
          "ゼロでなければ**証拠金の押し合い**が起きている。\n")
    print("| 案 | 窓 | 狙った枠のΔ | **他枠へのΔ（漏れ）** | ブック全体のΔ | 漏れの最大の相手 |")
    print("|---|---|---:|---:|---:|---|")
    pids = sorted({p for (p, _) in rows} - {"Q000"})
    for p in pids:
        for w in ("OOS", "IS"):
            r, b = rows.get((p, w)), base[w]
            if not r:
                continue
            tgt = set(TARGET.get(p, []))
            d_t = sum(f(r[f"{s}_net"]) - f(b[f"{s}_net"]) for s in tgt)
            others = [(LABEL[s], f(r[f"{s}_net"]) - f(b[f"{s}_net"]))
                      for s in SLEEVES if s not in tgt]
            d_o = sum(v for _, v in others)
            worst = min(others, key=lambda x: x[1]) if others else ("—", 0.0)
            print(f"| {p} | {w} | {d_t:+,.0f} | **{d_o:+,.0f}** "
                  f"| {f(r['net'])-f(b['net']):+,.0f} "
                  f"| {worst[0]} {worst[1]:+,.0f} |")

    print("\n## 狙った枠だけで見た判定（証拠金の押し合いを除く）\n")
    print("| 案 | 狙った枠 | OOS Δ | IS Δ | 判定（枠単体） |")
    print("|---|---|---:|---:|---|")
    for p in pids:
        if not all(rows.get((p, w)) for w in ("OOS", "IS")):
            continue
        tgt = TARGET.get(p, [])
        d = {}
        for w in ("OOS", "IS"):
            r, b = rows[(p, w)], base[w]
            d[w] = sum(f(r[f"{s}_net"]) - f(b[f"{s}_net"]) for s in tgt)
        if d["OOS"] > 0 and d["IS"] > 0:
            v = "**両窓で改善**"
        elif d["OOS"] > 0 or d["IS"] > 0:
            v = "片窓のみ"
        else:
            v = "両窓で悪化"
        print(f"| {p} | {'+'.join(LABEL[s] for s in tgt)} "
              f"| {d['OOS']:+,.0f} | {d['IS']:+,.0f} | {v} |")


if __name__ == "__main__":
    main()
