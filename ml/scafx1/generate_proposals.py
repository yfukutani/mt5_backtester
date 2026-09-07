"""親枠と新枠の寄与を混同しないよう、通貨別の既定値から掃引する。"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"
# EA入力のスナップショットにより、中心点と明示的な既定値変更の重複を除く。
DEFAULTS = {
    "RangeStart": 13, "RangeEnd": 15, "TradeEnd": 20, "ForceClose": 23,
    "MinRange": 0.30, "MaxRange": 1.00, "Buffer": 0.10, "RR": 2.0,
    "SkipFriday": False, "RevBoost": True, "BoostMult": 2.0, "Lot": 0.01,
}
rows, seen = [], set()
duplicates = 0


def add(prefix, family, description, **changes):
    global duplicates
    p = dict(DEFAULTS)
    if prefix == "Sca6":
        p.update(Buffer=0.0, BoostMult=6.0)
    p.update(changes)
    assert 9 <= p["RangeStart"] < p["RangeEnd"] < p["TradeEnd"] < p["ForceClose"] <= 24
    assert 0 < p["MinRange"] < p["MaxRange"]
    params = {prefix + k: v for k, v in p.items()}
    params[prefix + "Enable"] = True
    encoded = json.dumps(params, ensure_ascii=False, sort_keys=True)
    if encoded in seen:
        duplicates += 1
        return
    seen.add(encoded)
    symbol = "USDJPY" if prefix == "Sca5" else "GBPJPY"
    rows.append(dict(proposal_id=f"X{len(rows)+1:03d}", family=family,
                     description=f"SCA {symbol} 第2セッション: {description}",
                     parameter_json=encoded))


for prefix, family in (("Sca5", "U"), ("Sca6", "G")):
    add(prefix, family + "0", "EA既定値の中心点")
    for start in range(10, 18):
        for width in (1, 2):
            end = start + width
            if end <= 19:
                add(prefix, family + "1", f"レンジ {start}-{end}時",
                    RangeStart=start, RangeEnd=end)
    for value in (17, 18, 19, 21, 22):
        add(prefix, family + "2", f"締切 {value}時", TradeEnd=value)
    for value in (1.3, 1.5, 1.7, 2.4, 3.0):
        add(prefix, family + "3", f"RR {value}", RR=value)
    # 広いレンジ許容と厳選の両側を残すため、対角を含む5組を固定する。
    for low, high in ((0.20, 0.80), (0.20, 1.40), (0.40, 0.80),
                      (0.40, 1.40), (0.50, 1.40)):
        add(prefix, family + "4", f"レンジ幅 {low}-{high}", MinRange=low, MaxRange=high)
    for value in (0.0, 0.05, 0.20):
        add(prefix, family + "5", f"バッファ {value}", Buffer=value)
    for value in (1.0, 3.0):
        add(prefix, family + "5", f"Boost {value}", BoostMult=value)


def write(path, records):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    assert len(rows) == 71 and duplicates == 3
    write(OUT, rows)
    # 中心点は新枠ONなので、OFFの実測基準を独立に用意する必要がある。
    write(ROOT / "baseline_proposals.csv", [dict(
        proposal_id="BASE", family="BASE", description="OANDA相当・新枠両方OFF",
        parameter_json="{}")])
    print(f"生成: {len(rows)}件 / 重複除去: {duplicates}件 / 出力内重複: {len(rows)-len(seen)}件")
    for family, count in Counter(r["family"] for r in rows).items():
        print(f"{family}: {count}件")
