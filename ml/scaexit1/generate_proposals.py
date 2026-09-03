"""SCA GOLD 利確側ラウンド（scaexit1）の提案を生成する。

## 発端

pprot1 で「SCA GOLD は含み益を守る問題ではなく、利確位置の問題」と判明した。

  SCA GOLD 242取引（IS）  TP到達 15件 / SL到達 28件 / 20:00強制決済 199件
  利益 193,974円のうち 156,169円（83%）が強制決済由来。TP(1.7R)は事実上機能していない。
  唯一通った PP0428（ピーク0.5ATRでTPを1.0ATR延長）は SCA枠を +22.5%(IS) / +24.8%(OOS) 改善し、
  機序は「TP到達は15→8件に減るが、届いた8件が +1.70R → +2.35R に伸びる」だった。

つまり **TP(1.7R)は、到達できるほど強い動きに対しては近すぎる**。
本ラウンドはその周辺を直接掃引する。

## 掃引する軸

1. RR そのもの（1.7 は pprot1 以前の最適化で採用された値で、TP延長を知らない状態の最適点）
2. TPの置き方（RR×SL幅ではなく ATR×係数）
3. 強制決済時刻（199件がここで決済される最大のレバー）
4. 含み益/含み損で決済時刻を分ける（勝ちは伸ばし負けは早く切る／その逆も対照として測る）
5. エントリー締切（TP到達には「その日に残り時間があるか」が効く）
6. 上記 × PP0428（採用候補）との併用

**PP0428 との併用を必ず対にする。** 単独で効いても併用で消えるなら実運用では意味がなく、
逆に併用でしか出ない効果もありうる。ユーザー指示「新案が出た際にそちらと合わせて行う」に対応する。
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

SCA_GOLD_MASK = 1          # SxitSleeveMask bit0
PPROT_SCA_MASK = 2         # PprotSleeveMask bit1（pprot1と同じ）

# 既定値（EA側の「未使用」表現に一致させる）
DEFAULTS = {
    "SxitMode": 0, "SxitSleeveMask": 0,
    "SxitRR": 0.0, "SxitTPATR": 0.0,
    "SxitTradeEndHour": -1, "SxitForceCloseHour": -1,
    "SxitProfitCloseHour": -1, "SxitLossCloseHour": -1,
    "SxitProfitHoldATR": 0.0, "SxitHoldUntilHour": -1,
    # PP0428（採用候補）の設定。併用時のみ入れる。
    "PprotMode": 0, "PprotSleeveMask": 0,
    "PprotArmPeakATR": 0.0, "PprotTPExtendATR": 0.0,
}

PP0428 = {
    "PprotMode": 14, "PprotSleeveMask": PPROT_SCA_MASK,
    "PprotArmPeakATR": 0.5, "PprotTPExtendATR": 1.0,
}

FAMILIES = {
    "G01_rr_sweep": 1,
    "G02_force_close_hour": 2,
    "G03_hold_winners": 3,
    "G04_cut_losers_early": 4,
    "G05_tp_atr": 5,
    "G06_trade_end_hour": 6,
    "G07_tp_extend_grid": 7,
    "G08_rr_x_tp_extend": 8,
    "G09_force_close_x_tp_extend": 9,
}

rows = []


def add(family, desc, with_pp0428, **params):
    p = dict(DEFAULTS)
    p["SxitMode"] = FAMILIES[family]
    p["SxitSleeveMask"] = SCA_GOLD_MASK
    p.update(params)
    if with_pp0428:
        p.update(PP0428)
    rows.append({
        "proposal_id": "",
        "family": family,
        "combo": "PP0428併用" if with_pp0428 else "単独",
        "description": f"{desc}{'（＋PP0428）' if with_pp0428 else ''}",
        "parameter_json": json.dumps(p, ensure_ascii=False, sort_keys=True),
    })


def both(family, desc, **params):
    """単独と PP0428 併用を対で作る。"""
    add(family, desc, False, **params)
    add(family, desc, True, **params)


# --- G01 RR の再掃引（現行1.7）------------------------------------------ 24
for rr in (1.0, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0, 4.0):
    both("G01_rr_sweep", f"RRを{rr}に変更（現行1.7）", SxitRR=rr)

# --- G02 強制決済時刻（現行20時・199件がここで決済される）---------------- 18
for h in (16, 17, 18, 19, 21, 22, 23):
    both("G02_force_close_hour", f"強制決済を{h}時に変更（現行20時）", SxitForceCloseHour=h)
for h in (21, 22):   # 締切も後ろにずらす組合せ
    both("G02_force_close_hour", f"強制決済{h}時＋エントリー締切17時",
         SxitForceCloseHour=h, SxitTradeEndHour=17)

# --- G03 含み益なら保有を延長（勝ちを伸ばす）------------------------------ 30
for until in (21, 22, 23):
    for min_atr in (0.25, 0.5, 0.75, 1.0):
        both("G03_hold_winners",
             f"含み益{min_atr}ATR以上なら{until}時まで保有延長",
             SxitProfitHoldATR=min_atr, SxitHoldUntilHour=until)
# 含み益なら一律で延長（しきい値なし＝時刻だけずらす対照）
for until in (21, 22, 23):
    both("G03_hold_winners", f"含み益があれば{until}時まで保有延長（しきい値なし）",
         SxitProfitCloseHour=until)

# --- G04 含み損は早く切る（負けを短くする）-------------------------------- 16
for h in (12, 14, 16, 17, 18):
    both("G04_cut_losers_early", f"含み損なら{h}時に決済（含み益は20時のまま）",
         SxitLossCloseHour=h)
# 逆側の対照: 含み益を早く切り含み損を引っ張る（期待値を下げる向き。効かないことの確認用）
for h in (14, 16, 18):
    both("G04_cut_losers_early", f"【対照】含み益なら{h}時に決済（含み損は20時のまま）",
         SxitProfitCloseHour=h)

# --- G05 TPをATR基準で置く（RR×SL幅をやめる）----------------------------- 24
for a in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0):
    both("G05_tp_atr", f"TPを{a}ATRの距離に置く（RR基準をやめる）", SxitTPATR=a)

# --- G06 エントリー締切（現行15時）--------------------------------------- 14
for h in (10, 11, 12, 13, 14, 16, 17):
    both("G06_trade_end_hour", f"エントリー締切を{h}時に変更（現行15時）", SxitTradeEndHour=h)

# --- G07 TP延長グリッドの細分化（PP0428近傍を面で確認）-------------------- 28
for arm in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
    for ext in (0.75, 1.0, 1.25, 1.5):
        add("G07_tp_extend_grid",
            f"ピーク{arm}ATR到達でTPを{ext}ATR延長", False,
            SxitMode=FAMILIES["G07_tp_extend_grid"], SxitSleeveMask=0,
            PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
            PprotArmPeakATR=arm, PprotTPExtendATR=ext)

# --- G08 RR × TP延長 の組合せ -------------------------------------------- 15
for rr in (1.4, 1.7, 2.0, 2.5, 3.0):
    for ext in (0.5, 1.0, 1.5):
        add("G08_rr_x_tp_extend",
            f"RR{rr} × ピーク0.5ATRでTPを{ext}ATR延長", False,
            SxitMode=FAMILIES["G08_rr_x_tp_extend"], SxitSleeveMask=SCA_GOLD_MASK,
            SxitRR=rr,
            PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
            PprotArmPeakATR=0.5, PprotTPExtendATR=ext)

# --- G09 強制決済の延長 × TP延長 ----------------------------------------- 18
for h in (21, 22, 23):
    for ext in (0.5, 1.0, 1.5):
        add("G09_force_close_x_tp_extend",
            f"強制決済{h}時 × ピーク0.5ATRでTPを{ext}ATR延長", False,
            SxitMode=FAMILIES["G09_force_close_x_tp_extend"], SxitSleeveMask=SCA_GOLD_MASK,
            SxitForceCloseHour=h,
            PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
            PprotArmPeakATR=0.5, PprotTPExtendATR=ext)
for h in (21, 22, 23):
    for min_atr in (0.25, 0.5, 0.75):
        add("G09_force_close_x_tp_extend",
            f"含み益{min_atr}ATRで{h}時まで延長 × TPを1.0ATR延長", False,
            SxitMode=FAMILIES["G09_force_close_x_tp_extend"], SxitSleeveMask=SCA_GOLD_MASK,
            SxitProfitHoldATR=min_atr, SxitHoldUntilHour=h,
            PprotMode=14, PprotSleeveMask=PPROT_SCA_MASK,
            PprotArmPeakATR=0.5, PprotTPExtendATR=1.0)


if __name__ == "__main__":
    for n, row in enumerate(rows, start=1):
        row["proposal_id"] = f"SX{n:04d}"

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
    print(f"{'ファミリー':<32}{'件数':>5}")
    for fam, c in sorted(Counter(r["family"] for r in rows).items()):
        print(f"{fam:<32}{c:>5}")
    print()
    for combo, c in sorted(Counter(r["combo"] for r in rows).items()):
        print(f"{combo:<32}{c:>5}")
