# -*- coding: utf-8 -*-
"""入金が大きいほど月利が下がるのはなぜか — ロットの上限に当たっていないか。

`analyse.py` で立てた「固定ロット枠が効いている」という仮説は**外れた**
（固定ロット枠の寄与は入金50万でも純益のごく一部）。

次の候補は `Clamp()` の `SYMBOL_VOLUME_MAX` である。
入金2000万は 13.2倍に増えて最終資産 2.6億円になる。risk 1% × 倍率3 × 枠重み4 なら
1回のロットが業者の上限に当たってもおかしくない。**当たっていれば、
大口座はロットを頭打ちにされており、月利が下がるのは当然**である。

ロットの分布を入金別に出して確かめる。deal ログだけで見える。
"""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CAP25 = ROOT.parent / "fxcap25"
MAGICS = {20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
          20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
          20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ"}


def entries(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["entry"]) != 0:
            continue
        m = int(r["magic"])
        if m in MAGICS:
            out.append((m, float(r["volume"])))
    return out


def find():
    got = []
    hits = sorted(CAP25.glob("run_deals/mc_oos_Y100_*_deals.csv"))
    if hits:
        got.append((500_000, hits[0]))
    for pid, dep in (("D02M", 2_000_000), ("D05M", 5_000_000), ("D20M", 20_000_000)):
        h = sorted(ROOT.glob(f"run_deals/mc_oos_{pid}_*_deals.csv"))
        if h:
            got.append((dep, h[0]))
    return got


def main():
    runs = find()
    if not runs:
        print("deal ログが見つからない")
        return 1

    print("# ロットは上限に当たっているか（OOS 55か月・cap100%）")
    print("")
    print("| 入金 | 発注数 | 最大ロット | 最頻ロット | その回数 | 最頻の割合 | 中央値 |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    tops = {}
    for dep, p in runs:
        es = entries(p)
        vols = sorted(v for _m, v in es)
        c = Counter(v for _m, v in es)
        top, n = c.most_common(1)[0]
        tops[dep] = top
        print("| {:,} | {} | {:.2f} | **{:.2f}** | {} | {:.0f}% | {:.2f} |".format(
            dep, len(es), max(vols), top, n, n / len(es) * 100,
            vols[len(vols) // 2]))

    print("")
    print("## 最大ロットに張り付いた発注の割合（枠別）")
    print("")
    print("同じロットが何度も出るなら、それは計算値ではなく**上限**である。")
    print("")
    print("| 入金 | " + " | ".join(MAGICS.values()) + " |")
    print("|---:|" + "---:|" * len(MAGICS))
    for dep, p in runs:
        es = entries(p)
        mx = max(v for _m, v in es)
        cells = []
        for m in MAGICS:
            sub = [v for mm, v in es if mm == m]
            if not sub:
                cells.append("—")
                continue
            hit = sum(1 for v in sub if abs(v - mx) < 1e-9)
            cells.append("{:.0f}%".format(hit / len(sub) * 100))
        print("| {:,} | ".format(dep) + " | ".join(cells) + " |")

    print("")
    print("## 入金を4倍にしたらロットも4倍になったか（比例していれば scale 不変）")
    print("")
    print("| 枠 | 500,000 の平均ロット | 20,000,000 の平均ロット | 倍率（40倍なら比例） |")
    print("|---|---:|---:|---:|")
    small = dict((m, []) for m in MAGICS)
    big = dict((m, []) for m in MAGICS)
    for dep, p in runs:
        if dep not in (500_000, 20_000_000):
            continue
        tgt = small if dep == 500_000 else big
        for m, v in entries(p):
            tgt[m].append(v)
    for m in MAGICS:
        a = sum(small[m]) / len(small[m]) if small[m] else 0.0
        b = sum(big[m]) / len(big[m]) if big[m] else 0.0
        r = b / a if a > 0 else 0.0
        print("| {} | {:.3f} | {:.3f} | **{:.1f}倍** |".format(MAGICS[m], a, b, r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
