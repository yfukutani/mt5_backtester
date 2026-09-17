# -*- coding: utf-8 -*-
"""入金額を変えると月利がどう動くか、そしてなぜ動くか。

事前の予想（`measure.py` の docstring）は「**月利は入金額に対して不変のはず**」だった。
ロットも必要証拠金も equity に比例するので、証拠金/equity は入金額によらない——という理屈。

**実測は不変ではなかった。** その理由を枠別の寄与から見る。

仮説: **固定ロット枠**（SCA UJ / SCA GJ / Pair は `lot=0.01` を equity で割らない）は
入金額に比例して大きくならない。入金が小さいほど、これらの枠が口座に対して相対的に大きい。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CAP25 = ROOT.parent / "fxcap25"
MONTHS = 55.0
SLEEVES = ["pb_uj", "pb_gj", "rsi_uj", "rsi_eu", "rsi_gu",
           "pair", "carry", "sca_uj", "sca_gj"]
LABEL = {"pb_uj": "PB UJ", "pb_gj": "PB GJ", "rsi_uj": "RSI UJ",
         "rsi_eu": "RSI EU", "rsi_gu": "RSI GU", "pair": "Pair",
         "carry": "Carry", "sca_uj": "SCA UJ", "sca_gj": "SCA GJ"}
# equity連動（risk%またはrefDeposit連動）か、固定ロットか
KIND = {"pb_uj": "連動", "pb_gj": "連動", "rsi_uj": "連動(risk%)",
        "rsi_eu": "連動(risk%)", "rsi_gu": "連動(risk%)", "pair": "固定",
        "carry": "連動", "sca_uj": "固定", "sca_gj": "固定"}


def monthly(net, dep):
    return ((dep + net) / dep) ** (1.0 / MONTHS) - 1.0


def rows():
    out = []
    # 入金50万は fxcap25 の Y100（同一構成）を借りる
    for r in csv.DictReader(open(CAP25 / "results.csv", encoding="utf-8")):
        if r["proposal_id"] == "Y100" and r["window"] == "OOS" and r["status"] == "OK":
            out.append((500_000, r))
    deps = {"D02M": 2_000_000, "D05M": 5_000_000, "D20M": 20_000_000}
    p = ROOT / "results.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and r["proposal_id"] in deps:
                out.append((deps[r["proposal_id"]], r))
    out.sort(key=lambda t: t[0])
    return out


def main():
    data = rows()
    if not data:
        print("結果がまだ無い")
        return 1

    print("# 入金額と月利（X005の重み＋cap100%・OOS 55か月・1:25）")
    print("")
    print("| 入金 | 純益 | **月利** | 最大DD | 取引数 | 最終資産/入金 |")
    print("|---:|---:|---:|---:|---:|---:|")
    for dep, r in data:
        net = float(r["net"])
        print("| {:,} | {:,.0f} | **{:.2f}%** | {:.1f}% | {} | {:.1f}倍 |".format(
            dep, net, monthly(net, dep) * 100, float(r["dd_pct"]),
            r["trades"], (dep + net) / dep))

    print("")
    print("## 枠別の純益（入金に対する%）— なぜ月利が下がるのか")
    print("")
    print("**固定ロット枠は入金に比例して大きくならない。**")
    print("入金が小さいほど、固定ロット枠が口座に対して相対的に大きい。")
    print("")
    header = " | ".join("{:,}".format(d) for d, _ in data)
    print("| 枠 | ロット | " + header + " |")
    print("|---|---|" + "---:|" * len(data))
    for s in SLEEVES:
        cells = []
        for dep, r in data:
            try:
                v = float(r.get(f"{s}_net") or 0.0)
            except ValueError:
                v = 0.0
            cells.append("{:,.0f}%".format(v / dep * 100))
        print("| {} | {} | ".format(LABEL[s], KIND[s]) + " | ".join(cells) + " |")

    print("")
    print("## 取引数 — capで見送られていた注文が入金とともに復活する")
    print("")
    print("| 入金 | 取引数 | 無制約(1,375)との差 |")
    print("|---:|---:|---:|")
    for dep, r in data:
        n = int(r["trades"])
        print("| {:,} | {} | {:+d} |".format(dep, n, n - 1375))
    return 0


if __name__ == "__main__":
    sys.exit(main())
