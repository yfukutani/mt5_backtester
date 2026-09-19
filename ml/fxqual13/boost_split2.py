"""boost_split.py の判別を作り直す（**前版の判別はノイズが乗っていた**）。

【前版の何が悪かったか】
前版は「発注時のリスク額 ÷ **確定損益の累積（残高）**」を equity の代理にして、
1.5% を閾値に boost / plain を割った。「分布がきれいに二峰だから誤判定はほぼ無い」と
書いたが、**それは分位を読み違えていた**——IS の `sca_gj` は p75 0.962 / p90 3.220 で、
**15%（約102取引）が 0.96〜3.22% の谷に落ちている。** 二峰ではあるが谷は埋まっている。

原因は代理の質である。**Carry は数か月〜数年ポジションを持つので、確定残高と
実 equity が大きく乖離する。** 真の 0.5% が 1.5% に見えたり、真の 3.0% が 6% に
見えたりする（実際 max は 6.106% だった）。

【作り直した判別 — 局所中央値との比】
`lot = LotRisk()` は `equity × riskPct ÷ SL距離` なので、
**同じ枠の・時間的に近い取引どうしなら equity はほぼ同じ**である。
したがって **「その取引のリスク額 ÷ 近傍 K 取引のリスク額の中央値」**は
equity の推定誤差に依らない。boost は 6倍（UJ は 2倍）なので、
平常日ばかりの近傍に対して比は 6 に近づく。

判別は **GJ: 比 ≥ 3.0 / UJ: 比 ≥ 1.5**。近傍は前後 20取引（自分を除く）。
**谷がどれだけ空いているかを必ず出力する**（前版の失敗を繰り返さないため）。
"""
from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# magic -> (名前, 契約サイズ, 比のしきい値, 設計上の boost 倍率)
TARGET = {
    20261001: ("sca_gj", 100_000.0, 3.0, 6.0),
    20261000: ("sca_uj", 100_000.0, 1.5, 2.0),
}
K = 20          # 近傍の片側取引数


def analyse(path: Path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))
    # 枠ごとに「建玉の列」を作る
    seq = defaultdict(list)          # name -> [(position_id, risk)]
    for r in rows:
        if r["entry"] != "0":
            continue
        m = int(r["magic"])
        if m not in TARGET:
            continue
        name, csz, _, _ = TARGET[m]
        dist = abs(float(r["price"]) - float(r["sl"]))
        seq[name].append((r["position_id"], float(r["volume"]) * csz * dist))

    label = {}                       # position_id -> (name, boosted, ratio)
    ratios = defaultdict(list)
    for name, lst in seq.items():
        thr = next(t[2] for t in TARGET.values() if t[0] == name)
        risks = [x[1] for x in lst]
        for j, (pid, risk) in enumerate(lst):
            lo, hi = max(0, j - K), min(len(lst), j + K + 1)
            near = [risks[q] for q in range(lo, hi) if q != j]
            med = statistics.median(near) if near else risk
            ratio = risk / med if med > 0 else 1.0
            label[pid] = (name, ratio >= thr, ratio)
            ratios[name].append(ratio)

    out = defaultdict(lambda: {"n": 0, "net": 0.0, "risk": 0.0})
    for r in rows:
        if r["entry"] == "0":
            continue
        pid = r["position_id"]
        if pid not in label:
            continue
        name, boosted, _ = label[pid]
        k = (name, "boost" if boosted else "plain")
        out[k]["n"] += 1
        out[k]["net"] += float(r["profit"])
    return out, ratios


def main(paths):
    for p in paths:
        p = Path(p)
        out, ratios = analyse(p)
        print(f"\n=== {p.name} ===")
        print(f"{'群':14} {'取引数':>6} {'純益(円)':>12} {'1取引平均':>10}")
        for k in sorted(out):
            v = out[k]
            print(f"{k[0]+'/'+k[1]:14} {v['n']:6d} {v['net']:12,.0f} "
                  f"{v['net']/v['n'] if v['n'] else 0:10,.0f}")
        for name, rs in sorted(ratios.items()):
            thr = next(t[2] for t in TARGET.values() if t[0] == name)
            rs = sorted(rs)
            band = [x for x in rs if 1.3 <= x <= thr + 1.0]
            print(f"  [{name}] 近傍中央値比 n={len(rs)} "
                  f"p50={rs[len(rs)//2]:.2f} p75={rs[int(.75*len(rs))]:.2f} "
                  f"p90={rs[int(.9*len(rs))]:.2f} max={rs[-1]:.2f} / "
                  f"**谷(1.3〜{thr+1.0:.1f})に居るのは {len(band)}件 "
                  f"({100*len(band)/len(rs):.1f}%)**")


if __name__ == "__main__":
    main(sys.argv[1:])
