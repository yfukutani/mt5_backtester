"""SCA枠のrisk%化を初めて実効化した状態で測り直すための比較条件。

【なぜ第2ラウンドが必要か】
fxrisk1（88run）は `FxRiskMask` の bit3/bit4（SCA USDJPY / SCA GBPJPY）を
立てて測っていたが、**SCAの発注経路は LotRisk() を通らず固定ロットを直接
計算していたため、bit3/bit4 は一度も効いていなかった。**
実測の証拠は fxrisk1/results.csv にある——R008(mask=8)・R009(mask=16)・
R016〜R021(mask=24) が、mask=0 の R003 と純益・最大DD・取引数まで完全一致する。

2026-09-15 に `ScaBaseLot()` を入れて修正した（experts/MIX_EA_SIMVERIFY.mq5）。
本ラウンドは**SCAが実際に risk% サイジングされる状態での初回測定**である。

【SCA の注意】SCA GBPJPY は `scaBoostMult=6.0`（ドリフト逆行時のロット6倍）を
持つ。risk% 化するとブースト取引の実効リスクは risk%×6 になるので、
fxrisk1 が使った 0.25〜1.0% では過大になりうる。0.05% から並べる。

【RSI枠は再測定しない】修正は SCA の発注経路にしか触れていないため、
mask が bit0〜2 のみの案（fxrisk1 の A/B/C/H-RSI群）の結果はそのまま有効。
S001/S002 は「修正が SCA 以外に影響していないこと」を確かめる対照で、
それぞれ fxrisk1 の R003 / R013 と**完全一致しなければならない。**
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["proposal_id", "family", "description", "parameter_json"]
MULTS = tuple("Mult_" + s for s in (
    "PB_USDJPY", "PB_GBPJPY", "PB_GOLD", "RSI_USDJPY", "RSI_EURUSD",
    "RSI_GBPUSD", "PAIR", "CARRY", "VBO", "ETH", "BTC_FUND", "BFXREV",
    "SCA_GOLD", "SCA_USDJPY", "SCA_GBPJPY"))
REFCAPS = ("RefCap_PB_USDJPY", "RefCap_PB_GBPJPY", "RefCap_CARRY")
LAB = ("FxRiskMask", "FxRiskPct", "FxRiskRefCap")


def parameters(raw):
    p = json.loads(raw)
    if not isinstance(p, dict) or set(p) != {*MULTS, *REFCAPS, *LAB, "GlobalLotMult"}:
        raise ValueError("比較軸以外の変更、またはパラメータの指定漏れがあります")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in p.values()):
        raise ValueError("パラメータは有限の数値にしてください")
    if not isinstance(p["FxRiskMask"], int) or not 0 <= p["FxRiskMask"] <= 31:
        raise ValueError("FxRiskMaskは0〜31の整数にしてください")
    if p["FxRiskPct"] <= 0 or p["FxRiskRefCap"] < 0:
        raise ValueError("FxRiskPctは正、FxRiskRefCapは非負にしてください")
    if len({p[k] for k in REFCAPS}) != 1 or p[REFCAPS[0]] < 0:
        raise ValueError("3枠のRefCapは同一の非負値にしてください")
    if p["GlobalLotMult"] not in (1, 2, 3):
        raise ValueError("倍率は1・2・3のいずれかにしてください")
    if any(p[k] != 1.0 for k in MULTS):
        raise ValueError("サイジング軸の効果を分離するため、枠別重みは1.0に固定してください")
    return p


def generate():
    rows = []
    seen = set()

    def add(family, mask, risk, fxref, refcap, mult):
        p = dict.fromkeys(MULTS, 1.0)
        p.update(dict.fromkeys(REFCAPS, refcap))
        p.update(FxRiskMask=mask, FxRiskPct=risk, FxRiskRefCap=fxref, GlobalLotMult=mult)
        raw = json.dumps(p, sort_keys=True, separators=(",", ":"))
        parameters(raw)
        if raw in seen:
            return
        seen.add(raw)
        rows.append(dict(
            proposal_id=f"S{len(rows) + 1:03d}", family=family,
            description=(f"マスク={mask} / risk%={risk:g} / FxRiskRefCap={fxref} "
                         f"/ RefCap={refcap} / 倍率={mult}"),
            parameter_json=raw))

    # A: 対照。S001は fxrisk1 R003、S002は R013 と完全一致するはず（修正の無影響確認）。
    #    S001が先頭なのは、各窓の破綻判定基準を後続案より先に取得するため。
    add("A", 0, 0.5, 0, 250000, 1)
    add("A", 7, 0.5, 0, 250000, 1)

    # B: SCAを1枠ずつ。どちらの枠がどれだけ効くかを分離する。
    for mask in (8, 16):
        for risk in (0.05, 0.1, 0.25):
            add("B", mask, risk, 250000, 250000, 1)

    # C: SCA 2枠。fxrefで「単なる増量」と「複利」を分ける。
    for risk in (0.05, 0.1, 0.25, 0.5):
        add("C", 24, risk, 250000, 250000, 1)
    for risk in (0.1, 0.25):
        add("C", 24, risk, 0, 250000, 1)

    # D: RSI3枠＋SCA2枠。非複利（fxref固定）で増量効果だけを見る。
    for risk in (0.05, 0.1, 0.25, 0.5):
        add("D", 31, risk, 250000, 250000, 1)

    # E: 5枠を equity 連動に。既存3枠は RefCap=250000 のまま。
    for risk in (0.05, 0.1, 0.25):
        add("E", 31, risk, 0, 250000, 1)

    # F: 9枠中8枠が equity 連動（Pairのみ固定）＝最大複利。破綻リスクが最も高い。
    for risk in (0.05, 0.1, 0.25, 0.5):
        add("F", 31, risk, 0, 0, 1)

    # G: 最大複利に全体倍率を重ねる。fxrisk1ではここ（R037相当）がOOS最良だった。
    for risk, mult in ((0.05, 3), (0.1, 2), (0.1, 3), (0.25, 2), (0.25, 3)):
        add("G", 31, risk, 0, 0, mult)

    return rows


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError("proposals.csvのヘッダーが一致しません")
        rows = list(reader)
    expected = {r["proposal_id"]: r for r in generate()}
    if len(rows) != len(expected) or {r["proposal_id"] for r in rows} != set(expected):
        raise ValueError(f"S001〜S{len(expected):03d}の{len(expected)}案すべてが必要です")
    for r in rows:
        e = expected[r["proposal_id"]]
        if (parameters(r["parameter_json"]) != parameters(e["parameter_json"])
                or any(r[k] != e[k] for k in ("family", "description"))):
            raise ValueError(f"{r['proposal_id']}の設定または説明が設計と異なります")
    return rows


def main():
    rows = generate()
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(ROOT / "proposals.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    duplicates = len(rows) - len({r["parameter_json"] for r in rows})
    print(f"総数={len(rows)} / 内訳={dict(Counter(r['family'] for r in rows))} / 重複={duplicates}")


if __name__ == "__main__":
    main()
