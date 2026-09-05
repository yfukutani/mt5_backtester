"""PB GOLD 第2時間軸の中心点と周辺を比較し、時間軸分散の候補を探す。

入力名と既定値は MIX_EA_SIMVERIFY.mq5 の PB2 入力群に合わせる。
PB2を有効にしたH1中心点を固定し、各変更の効果を切り分ける。
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

DEFAULTS = {
    "Pb2Enable": True, "Pb2TFMinutes": 60, "Pb2Lot": 0.01,
    "Pb2RR": 1.8, "Pb2ATRSLmult": 2.0, "Pb2ADXThr": 22.5,
    "Pb2SlopeMinATR": 1.2, "Pb2HoldBars": 64, "Pb2UseHourGate": False,
}

rows = []
seen = set()
duplicates = 0


def add(family, desc, **params):
    global duplicates
    assert params.keys() <= DEFAULTS.keys(), desc
    p = dict(DEFAULTS)
    p.update(params)
    # EAが受け付けない時間軸で測定枠を浪費しないようにする。
    assert p["Pb2TFMinutes"] in (30, 60, 120, 240), desc
    parameter_json = json.dumps(p, ensure_ascii=False, sort_keys=True)
    # 単項目案と交差案の共通点は先のファミリーに残し、二重測定を避ける。
    if parameter_json in seen:
        duplicates += 1
        return
    seen.add(parameter_json)
    rows.append({
        "proposal_id": "", "family": family, "description": desc,
        "parameter_json": parameter_json,
    })


# 台地判定の基準点をPB2001に固定し、P1のH1案も兼ねる。
add("P1_timeframe", "H1中心点（H4版PB GOLDの設定をH1に適用）")
for tf in (30, 60, 120, 240):
    desc = "H4対照（既存PB GOLDとの健全性確認）" if tf == 240 else f"時間軸{tf}分"
    add("P1_timeframe", desc, Pb2TFMinutes=tf)

for rr in (1.2, 1.5, 2.2, 2.6, 3.0):
    add("P2_rr", f"RR{rr}（中心1.8）", Pb2RR=rr)

for atr in (1.2, 1.6, 2.5, 3.0):
    add("P3_atr_stop", f"ATRストップ幅{atr}（中心2.0）", Pb2ATRSLmult=atr)

for adx in (15.0, 20.0, 27.5, 32.0):
    add("P4_adx", f"ADX閾値{adx}（中心22.5）", Pb2ADXThr=adx)

for slope in (0.6, 0.9, 1.6, 2.0):
    add("P5_slope", f"トレンド傾き下限{slope}ATR（中心1.2）", Pb2SlopeMinATR=slope)

for bars in (0, 16, 32, 128, 256):
    add("P6_hold", f"保有上限{bars}バー（0は無効・中心64）", Pb2HoldBars=bars)

for tf in (30, 60, 120):
    add("P7_hour_gate", f"時間軸{tf}分・H4版の時間帯ゲート適用",
        Pb2TFMinutes=tf, Pb2UseHourGate=True)

for tf in (30, 60, 120):
    for rr in (1.5, 2.2, 2.6):
        add("P8_timeframe_x_rr", f"時間軸{tf}分 × RR{rr}",
            Pb2TFMinutes=tf, Pb2RR=rr)

for tf in (30, 60, 120):
    for atr in (1.6, 2.5):
        add("P9_timeframe_x_atr", f"時間軸{tf}分 × ATRストップ幅{atr}",
            Pb2TFMinutes=tf, Pb2ATRSLmult=atr)

for adx in (20.0, 27.5):
    for slope in (0.9, 1.6):
        for rr in (1.8, 2.2):
            add("P10_refine", f"ADX{adx} × 傾き{slope}ATR × RR{rr}",
                Pb2ADXThr=adx, Pb2SlopeMinATR=slope, Pb2RR=rr)


if __name__ == "__main__":
    for n, row in enumerate(rows, start=1):
        row["proposal_id"] = f"PB2{n:03d}"

    assert json.loads(rows[0]["parameter_json"]) == DEFAULTS
    assert len(rows) == len(seen) == 47, len(rows)
    assert duplicates == 6, duplicates
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"生成: {len(rows)} 件 -> {OUT}")
    print(f"重複: 出力0件（候補から{duplicates}件除外）")
    print()
    for fam, count in Counter(r["family"] for r in rows).items():
        print(f"{fam:<22}{count:>5}")
