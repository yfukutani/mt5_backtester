"""GOLD側の倍率を上に伸ばして、DD予算が拘束するところまで測る。

【なぜ必要か】84runの結果で、最良は G004（倍率4・Gszラボは**OFF**）だった。
risk%サイジング（Gszラボ）は複利にしても固定ロットに勝てず、
gold_risk_sizing_20260905.md の棄却が複利前提でも追認された形になった。

そのG004の**最大DDが10.5%しかない**。入金50万に対してDD予算をまったく使っていない。
FX側は倍率3〜4でDD 27%前後まで使っていたのに対し、GOLD側は倍率4でこの水準である。
**倍率の上限がどこかを測っていない**ので、そこを埋める。

【注意】GOLD 2枠も暗号3枠も固定ロットなので、円建て損益は倍率に比例する。
つまり複利は効かない。ここで出る「月利(複利)」は最終資産から逆算した幾何平均で、
実際に資産が再投下されているわけではない。倍率を上げても複利にはならない。
"""
import csv
from pathlib import Path

import measure as m

OUT = Path(__file__).resolve().parent / "results_highmult.csv"

# 既測定は倍率1〜4。DDが10.5%しか使われていないので上を測る。
MULTS = [6, 8, 10, 12, 16]


def main():
    props = {r["proposal_id"]: r for r in
             csv.DictReader(open(m.ROOT / "proposals.csv", encoding="utf-8"))}
    base = props["G001"]          # 倍率1・Gszラボ OFF
    import json
    p0 = json.loads(base["parameter_json"])

    for d in (m.RUN_DIR, m.CONFIG_DIR, m.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    m._ea_sha = m.ea_sha()
    m.log(f"HIGHMULT_START EA_SHA {m._ea_sha[:16]} mults={MULTS}")

    jobs = []
    for mult in MULTS:
        p = dict(p0)
        p["GlobalLotMult"] = mult
        prop = {"proposal_id": f"H{mult:02d}", "family": "HIGHMULT",
                "description": f"Gszラボ OFF / 倍率{mult}（DD上限の探索）",
                "parameter_json": json.dumps(p)}
        for w in ("FULL", "OOS"):
            jobs.append((prop, w))

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        for prop, window in jobs:
            results.append(m.run(prop, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=m.FIELDS)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in m.FIELDS})
    ok = sum(1 for r in results if r.get("status") == "OK")
    m.log(f"HIGHMULT_END rows={len(results)} ok={ok} -> {OUT}")


if __name__ == "__main__":
    main()
