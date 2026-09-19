"""SCA 2枠の損益を「反転日ブーストが乗った玉」と「平常日の玉」に割る。

【なぜ要るか】
第23報で自己訂正したとおり、`RevBoost` は最大6倍のロットを乗せるので、
**「リスク当たり」と「equity 当たり」で `sca_gj` の符号が割れる。**
第12ラウンドの C群（`Mult_SCA_GBPJPY` を下げる）は**枠ぜんぶ**を一律に下げたので、
**IS の悪化が反転日から来たのか平常日から来たのかが分からない。**

`docs/oanda_fx_sca_boost_under_risk_20260919.md` の案（boost だけを下げる）を
走らせる前に、ここを確認する。**確認せずに測ると、また「効かなかった」だけが残る。**

【どう割るか】
deal ログに boost フラグは無い。だが risk% 化された枠では
**発注時のリスク額 ＝ volume × 契約サイズ × |price − sl|** が
equity の 0.5%（平常）か 3.0%（GJ の反転日・0.5%×6）に張り付く。
**equity は確定損益の累積で近似する**（含み益は無視する＝やや過小）。
したがって「リスク率 > 1.5%」を boost 判定に使う。UJ は 0.5% vs 1.0% なので
閾値 0.75% を使う。**境界に玉が溜まっていないことを必ず確認する**（§出力の分布）。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

DEPOSIT = 500_000.0
# magic -> (名前, 契約サイズ, boost 判定のリスク率しきい値%)
TARGET = {
    20261001: ("sca_gj", 100_000.0, 1.5),
    20261000: ("sca_uj", 100_000.0, 0.75),
}


def analyse(path: Path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))
    # position_id -> 建玉時の情報
    opened = {}
    bal = DEPOSIT
    out = defaultdict(lambda: {"n": 0, "net": 0.0, "risk": 0.0})
    ratios = defaultdict(list)
    for r in rows:
        pid = r["position_id"]
        m = int(r["magic"])
        if r["entry"] == "0":
            if m in TARGET:
                name, csz, thr = TARGET[m]
                vol = float(r["volume"])
                dist = abs(float(r["price"]) - float(r["sl"]))
                risk = vol * csz * dist          # GBPJPY/USDJPY は JPY 建てなのでそのまま円
                ratio = 100.0 * risk / bal if bal > 0 else 0.0
                opened[pid] = (name, ratio >= thr, risk, ratio)
                ratios[name].append(ratio)
            continue
        bal += float(r["profit"])
        if pid in opened:
            name, boosted, risk, ratio = opened.pop(pid)
            k = (name, "boost" if boosted else "plain")
            out[k]["n"] += 1
            out[k]["net"] += float(r["profit"])
            out[k]["risk"] += risk
    return out, ratios


def main(paths):
    for p in paths:
        p = Path(p)
        out, ratios = analyse(p)
        print(f"\n=== {p.name} ===")
        print(f"{'群':14} {'取引数':>6} {'純益(円)':>12} {'риск合計':>12} "
              f"{'1取引平均':>10} {'リスク当たりR':>12}")
        for k in sorted(out):
            v = out[k]
            avg = v["net"] / v["n"] if v["n"] else 0.0
            rr = v["net"] / v["risk"] if v["risk"] else 0.0
            print(f"{k[0]+'/'+k[1]:14} {v['n']:6d} {v['net']:12,.0f} "
                  f"{v['risk']:12,.0f} {avg:10,.0f} {rr:12.4f}")
        for name, rs in ratios.items():
            rs = sorted(rs)
            if not rs:
                continue
            q = lambda f: rs[min(len(rs) - 1, int(f * len(rs)))]
            print(f"  [{name}] リスク率%分布 n={len(rs)} "
                  f"min={rs[0]:.3f} p25={q(.25):.3f} p50={q(.5):.3f} "
                  f"p75={q(.75):.3f} p90={q(.9):.3f} max={rs[-1]:.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
