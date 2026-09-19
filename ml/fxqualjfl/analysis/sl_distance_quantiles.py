# -*- coding: utf-8 -*-
"""枠ごとの SL距離比 |entry-sl|/entry の分位点を出す。フロア水準を決めるため。"""
import csv
import sys

MAGIC = {20260622: "pb_uj", 20260627: "pb_gj",
         20261000: "sca_uj", 20261001: "sca_gj"}


def main(path, label):
    vals = {k: [] for k in MAGIC}
    for r in csv.DictReader(open(path, encoding="utf-8", errors="replace")):
        if r["entry"] != "0":
            continue
        m = int(r["magic"])
        if m not in MAGIC:
            continue
        p, s = float(r["price"]), float(r["sl"])
        if p > 0 and s > 0:
            vals[m].append(abs(p - s) / p)
    print(f"===== {label} =====")
    print(f"{'枠':8s} {'n':>5s} " + " ".join(f"p{q:02d}" .rjust(8) for q in
                                            (5, 10, 20, 30, 40, 50, 60, 70, 80, 90)))
    for m, name in MAGIC.items():
        v = sorted(vals[m])
        if not v:
            continue
        qs = [v[min(len(v) - 1, len(v) * q // 100)]
              for q in (5, 10, 20, 30, 40, 50, 60, 70, 80, 90)]
        print(f"{name:8s} {len(v):>5d} " + " ".join(f"{x:8.5f}" for x in qs))


if __name__ == "__main__":
    for a in sys.argv[1:]:
        lbl, p = a.split("=", 1)
        main(p, lbl)
