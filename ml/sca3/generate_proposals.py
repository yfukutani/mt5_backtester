"""第2セッション採用後の増分を比較するため、SCA3の各軸を中心点から振る。"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

# EA既定値に揃え、調べたい軸以外の差が増分に混ざるのを避ける。
DEFAULTS = {
    "Sca3Enable": True,
    "Sca3RangeStart": 9, "Sca3RangeEnd": 11,
    "Sca3TradeEnd": 20, "Sca3ForceClose": 23,
    "Sca3MinRange": 0.40, "Sca3MaxRange": 1.00, "Sca3Buffer": 0.0,
    "Sca3RR": 1.7, "Sca3SkipFriday": True,
    "Sca3RevBoost": True, "Sca3BoostMult": 2.0, "Sca3Lot": 0.01,
}
rows = []
seen = set()
duplicates = 0


def add(family, desc, **params):
    global duplicates
    p = dict(DEFAULTS)
    p.update(params)
    # 締切と同時の20時決済も比較対象なので、決済側だけ等号を許す。
    assert 0 <= p["Sca3RangeStart"] < p["Sca3RangeEnd"] < p["Sca3TradeEnd"] <= p["Sca3ForceClose"] <= 24, desc
    assert p["Sca3RangeEnd"] <= 13, desc
    assert 0 < p["Sca3MinRange"] < p["Sca3MaxRange"], desc
    encoded = json.dumps(p, ensure_ascii=False, sort_keys=True)
    if encoded in seen:
        duplicates += 1
        return
    seen.add(encoded)
    rows.append({
        "proposal_id": f"S{3001 + len(rows)}",
        "family": family,
        "description": desc,
        "parameter_json": encoded,
    })


# 中心点を先頭かつ窓ファミリーに置き、台地表でも同じ参照点を使えるようにする。
add("T1_window", "第3レンジ9-11時・EA既定の中心点（有効化）")
for start in range(7, 13):
    for width in (1, 2, 3):
        end = start + width
        if end <= 13:
            add("T1_window", f"第3レンジ{start}-{end}時（締切20h・決済23h）",
                Sca3RangeStart=start, Sca3RangeEnd=end)

for te in (13, 15, 17, 19, 21, 22):
    add("T2_trade_end", f"第3レンジ9-11時・締切{te}h", Sca3TradeEnd=te)

for fc in (20, 21, 22, 24):
    add("T3_force_close", f"第3レンジ9-11時・強制決済{fc}h", Sca3ForceClose=fc)

for mn in (0.20, 0.30, 0.50):
    for mx in (0.80, 1.00, 1.40):
        # 8案に収めるため、両端を同時に最も緩める組だけを外す。
        if (mn, mx) != (0.20, 1.40):
            add("T4_range_filter", f"第3レンジ幅{mn}〜{mx}ATR",
                Sca3MinRange=mn, Sca3MaxRange=mx)

for rr in (1.3, 1.5, 1.9, 2.1, 2.4):
    add("T5_rr", f"第3セッションRR{rr}", Sca3RR=rr)

for buffer in (0.02, 0.05, 0.10):
    add("T6_buffer", f"第3バッファ{buffer}ATR", Sca3Buffer=buffer)

add("T7_friday_boost", "第3セッション金曜も取引", Sca3SkipFriday=False)
add("T7_friday_boost", "第3セッション逆行ブーストなし", Sca3RevBoost=False)
for mult in (1.5, 3.0):
    add("T7_friday_boost", f"第3逆行ブースト{mult}倍", Sca3BoostMult=mult)


if __name__ == "__main__":
    assert len(rows) == 45, len(rows)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"生成: {len(rows)} 件 -> {OUT}")
    print(f"重複除去: {duplicates} 件 / 出力内の重複: {len(rows) - len(seen)} 件")
    for family, count in sorted(Counter(r["family"] for r in rows).items()):
        print(f"{family:<22}{count:>5}")
