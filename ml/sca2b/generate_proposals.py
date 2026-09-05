"""SCA GOLD 第2セッションの時間窓を1時間刻みで精査する。

前ラウンドの S2046 を中心に、隣接窓でも成績が保たれる台地なのか、
単独のスパイクなのかを判別するための案を揃える。
指定のない値は S2046 に固定し、時間窓以外の差が混ざるのを避ける。
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

DEFAULTS = {
    "Sca2Enable": True,
    "Sca2RangeStart": 13, "Sca2RangeEnd": 15,
    "Sca2TradeEnd": 20, "Sca2ForceClose": 23,
    "Sca2MinRange": 0.40, "Sca2MaxRange": 1.00, "Sca2Buffer": 0.0,
    "Sca2RR": 1.7, "Sca2SkipFriday": True,
    "Sca2RevBoost": True, "Sca2BoostMult": 2.0, "Sca2Lot": 0.01,
}

rows = []


def add(family, desc, **params):
    p = dict(DEFAULTS)
    p.update(params)
    # W3の20時決済は締切と同時刻を比較する案なので、等号を許す。
    assert 0 <= p["Sca2RangeStart"] < p["Sca2RangeEnd"] < p["Sca2TradeEnd"] <= p["Sca2ForceClose"] <= 24, desc
    assert 0 < p["Sca2MinRange"] < p["Sca2MaxRange"], desc
    rows.append({
        "proposal_id": "",
        "family": family,
        "description": desc,
        "parameter_json": json.dumps(p, ensure_ascii=False, sort_keys=True),
    })


# S2046そのものも含め、同じ測定条件で隣接窓と比較できるようにする。
for a in range(9, 17):
    for length in (1, 2, 3):
        b = a + length
        if b <= 18:
            add("W1_window", f"第2レンジ{a}-{b}時（締切20h・決済23h）",
                Sca2RangeStart=a, Sca2RangeEnd=b)

for te in (16, 17, 18, 19, 21, 22):
    add("W2_trade_end", f"第2レンジ13-15時・締切{te}h（決済23h）",
        Sca2TradeEnd=te)

for fc in (20, 21, 22, 24):
    add("W3_force_close", f"第2レンジ13-15時・強制決済{fc}h（締切20h）",
        Sca2ForceClose=fc)

for mn in (0.20, 0.30, 0.50, 0.60):
    for mx in (0.80, 1.00, 1.40):
        add("W4_range_filter", f"レンジ幅{mn}〜{mx}ATR（中心0.40〜1.00）",
            Sca2MinRange=mn, Sca2MaxRange=mx)

for rr in (1.3, 1.5, 1.9, 2.1, 2.4):
    add("W5_rr", f"第2セッションのRRを{rr}に（中心1.7）", Sca2RR=rr)

# 13-15時のRR1.5/1.9はW5に含まれるため、二重測定を避ける。
for a, b in [(12, 14), (14, 16), (13, 16)]:
    for rr in (1.5, 1.9):
        add("W6_window_x_rr", f"第2レンジ{a}-{b}時 × RR{rr}",
            Sca2RangeStart=a, Sca2RangeEnd=b, Sca2RR=rr)


if __name__ == "__main__":
    for n, row in enumerate(rows, start=1):
        row["proposal_id"] = f"S2B{n:03d}"

    seen = {}
    for row in rows:
        if row["parameter_json"] in seen:
            raise SystemExit(f"重複: {row['proposal_id']} と {seen[row['parameter_json']]}")
        seen[row["parameter_json"]] = row["proposal_id"]

    assert 56 <= len(rows) <= 72, len(rows)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"生成: {len(rows)} 件 -> {OUT}")
    print("重複なし")
    print()
    for fam, c in sorted(Counter(r["family"] for r in rows).items()):
        print(f"{fam:<22}{c:>5}")
