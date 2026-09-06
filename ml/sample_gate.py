"""採否判断に「サンプル数が足りているか」のゲートを追加する（全ラウンド共通）。

【なぜ必要か】sca4（第4セッション）で、最良年除外後の頑健性ゲートを通った上位案が
軒並み IS 11〜20取引（年3〜4回）しかないことが判明した。「年次5/5黒字」という
合格判定が年3取引の上に乗っており、統計として意味を成していない。

サンプルが十分な案（IS 60取引以上）だけに絞ると、sca4 は13案中1案しか両窓黒字が
残らず、しかもその1案も IS +6,186/5年 と無視できる規模だった。
**ゲートが無ければ、年3取引の案を「年次6/6黒字の優良案」として採用していた。**

sca2b（第2セッション・91取引）と sca3（第3セッション・121取引）は結果的に
十分だったので問題が表面化しなかっただけである。以後は全ラウンドでこれを通す。

【閾値の根拠】既存の採用済み枠の IS 取引数は PB GOLD 63・第2セッション 91・
第3セッション 121・SCA第1 242。最小の PB GOLD が63なので、それを下回るものは
既存枠より薄いという意味で 60 を下限に置く。閾値自体に理論的な裏付けは無いので、
必ず取引数の実数と併せて見ること。

使い方:
    python ml/sample_gate.py sca2b sca3 sca4
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

ML = Path(__file__).resolve().parent

# ラウンド名 -> (枠の列接頭辞, 枠の説明)
ROUNDS = {
    "sca2b": ("sca2", "第2セッション（13-15時）の窓精査"),
    "sca3": ("sca3", "第3セッション（9-11時）"),
    "sca4": ("sca4", "第4セッション（未使用帯）"),
}

MIN_TRADES = 60   # 既存枠の最小（PB GOLD 63取引）を下回らないこと


def load(round_name: str, prefix: str):
    path = ML / round_name / "results.csv"
    if not path.exists():
        return {}
    by = collections.defaultdict(dict)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["status"] != "OK":
            continue
        by[r["proposal_id"]][r["window"]] = r
    out = []
    for pid, w in by.items():
        if "IS" not in w or "OOS" not in w:
            continue
        try:
            ni = int(w["IS"][f"{prefix}_n"] or 0)
            no = int(w["OOS"][f"{prefix}_n"] or 0)
            pi = float(w["IS"][f"{prefix}_net"] or 0)
            po = float(w["OOS"][f"{prefix}_net"] or 0)
        except (KeyError, ValueError):
            continue
        out.append({"pid": pid, "n_is": ni, "n_oos": no, "net_is": pi,
                    "net_oos": po, "desc": w["IS"]["description"]})
    return out


def report(round_name: str):
    prefix, label = ROUNDS[round_name]
    rows = load(round_name, prefix)
    if not rows:
        print(f"\n### {round_name} — 結果なし")
        return
    both = [r for r in rows if r["net_is"] > 0 and r["net_oos"] > 0]
    rich = [r for r in rows if r["n_is"] >= MIN_TRADES]
    rich_both = [r for r in rich if r["net_is"] > 0 and r["net_oos"] > 0]
    ns = sorted(r["n_is"] for r in rows)

    print(f"\n### {round_name} — {label}")
    print(f"  評価 {len(rows)}案 / 両窓とも枠が黒字 {len(both)}案")
    print(f"  IS取引数 中央値 {ns[len(ns)//2]} / 最小 {ns[0]} / 最大 {ns[-1]}")
    print(f"  サンプル十分（IS>={MIN_TRADES}取引） {len(rich)}案 / "
          f"うち両窓黒字 {len(rich_both)}案")
    if both:
        thin = [r for r in both if r["n_is"] < MIN_TRADES]
        print(f"  → 両窓黒字のうち {len(thin)}案 がサンプル不足で失格")
    print(f"\n  {'案':<8}{'IS取引':>7}{'OOS取引':>8}{'IS純益':>10}{'OOS純益':>10}"
          f"{'判定':>6}  内容")
    for r in sorted(rich_both, key=lambda x: -min(x["net_is"], x["net_oos"]))[:10]:
        print(f"  {r['pid']:<8}{r['n_is']:>7}{r['n_oos']:>8}{r['net_is']:>10,.0f}"
              f"{r['net_oos']:>10,.0f}{'合格':>6}  {r['desc'][:32]}")
    if not rich_both:
        print("  （サンプル十分かつ両窓黒字の案なし）")


def main():
    names = sys.argv[1:] or list(ROUNDS)
    print("既存の採用済み枠の IS 取引数: "
          "PB GOLD 63 / 第2セッション 91 / 第3セッション 121 / SCA第1 242")
    print(f"サンプル数ゲート: IS {MIN_TRADES}取引以上")
    for n in names:
        if n not in ROUNDS:
            print(f"\n未知のラウンド: {n}")
            continue
        report(n)


if __name__ == "__main__":
    main()
