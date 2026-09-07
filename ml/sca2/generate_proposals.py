"""SCA GOLD 第2セッションの提案を生成する。

## 発端

SCA GOLD は IS 242取引で GOLD の取引数の8割を占める主力枠だが、
**1日1レンジ（1-9時）しか使っておらず、米国時間帯のレンジは丸ごと未利用**。
GOLD の弱点は「630取引/10年＝月5.5回」という薄さで、取引数を増やすこと自体に価値がある。

docs/rejected_strategies.md に第2セッションの検討記録は無い（完全に未検討）。
既存パラメータの最適化ではなく新しい収益源の追加であり、
これまで全滅した「決済側の後付け」「サイジング」とは別軸である。

## 探索軸

第1セッションは Range 1-9h / 締切15h / 強制決済20h。第2セッションは
その後ろ（欧州後半〜米国時間）に置く。GOLDは米国時間に動くので素直な仮説。

1. レンジ窓の位置と長さ（9-11h, 11-13h, 13-15h, 13-16h, 14-16h, 15-17h ...）
2. 締切と強制決済（レンジ確定からどれだけ取引時間を残すか）
3. レンジ幅フィルタ（MinRange/MaxRange）— 第1と同じ 0.40/1.00 が最適とは限らない
4. RR
5. リバーサルBoost の有無（第1では -10,704円 の事故を起こした機構）

## 判定

第2セッション枠（magic 20261003）だけを見ても意味がない。**GOLD 2枠の合計**で
純益とDDがどう動くかで判定する。取引が増えればDDも増えるのが自然なので、
固定ロットの倍率を上げた場合と同じ効率（純益倍率÷DD倍率）で比較する。
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
    "Sca2MinRange": 0.40, "Sca2MaxRange": 1.00, "Sca2Buffer": 0.05,
    "Sca2RR": 1.7, "Sca2SkipFriday": True,
    "Sca2RevBoost": True, "Sca2BoostMult": 2.0, "Sca2Lot": 0.01,
}

rows = []


def add(family, desc, **params):
    p = dict(DEFAULTS)
    p.update(params)
    # レンジ確定より締切が後、締切より強制決済が後、でなければ成立しない
    assert p["Sca2RangeStart"] < p["Sca2RangeEnd"] < p["Sca2TradeEnd"] < p["Sca2ForceClose"], desc
    rows.append({
        "proposal_id": "",
        "family": family,
        "description": desc,
        "parameter_json": json.dumps(p, ensure_ascii=False, sort_keys=True),
    })


# --- S01 レンジ窓の位置と長さ（本ラウンドの主軸）----------------------- 16
WINDOWS = [
    (9, 11), (9, 12), (9, 13),
    (11, 13), (11, 14), (11, 15),
    (12, 14), (12, 15), (12, 16),
    (13, 15), (13, 16), (13, 17),
    (14, 16), (14, 17),
    (15, 17), (15, 18),
]
for a, b in WINDOWS:
    add("S01_window", f"第2レンジ {a}-{b}時（締切20h・決済23h）",
        Sca2RangeStart=a, Sca2RangeEnd=b)

# --- S02 締切と強制決済（レンジ13-15hを固定して時間配分を探る）--------- 11
# (20,23) は既定値そのもので S01 の 13-15h と重複するため除く
for te, fc in [(17, 20), (17, 22), (18, 21), (18, 23), (19, 22), (19, 23),
               (20, 22), (21, 23), (16, 19), (16, 22), (22, 23)]:
    add("S02_timing", f"第2レンジ13-15時・締切{te}h・強制決済{fc}h",
        Sca2TradeEnd=te, Sca2ForceClose=fc)

# --- S03 レンジ幅フィルタ ---------------------------------------------- 10
for mn, mx in [(0.20, 1.00), (0.30, 1.00), (0.50, 1.00), (0.60, 1.20),
               (0.40, 0.80), (0.40, 1.50), (0.40, 2.00), (0.25, 0.75),
               (0.30, 1.50), (0.50, 2.00)]:
    add("S03_range_filter", f"レンジ幅 {mn}〜{mx}ATR（既定0.40〜1.00）",
        Sca2MinRange=mn, Sca2MaxRange=mx)

# --- S04 RR -------------------------------------------------------------- 8
for rr in (1.0, 1.3, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
    add("S04_rr", f"第2セッションのRRを{rr}に（既定1.7）", Sca2RR=rr)

# --- S05 ブレイク判定バッファ -------------------------------------------- 6
for buf in (0.0, 0.02, 0.10, 0.15, 0.20, 0.30):
    add("S05_buffer", f"ブレイクバッファ {buf}ATR（既定0.05）", Sca2Buffer=buf)

# --- S06 リバーサルBoost（第1で -10,704円 の事故を起こした機構）--------- 6
add("S06_boost", "Boostなし（等ロット）", Sca2RevBoost=False)
for m in (1.5, 2.5, 3.0, 4.0):
    add("S06_boost", f"Boost倍率 {m}（既定2.0）", Sca2BoostMult=m)
add("S06_boost", "Boostなし＋金曜も取引", Sca2RevBoost=False, Sca2SkipFriday=False)

# --- S07 金曜の扱い ------------------------------------------------------ 1
add("S07_friday", "金曜も取引する（既定はスキップ）", Sca2SkipFriday=False)

# --- S08 有力窓 × RR の交差（S01で当たりが出た近傍を面で見るための先行分）-- 12
# (13,15) は既定窓で S04 の RR 掃引と重複するため除く
for a, b in [(11, 13), (13, 16), (12, 15)]:
    for rr in (1.3, 2.0, 2.5, 3.0):
        add("S08_window_x_rr", f"第2レンジ{a}-{b}時 × RR{rr}",
            Sca2RangeStart=a, Sca2RangeEnd=b, Sca2RR=rr)


if __name__ == "__main__":
    for n, row in enumerate(rows, start=1):
        row["proposal_id"] = f"S2{n:03d}"

    seen = {}
    for row in rows:
        if row["parameter_json"] in seen:
            raise SystemExit(f"重複: {row['proposal_id']} と {seen[row['parameter_json']]}")
        seen[row["parameter_json"]] = row["proposal_id"]

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
