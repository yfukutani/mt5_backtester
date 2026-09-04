"""SCA GOLD 利確側ラウンド3（scaexit2）— TP最適点の解像度を上げる。

## 答えるべき問い

scaexit1 で「TP延長1.0ATR」が最良（SCA枠 IS +22.6% / OOS +25.3%）と出たが、
応答を並べ直すと台地ではなく**尖ったピーク**だった。

    延長幅   0.5     0.75    1.0     1.5     2.0
    IS      +10.1%  +18.2%  +22.6%  +9.3%   +9.3%

1.5以上はTPが到達不能になった値（＝TP撤廃と同一）なので、実質的な探索範囲は
0.5〜1.5ATR しかなく、そこを4点しか測っていない。**1.0のピークが実在するのか、
たまたま当たった1点なのかを、刻みを細かくして判別する。**

面（台地）であれば隣接点も同程度に良いはずで、点（スパイク）であれば
0.9 や 1.1 で急落する。

## もう一つの軸

TPを絶対ATR距離で置く場合（SxitTPATR）も、到達可能な範囲は 1.0〜2.5ATR しかない。
  1.0 -12.30% / 1.5 +10.71% / 2.0 +9.76% / 2.5以上 +9.34%（到達不能）
ここも刻みが粗いので 1.4〜2.6 を 0.1 刻みで埋める。

## 構造上の限界（これは動かせない）

TP側の施策が触れられるのは「TPに到達する取引」だけで、ISでは242件中15件。
どんな案でも小標本になる。本ラウンドは**その中で形（面か点か）を見る**のが目的であり、
標本を増やすことはできない。判定には集中度と年次一貫性の検査を必ず併用する。
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

PPROT_SCA_MASK = 2
SCA_GOLD_MASK = 1

DEFAULTS = {
    "SxitMode": 0, "SxitSleeveMask": 0,
    "SxitRR": 0.0, "SxitTPATR": 0.0,
    "SxitTradeEndHour": -1, "SxitForceCloseHour": -1,
    "SxitProfitCloseHour": -1, "SxitLossCloseHour": -1,
    "SxitProfitHoldATR": 0.0, "SxitHoldUntilHour": -1,
    "PprotMode": 0, "PprotSleeveMask": 0,
    "PprotArmPeakATR": 0.0, "PprotTPExtendATR": 0.0,
}

FAMILIES = {
    "H01_extend_fine": 1,      # TP延長幅の細刻み（本ラウンドの主目的）
    "H02_tp_atr_fine": 2,      # 絶対ATR距離TPの細刻み
    "H03_rr_fine": 3,          # RRの細刻み
    "H04_extend_x_rr": 4,      # 最適点近傍の交差確認
    "H05_control": 5,          # 無操作対照（基準と一致するはず）
}

rows = []


def add(family, desc, **params):
    p = dict(DEFAULTS)
    p.update(params)
    rows.append({
        "proposal_id": "",
        "family": family,
        "combo": "-",
        "description": desc,
        "parameter_json": json.dumps(p, ensure_ascii=False, sort_keys=True),
    })


def frange(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 3) for i in range(n + 1)]


# --- H01 TP延長幅を 0.50〜1.50 の 0.05 刻みで埋める ----------------------- 21
# 武装水準は scaexit1 で 0.2〜0.8 のあいだ結果が完全同一＝条件が効いていないことが
# 分かっているので 0.5 に固定する（PP0428 と同じ）。
for ext in frange(0.50, 1.50, 0.05):
    add("H01_extend_fine",
        f"ピーク0.5ATR到達でTPを{ext:.2f}ATR延長",
        SxitMode=FAMILIES["H01_extend_fine"], SxitSleeveMask=0,
        PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
        PprotArmPeakATR=0.5, PprotTPExtendATR=ext)

# --- H02 絶対ATR距離TPを 1.40〜2.60 の 0.10 刻みで埋める ------------------ 13
for a in frange(1.40, 2.60, 0.10):
    add("H02_tp_atr_fine",
        f"TPを{a:.2f}ATRの距離に置く",
        SxitMode=FAMILIES["H02_tp_atr_fine"], SxitSleeveMask=SCA_GOLD_MASK,
        SxitTPATR=a)

# --- H03 RRを 1.55〜2.60 の 0.05 刻みで埋める ----------------------------- 22
# scaexit1 では 1.6 で +23.59%(併用)。単独の最適点も細かく見る。
for rr in frange(1.55, 2.60, 0.05):
    add("H03_rr_fine",
        f"RRを{rr:.2f}に変更（現行1.7）",
        SxitMode=FAMILIES["H03_rr_fine"], SxitSleeveMask=SCA_GOLD_MASK,
        SxitRR=rr)

# --- H04 最適点近傍の交差（延長幅 × RR）--------------------------------- 45
for rr in (1.60, 1.70, 1.80, 1.90, 2.00):
    for ext in (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30):
        add("H04_extend_x_rr",
            f"RR{rr:.2f} × ピーク0.5ATRでTPを{ext:.2f}ATR延長",
            SxitMode=FAMILIES["H04_extend_x_rr"], SxitSleeveMask=SCA_GOLD_MASK,
            SxitRR=rr,
            PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
            PprotArmPeakATR=0.5, PprotTPExtendATR=ext)

# --- H05 無操作対照（測定系が壊れていないことの確認）---------------------- 2
# ラボはONだが実効パラメータは全て既定＝基準と1円も違わないはず。
add("H05_control", "【対照】ラボONだが実効変更なし（基準と一致するはず）",
    SxitMode=FAMILIES["H05_control"], SxitSleeveMask=SCA_GOLD_MASK)
add("H05_control", "【対照】TP延長0（基準と一致するはず）",
    SxitMode=FAMILIES["H05_control"], SxitSleeveMask=0,
    PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
    PprotArmPeakATR=0.5, PprotTPExtendATR=0.0)


if __name__ == "__main__":
    for n, row in enumerate(rows, start=1):
        row["proposal_id"] = f"HX{n:04d}"

    seen = {}
    for row in rows:
        key = row["parameter_json"]
        if key in seen:
            raise SystemExit(f"重複: {row['proposal_id']} と {seen[key]}")
        seen[key] = row["proposal_id"]

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"生成: {len(rows)} 件 -> {OUT}")
    print("重複なし")
    print()
    print(f"{'ファミリー':<22}{'件数':>5}")
    for fam, c in sorted(Counter(r["family"] for r in rows).items()):
        print(f"{fam:<22}{c:>5}")
