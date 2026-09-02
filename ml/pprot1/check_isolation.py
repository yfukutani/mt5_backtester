"""枠マスクの分離を検証する。

PprotSleeveMask で対象外にした枠は、dealが1件も変わっていないはずである。
変わっていれば、ラボの機構が対象外の枠に漏れているか、枠どうしが口座状態を通じて
干渉していることになり、測定の解釈が変わる。
"""
import csv
import sys
from collections import defaultdict

MAGIC_NAME = {20260640: "PB GOLD", 20261002: "SCA GOLD"}


def load(path):
    per_magic = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        per_magic[int(r["magic"])].append(
            (int(r["time"]), r["entry"], int(r["position_id"]), r["type"],
             r["volume"], r["price"], r["sl"], r["profit"], r["profit_jpy"], r["usdjpy"]))
    for k in per_magic:
        per_magic[k].sort()
    return per_magic


def main(base_path, cand_path):
    base, cand = load(base_path), load(cand_path)
    for magic in sorted(set(base) | set(cand)):
        b, c = base.get(magic, []), cand.get(magic, [])
        name = MAGIC_NAME.get(magic, str(magic))
        if b == c:
            print(f"{name:<10} deal {len(b):>4} 件  → 完全一致（1バイトの差もなし）")
            continue
        print(f"{name:<10} deal 基準{len(b)} / 候補{len(c)}  → 差分あり")
        # どの列が違うのかを特定する
        cols = ["time", "entry", "position_id", "type", "volume", "price", "sl",
                "profit", "profit_jpy", "usdjpy"]
        if len(b) == len(c):
            diff_cols = set()
            n_diff = 0
            for rb, rc in zip(b, c):
                if rb != rc:
                    n_diff += 1
                    for i, col in enumerate(cols):
                        if rb[i] != rc[i]:
                            diff_cols.add(col)
            print(f"           件数は同じ。異なるdeal {n_diff} 件 / 異なる列: {sorted(diff_cols)}")
            for rb, rc in zip(b, c):
                if rb != rc:
                    print(f"           基準: {rb}")
                    print(f"           候補: {rc}")
                    break
        else:
            print(f"           件数が違う（差 {len(c)-len(b):+d}）")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
