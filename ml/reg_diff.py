# -*- coding: utf-8 -*-
"""回帰ゲート: 2つのmixlog CSV（EnableOpsLog出力）のDEAL行が完全一致するか判定。
時刻・magic・銘柄・方向・ロット・価格・SL/TP・損益・IN/OUTの全列を比較する。
SCA_RANGE行の差分は参考表示（equityが乗るDAILY行は比較しない）。

usage: python ml/reg_diff.py <label> <base.csv...> -- <post.csv...>
exit 0 = 完全一致 / 1 = 差分あり
"""
import csv
import sys


def load(paths, rowtype):
    rows = []
    for p in paths:
        with open(p, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.reader(fh):
                if len(r) >= 11 and r[1] == rowtype:
                    rows.append(",".join(r))
    return rows


def main():
    args = sys.argv[1:]
    label = args[0]
    sep = args.index("--")
    base_paths, post_paths = args[1:sep], args[sep + 1:]

    fail = False
    for rowtype in ("DEAL", "SCA_RANGE"):
        b, p = load(base_paths, rowtype), load(post_paths, rowtype)
        if b == p:
            print("[%s] %-9s PASS  (%d rows identical)" % (label, rowtype, len(b)))
            continue
        if rowtype == "DEAL":
            fail = True
        print("[%s] %-9s %s  base=%d post=%d"
              % (label, rowtype, "FAIL" if rowtype == "DEAL" else "DIFF(参考)", len(b), len(p)))
        sb, sp = set(b), set(p)
        for r in b:
            if r not in sp:
                print("   base only: " + r)
        for r in p:
            if r not in sb:
                print("   post only: " + r)
        if b != p and sb == sp:
            print("   (行集合は同一・順序のみ相違)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
