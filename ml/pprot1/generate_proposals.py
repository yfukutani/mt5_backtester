"""利益保護ラウンド1の提案500件を生成する。

## 設計根拠（ml/pprot1/analyze_baseline.py の実測・IS 2021-2026）

PB GOLD  59取引 / 負け24件は **全件が実現 -1.00R**（当初SLちょうど）。損失計 -112,772円。
         勝ちは中央 +1.80R（TP到達）。保有中央56h・90%点169.5h。初期リスク中央22.68USD。
         → 「TPかSLか」の二値構造。利益保護の余地が最も大きいのはここ。
SCA GOLD 242取引 / 負け108件のうちSL決済は28件(11.6%)のみ・中央 -0.44R。
         勝ちも中央 +0.48R とTP(1.7R)に遠い。保有中央8.5h・max10.8h。
         → SLで死ぬ問題ではなく20:00強制決済で途中で切られる問題。守りより利確側。

PB GOLD は H4 枠（ATR SL 2.0 倍 → 1ATR ≈ 11.3USD ≈ 0.5R）。
SCA GOLD は M15 枠。ArmAfterBars/TightenBars は枠のTF単位で与える。

## 過去に否定済みで、繰り返さない条件

固定pipsのBE/トレール（v2.7/v2.8）、残高%連動の利益トレール（2026-08-05・全水準悪化）、
R基準のみのBE/トレール/giveback/部分利確（oafx_dd2・1000案・採用ゼロ）。
本ラウンドは **ATR基準** と **武装条件（いつ守りに入るか）** を主たる設計変数にする。
R基準は対照群として F02 に少数だけ残し、ATR基準との差を測れるようにする。
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "proposals.csv"

# 枠マスク: bit0=PB GOLD, bit1=SCA GOLD
TARGETS = {"G1": (1, "PB GOLD"), "G2": (2, "SCA GOLD"), "G3": (3, "GOLD 2枠")}

# 既定値（EA側の「未使用」表現に合わせる）
DEFAULTS = {
    "PprotSleeveMask": 0,
    "PprotArmPeakATR": 0.0, "PprotArmPeakR": 0.0,
    "PprotArmAfterBars": 0, "PprotArmBeforeBars": 0,
    "PprotArmMinATRRatio": 0.0, "PprotArmMaxATRRatio": 0.0,
    "PprotArmHourStart": -1, "PprotArmHourEnd": -1,
    "PprotBELockATR": -9.0, "PprotBELockR": -9.0,
    "PprotTrailATR": 0.0, "PprotTrailPeakATR": 0.0,
    "PprotGivebackFrac": 0.0, "PprotGivebackATR": 0.0,
    "PprotPartialLots": 0.0,
    "PprotTightenBars": 0, "PprotTightenSLATR": 0.0,
    "PprotTPExtendATR": 0.0,
    "PprotFridayHour": -1, "PprotFridayMinATR": 0.0,
}

FAMILIES = {
    "F01_be_atr":            1, "F02_be_r":              2,
    "F03_trail_atr":         3, "F04_trail_peak":        4,
    "F05_giveback_frac":     5, "F06_giveback_atr":      6,
    "F07_be_then_trail":     7, "F08_age_conditioned_be": 8,
    "F09_age_tighten":       9, "F10_vol_conditioned_be": 10,
    "F11_hour_conditioned_be": 11, "F12_early_only_be":  12,
    "F13_partial":          13, "F14_tp_extend":        14,
    "F15_friday_lock":      15, "F16_trail_after_age":  16,
    "F17_giveback_after_age": 17,
}

rows = []


def add(family, target, desc, **params):
    mask, tname = TARGETS[target]
    p = dict(DEFAULTS)
    p["PprotMode"] = FAMILIES[family]
    p["PprotSleeveMask"] = mask
    p.update(params)
    rows.append({
        "proposal_id": "",           # 後で連番を振る
        "family": family,
        "target": target,
        "target_name": tname,
        "description": f"{tname}: {desc}",
        "parameter_json": json.dumps(p, ensure_ascii=False, sort_keys=True),
    })


ALL = ["G1", "G2", "G3"]

# --- F01 ATR基準の建値移動（本ラウンドの主役） -------------------------- 63
for t in ALL:
    for arm in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        for lock in (0.0, 0.1, 0.25):
            add("F01_be_atr", t,
                f"ピーク含み益{arm}ATRで建値+{lock}ATRへSL移動",
                PprotArmPeakATR=arm, PprotBELockATR=lock)

# --- F02 R基準の建値移動（ATR基準との対照群） --------------------------- 24
for t in ALL:
    for arm in (0.3, 0.5, 0.75, 1.0):
        for lock in (0.0, 0.1):
            add("F02_be_r", t,
                f"ピーク{arm}Rで建値+{lock}RへSL移動（R基準・対照）",
                PprotArmPeakR=arm, PprotBELockR=lock)

# --- F03 現値追従トレール ----------------------------------------------- 45
for t in ALL:
    for arm in (0.5, 1.0, 1.5):
        for tr in (0.75, 1.0, 1.5, 2.0, 2.5):
            add("F03_trail_atr", t,
                f"ピーク{arm}ATR到達後、現値から{tr}ATRでトレール",
                PprotArmPeakATR=arm, PprotTrailATR=tr)

# --- F04 ピーク基準トレール（チャンデリア） ------------------------------ 36
for t in ALL:
    for arm in (0.5, 1.0, 1.5):
        for tr in (0.5, 0.75, 1.0, 1.5):
            add("F04_trail_peak", t,
                f"ピーク{arm}ATR到達後、ピークから{tr}ATRでトレール",
                PprotArmPeakATR=arm, PprotTrailPeakATR=tr)

# --- F05 吐き出し割合キャップ -------------------------------------------- 36
for t in ALL:
    for arm in (0.5, 1.0, 1.5):
        for fr in (0.3, 0.4, 0.5, 0.6):
            add("F05_giveback_frac", t,
                f"ピーク{arm}ATR到達後、ピーク益の{int(fr*100)}%を戻したら決済",
                PprotArmPeakATR=arm, PprotGivebackFrac=fr)

# --- F06 吐き出し幅キャップ（ATR） --------------------------------------- 36
for t in ALL:
    for arm in (0.5, 1.0, 1.5):
        for gb in (0.25, 0.5, 0.75, 1.0):
            add("F06_giveback_atr", t,
                f"ピーク{arm}ATR到達後、ピークから{gb}ATR戻したら決済",
                PprotArmPeakATR=arm, PprotGivebackATR=gb)

# --- F07 建値移動→トレールの二段 ----------------------------------------- 36
for t in ("G1", "G3"):
    for arm in (0.5, 1.0, 1.5):
        for lock in (0.0, 0.1):
            for tr in (1.0, 1.5, 2.0):
                add("F07_be_then_trail", t,
                    f"ピーク{arm}ATRで建値+{lock}ATRへ、以後{tr}ATRトレール",
                    PprotArmPeakATR=arm, PprotBELockATR=lock, PprotTrailATR=tr)

# --- F08 保有時間条件つき建値移動（実測「長期保有で吐き出す」に直結） ------ 27
for bars in (6, 12, 18, 24, 36):          # H4 → 24/48/72/96/144時間
    for arm in (0.25, 0.5, 0.75):
        add("F08_age_conditioned_be", "G1",
            f"保有{bars}バー(H4={bars*4}h)以降かつピーク{arm}ATRで建値へ",
            PprotArmAfterBars=bars, PprotArmPeakATR=arm, PprotBELockATR=0.0)
for bars in (8, 16, 24, 32):              # M15 → 2/4/6/8時間
    for arm in (0.25, 0.5, 0.75):
        add("F08_age_conditioned_be", "G2",
            f"保有{bars}バー(M15={bars*15//60}h)以降かつピーク{arm}ATRで建値へ",
            PprotArmAfterBars=bars, PprotArmPeakATR=arm, PprotBELockATR=0.0)

# --- F09 保有経過によるSL圧縮（採用済み保有上限64バーの連続版） ----------- 30
for bars in (8, 12, 16, 24, 32, 48):
    for sl in (0.5, 1.0, 1.5):
        add("F09_age_tighten", "G1",
            f"保有{bars}バー(H4={bars*4}h)経過でSLを{sl}ATRまで圧縮",
            PprotTightenBars=bars, PprotTightenSLATR=sl)
for bars in (8, 16, 24, 32):
    for sl in (0.5, 1.0, 1.5):
        add("F09_age_tighten", "G2",
            f"保有{bars}バー(M15={bars*15//60}h)経過でSLを{sl}ATRまで圧縮",
            PprotTightenBars=bars, PprotTightenSLATR=sl)

# --- F10 ボラ局面条件つき建値移動 ---------------------------------------- 30
VOL = [("高ボラ時のみ", {"PprotArmMinATRRatio": 1.1}),
       ("高ボラ時のみ", {"PprotArmMinATRRatio": 1.25}),
       ("高ボラ時のみ", {"PprotArmMinATRRatio": 1.5}),
       ("低ボラ時のみ", {"PprotArmMaxATRRatio": 0.9}),
       ("低ボラ時のみ", {"PprotArmMaxATRRatio": 0.75})]
for t in ALL:
    for label, cond in VOL:
        for arm in (0.5, 1.0):
            v = list(cond.values())[0]
            add("F10_vol_conditioned_be", t,
                f"{label}(ATR比{v})かつピーク{arm}ATRで建値へ",
                PprotArmPeakATR=arm, PprotBELockATR=0.0, **cond)

# --- F11 時間帯条件つき建値移動 ------------------------------------------ 30
HOURS = [(0, 7), (8, 15), (16, 23), (12, 20), (20, 3)]
for t in ALL:
    for hs, he in HOURS:
        for arm in (0.5, 1.0):
            add("F11_hour_conditioned_be", t,
                f"{hs}-{he}時のみ武装しピーク{arm}ATRで建値へ",
                PprotArmPeakATR=arm, PprotBELockATR=0.0,
                PprotArmHourStart=hs, PprotArmHourEnd=he)

# --- F12 保有初期のみ武装（時間条件の逆側・対照） ------------------------- 12
for t, bars_list in (("G1", (6, 12, 24)), ("G2", (8, 16, 24))):
    for bars in bars_list:
        for arm in (0.5, 1.0):
            add("F12_early_only_be", t,
                f"保有{bars}バー以内に限り、ピーク{arm}ATRで建値へ（対照）",
                PprotArmBeforeBars=bars, PprotArmPeakATR=arm, PprotBELockATR=0.0)

# --- F13 部分利確 -------------------------------------------------------- 12
for t in ALL:
    for arm in (0.5, 0.75, 1.0, 1.5):
        add("F13_partial", t,
            f"ピーク{arm}ATRで0.01ロットを利確（残りは元SLのまま）",
            PprotArmPeakATR=arm, PprotPartialLots=0.01)

# --- F14 利確位置の延長（守りではなく攻め側の対照） ----------------------- 24
for t in ALL:
    for ext in (0.5, 1.0, 1.5, 2.0):
        for arm in (0.5, 1.0):
            add("F14_tp_extend", t,
                f"ピーク{arm}ATR到達でTPを{ext}ATR遠くへ延長",
                PprotArmPeakATR=arm, PprotTPExtendATR=ext)

# --- F15 週末前の利益確定 ------------------------------------------------ 36
for t in ALL:
    for hour in (12, 16, 18, 20):
        for m in (0.25, 0.5, 1.0):
            add("F15_friday_lock", t,
                f"金曜{hour}時以降に含み益{m}ATR以上なら決済",
                PprotFridayHour=hour, PprotFridayMinATR=m)

# --- F16 保有経過後のみトレール ------------------------------------------ 15
for bars in (6, 12, 24):
    for tr in (1.0, 1.5, 2.0):
        add("F16_trail_after_age", "G1",
            f"保有{bars}バー(H4={bars*4}h)以降のみ{tr}ATRトレール",
            PprotArmAfterBars=bars, PprotTrailATR=tr)
for bars in (8, 16, 24):
    for tr in (1.0, 1.5):
        add("F16_trail_after_age", "G2",
            f"保有{bars}バー(M15)以降のみ{tr}ATRトレール",
            PprotArmAfterBars=bars, PprotTrailATR=tr)

# --- F17 保有経過後のみ吐き出しキャップ ----------------------------------- 8
for bars in (6, 12, 24):
    for fr in (0.4, 0.5):
        add("F17_giveback_after_age", "G1",
            f"保有{bars}バー(H4={bars*4}h)以降のみピーク益{int(fr*100)}%戻しで決済",
            PprotArmAfterBars=bars, PprotGivebackFrac=fr)
for bars in (8, 16):
    add("F17_giveback_after_age", "G2",
        f"保有{bars}バー(M15)以降のみピーク益40%戻しで決済",
        PprotArmAfterBars=bars, PprotGivebackFrac=0.4)


if __name__ == "__main__":
    for n, row in enumerate(rows, start=1):
        row["proposal_id"] = f"PP{n:04d}"

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
    print(f"重複なし（パラメータ組合せがすべて一意）")
    print()
    print(f"{'ファミリー':<26}{'件数':>5}")
    for fam, c in sorted(Counter(r["family"] for r in rows).items()):
        print(f"{fam:<26}{c:>5}")
    print()
    print(f"{'対象枠':<12}{'件数':>5}")
    for t, c in sorted(Counter(r["target_name"] for r in rows).items()):
        print(f"{t:<12}{c:>5}")
