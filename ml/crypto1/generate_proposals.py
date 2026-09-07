"""単軸の効果と両枠の干渉を分けて比較できるよう、既定値から掃引する。"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"
# CSV参照とAPI無効化は測定BASEに任せ、戦略の中心点をEA入力と一致させる。
DEFAULTS = {
    "FundThreshold": -0.003, "FundMaxHold": 20,
    "BfxDropPct": 10.0, "BfxLookbackDays": 10, "BfxHoldDays": 10,
}
rows, seen = [], set()
duplicates = 0


def add(family, desc, **params):
    global duplicates
    p = dict(DEFAULTS)
    p.update(params)
    assert p["FundThreshold"] < 0
    assert p["BfxDropPct"] > 0
    assert all(type(p[k]) is int and p[k] > 0
               for k in ("FundMaxHold", "BfxLookbackDays", "BfxHoldDays"))
    encoded = json.dumps(p, ensure_ascii=False, sort_keys=True)
    if encoded in seen:
        duplicates += 1
        return
    seen.add(encoded)
    rows.append(dict(proposal_id="C{:03d}".format(len(rows) + 1),
                     family=family, description=desc, parameter_json=encoded))


add("BASE", "両枠EA既定値・S2046採用済みの基準")
for v in (-0.001, -0.002, -0.004, -0.005, -0.006, -0.008):
    add("F1", f"funding閾値 {v}", FundThreshold=v)
for v in (5, 10, 15, 25, 30, 40):
    add("F2", f"funding保有上限 {v}日", FundMaxHold=v)
for threshold in (-0.002, -0.004):
    for days in (10, 30):
        add("F3", f"funding閾値 {threshold}・上限 {days}日",
            FundThreshold=threshold, FundMaxHold=days)
for v in (5.0, 7.5, 12.5, 15.0, 20.0):
    add("B1", f"Bfx建玉急減閾値 {v}%", BfxDropPct=v)
for v in (3, 5, 7, 15, 20):
    add("B2", f"Bfx観測窓 {v}日", BfxLookbackDays=v)
for v in (3, 5, 7, 15, 20, 30):
    add("B3", f"Bfx保有 {v}日", BfxHoldDays=v)
for drop in (7.5, 12.5):
    for days in (5, 20):
        add("B4", f"Bfx閾値 {drop}%・保有 {days}日", BfxDropPct=drop, BfxHoldDays=days)
# 実測前の有望仮説として、頻度増加と厳選、短期退出と長期保有を対にする。
for threshold, hold, drop, days in (
        (-0.002, 10, 7.5, 5), (-0.004, 10, 12.5, 5),
        (-0.002, 30, 12.5, 20), (-0.004, 30, 7.5, 20)):
    add("X1", f"両枠同時の有望仮説（未測定）: funding {threshold}/{hold}日・Bfx {drop}%/{days}日",
        FundThreshold=threshold, FundMaxHold=hold, BfxDropPct=drop, BfxHoldDays=days)


if __name__ == "__main__":
    assert len(rows) == 41
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"生成: {len(rows)}件 / 重複除去: {duplicates}件 / 出力内重複: {len(rows)-len(seen)}件")
    for family, count in Counter(r["family"] for r in rows).items():
        print(f"{family}: {count}件")
