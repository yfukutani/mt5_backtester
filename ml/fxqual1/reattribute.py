"""第15報の枠別配賦を**建玉時の magic に引き直す**（第16報の訂正）。

【なぜ要るか】
`ml/fxmargin3/measure.py` の枠別集計は、deal の `magic` を直に引いていた。
ところが **窓の終わりに建ったままだったポジションをテスターが強制決済したときの
決済 deal は、`magic=0` で記録される**。したがってその損益は

  * ブック全体の `net`（最終残高ベース）には **入っている**
  * 枠別の `*_net` からは **丸ごと落ちている**

という非対称が生まれ、「枠の合計」と「ブック全体」が食い違う。
第15報はこの差額を **「FX以外の枠（GOLD・暗号・VBO）の損益」と誤読**し、
「Carry の退出SMA には他の枠を全滅させる副作用がある」と書いた。

実体は違う。この構成では GOLD・暗号・VBO は **1件も発注していない**。
差額の正体は **Carry AUDJPY の建玉が窓末に持っていた含み益**であり、
退出SMA を入れるとそれを早く切ってしまう、というだけである。

【このスクリプトがやること】
deal ダンプを読み直し、`magic=0` の決済 deal を `position_id` から
建玉時の magic に差し戻して集計する。ブック全体との残差も出す。
残差が入金額（500,000）だけになれば配賦は閉じている。
"""
from __future__ import annotations

import collections
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAGICS = {
    20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
    20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
    20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj",
}
ORDER = ["pb_uj", "pb_gj", "rsi_uj", "rsi_eu", "rsi_gu",
         "pair", "carry", "sca_uj", "sca_gj"]


def attribute(path: Path):
    """deal ダンプ1本を枠別に配賦する。戻り値は (枠→純益, 枠→取引数, 未配賦)。"""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    owner = {r["position_id"]: int(r["magic"]) for r in rows if r["entry"] == "0"}
    net = collections.defaultdict(float)
    cnt = collections.defaultdict(int)
    orphan = 0.0
    for r in rows:
        m = int(r["magic"])
        if m == 0:
            m = owner.get(r["position_id"], 0)
        k = MAGICS.get(m)
        if k is None:
            orphan += float(r["profit"])
            continue
        if r["entry"] == "0":
            cnt[k] += 1
        else:
            net[k] += float(r["profit"])
    return net, cnt, orphan


def main(results: Path = ROOT / "results.csv"):
    rows = list(csv.DictReader(open(results, encoding="utf-8")))
    out = []
    for r in rows:
        if r["status"] != "OK" or not r["deals"]:
            continue
        p = Path(r["deals"])
        if not p.exists():
            p = ROOT / "run_deals" / p.name
        if not p.exists():
            continue
        net, cnt, orphan = attribute(p)
        out.append({
            "id": r["proposal_id"], "window": r["window"],
            "book_net": float(r["net"]), "sum_sleeves": sum(net.values()),
            "orphan": orphan,
            **{k: net.get(k, 0.0) for k in ORDER},
            **{f"n_{k}": cnt.get(k, 0) for k in ORDER},
        })
    return out


def table(out, base_id="Q000"):
    base = {(o["window"]): o for o in out if o["id"] == base_id}
    hdr = f"{'案':<6}{'窓':<5}{'ブック純益':>12}{'枠の和':>12}{'未配賦':>9}  " + \
          "".join(f"{k:>10}" for k in ORDER)
    print(hdr)
    print("-" * len(hdr))
    for o in out:
        print(f"{o['id']:<6}{o['window']:<5}{o['book_net']:>12,.0f}"
              f"{o['sum_sleeves']:>12,.0f}{o['orphan']:>9,.0f}  " +
              "".join(f"{o[k]:>10,.0f}" for k in ORDER))
    print()
    print("=== 対照 Q000 との差（枠別・配賦修正後）===")
    print(hdr)
    for o in out:
        if o["id"] == base_id:
            continue
        b = base.get(o["window"])
        if not b:
            continue
        print(f"{o['id']:<6}{o['window']:<5}"
              f"{o['book_net'] - b['book_net']:>12,.0f}"
              f"{o['sum_sleeves'] - b['sum_sleeves']:>12,.0f}"
              f"{o['orphan'] - b['orphan']:>9,.0f}  " +
              "".join(f"{o[k] - b[k]:>10,.0f}" for k in ORDER))


if __name__ == "__main__":
    res = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results.csv"
    o = main(res)
    o.sort(key=lambda x: (x["id"], x["window"]))
    table(o)
