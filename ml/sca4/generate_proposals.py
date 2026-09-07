"""第2＋第4セッション採用後の増分を比較するため、SCA4の各軸を中心点から振る。"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

# EA既定値に揃え、調べたい軸以外の差が増分に混ざるのを避ける。
DEFAULTS = {
    "Sca4Enable": True,
    "Sca4RangeStart": 12, "Sca4RangeEnd": 13,
    "Sca4TradeEnd": 20, "Sca4ForceClose": 23,
    "Sca4MinRange": 0.40, "Sca4MaxRange": 1.00, "Sca4Buffer": 0.0,
    "Sca4RR": 1.7, "Sca4SkipFriday": True,
    "Sca4RevBoost": True, "Sca4BoostMult": 2.0, "Sca4Lot": 0.01,
}
rows = []
seen = set()
duplicates = 0


def add(family, desc, **params):
    global duplicates
    p = dict(DEFAULTS)
    p.update(params)
    # 日跨ぎと既存3枠のレンジ重複を避け、時間帯追加の増分に限定する。
    assert 0 <= p["Sca4RangeStart"] < p["Sca4RangeEnd"] < p["Sca4TradeEnd"] < p["Sca4ForceClose"] <= 24, desc
    assert any(lo <= p["Sca4RangeStart"] < p["Sca4RangeEnd"] <= hi
               for lo, hi in ((11, 13), (15, 22))), desc
    assert 0 < p["Sca4MinRange"] < p["Sca4MaxRange"], desc
    encoded = json.dumps(p, ensure_ascii=False, sort_keys=True)
    if encoded in seen:
        duplicates += 1
        return
    seen.add(encoded)
    rows.append({
        "proposal_id": f"S{4001 + len(rows)}",
        "family": family,
        "description": desc,
        "parameter_json": encoded,
    })


# 中心点を先頭かつ窓ファミリーに置き、台地表でも同じ参照点を使えるようにする。
add("U1_window", "第4レンジ12-13時・EA既定の中心点（有効化）")
windows = [(11, 12), (11, 13), (12, 13)]
windows += [(start, start + width) for start in range(15, 21)
            for width in (1, 2, 3) if start + width <= 22]
for start, end in windows:
    # 遅い窓でもエントリーと決済の時間を確保するため、必要な分だけ後ろへずらす。
    te = max(DEFAULTS["Sca4TradeEnd"], end + 1)
    fc = max(DEFAULTS["Sca4ForceClose"], te + 1)
    adjusted = "・窓終了後の時間確保のため締切/決済を調整" if (te, fc) != (20, 23) else ""
    add("U1_window", f"第4レンジ{start}-{end}時（締切{te}h・決済{fc}h{adjusted}）",
        Sca4RangeStart=start, Sca4RangeEnd=end, Sca4TradeEnd=te, Sca4ForceClose=fc)

for te in (15, 17, 19, 21, 22):
    add("U2_trade_end", f"第4レンジ12-13時・締切{te}h", Sca4TradeEnd=te)

for fc in (20, 21, 22, 24):
    # 決済20hは既定締切と同時になるため、厳密な前後条件を優先して19hへ戻す。
    te = min(DEFAULTS["Sca4TradeEnd"], fc - 1)
    adjusted = "・締切<決済を守るため締切19hへ調整" if te != 20 else ""
    add("U3_force_close", f"第4レンジ12-13時・強制決済{fc}h{adjusted}",
        Sca4ForceClose=fc, Sca4TradeEnd=te)

for rr in (1.3, 1.5, 1.9, 2.1, 2.4):
    add("U4_rr", f"第4セッションRR{rr}", Sca4RR=rr)

# 6案でも下限の全水準を各2回、上限の全水準を各2回含め、特定の水準への偏りを避ける。
for mn, mx in ((0.20, 0.80), (0.20, 1.00), (0.30, 0.80),
               (0.30, 1.40), (0.50, 1.00), (0.50, 1.40)):
    add("U5_range_filter", f"第4レンジ幅{mn}〜{mx}ATR",
        Sca4MinRange=mn, Sca4MaxRange=mx)

for buffer in (0.02, 0.05, 0.10):
    add("U6_buffer", f"第4バッファ{buffer}ATR", Sca4Buffer=buffer)

add("U7_friday_boost", "第4セッション金曜も取引", Sca4SkipFriday=False)
add("U7_friday_boost", "第4セッション逆行ブーストなし", Sca4RevBoost=False)
for mult in (1.5, 3.0):
    add("U7_friday_boost", f"第4逆行ブースト{mult}倍", Sca4BoostMult=mult)


if __name__ == "__main__":
    assert len(rows) == 47, len(rows)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"生成: {len(rows)} 件 -> {OUT}")
    print(f"重複除去: {duplicates} 件 / 出力内の重複: {len(rows) - len(seen)} 件")
    for family, count in sorted(Counter(r["family"] for r in rows).items()):
        print(f"{family:<22}{count:>5}")
