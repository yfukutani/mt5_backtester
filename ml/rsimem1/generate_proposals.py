"""未測定の有望さを仮定せず、記憶の寿命と消費を固定した格子で比較する。"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["proposal_id", "family", "description", "parameter_json"]
DEFAULTS = {
    "GlobalLotMult": 1,
    "RsiBBFlagMaxBars": 0, "RsiRSIFlagMaxBars": 0,
    "RsiResetOnMAFlip": False, "RsiConsumeWhileHeld": False,
    "RsiMemSleeveMask": 0,
}


def parameters(raw):
    p = json.loads(raw)
    if not isinstance(p, dict) or set(p) != set(DEFAULTS):
        raise ValueError("ラボ入力と固定倍率の指定に過不足があります")
    if type(p["GlobalLotMult"]) not in (int, float) or p["GlobalLotMult"] != 1:
        raise ValueError("GlobalLotMultは1に固定してください")
    for key in ("RsiBBFlagMaxBars", "RsiRSIFlagMaxBars", "RsiMemSleeveMask"):
        if type(p[key]) is not int or p[key] < 0:
            raise ValueError(f"{key}は非負整数（寿命0は無効）です")
    if p["RsiMemSleeveMask"] > 7:
        raise ValueError("マスクは0〜7です")
    for key in ("RsiResetOnMAFlip", "RsiConsumeWhileHeld"):
        if type(p[key]) is not bool:
            raise ValueError(f"{key}は真偽値です")
    return p


def canonical(p):
    p = dict(p)
    # マスク0と7はEAで同じ効果なので、表記差で重複を見逃さない。
    if p["RsiMemSleeveMask"] == 7 or not any(p[k] for k in (
            "RsiBBFlagMaxBars", "RsiRSIFlagMaxBars", "RsiResetOnMAFlip", "RsiConsumeWhileHeld")):
        p["RsiMemSleeveMask"] = 0
    return json.dumps(p, sort_keys=True, separators=(",", ":"))


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError("提案CSVの列が一致しません")
        rows = list(reader)
    ids, keys = set(), set()
    for i, row in enumerate(rows, 1):
        key = canonical(parameters(row["parameter_json"]))
        if row["proposal_id"] != f"M{i:03d}" or key in keys:
            raise ValueError("案IDの順序が不正、または設定が重複しています")
        ids.add(row["proposal_id"])
        keys.add(key)
    if not rows or parameters(rows[0]["parameter_json"]) != DEFAULTS:
        raise ValueError("M001には全ラボOFFの中心点が必要です")
    return rows


def generate():
    rows, seen = [], set()
    duplicates = 0

    def add(family, description, **changes):
        nonlocal duplicates
        p = dict(DEFAULTS, **changes)
        raw = json.dumps(p, sort_keys=True, separators=(",", ":"))
        key = canonical(parameters(raw))
        if key in seen:
            duplicates += 1
            return
        seen.add(key)
        rows.append(dict(proposal_id=f"M{len(rows)+1:03d}", family=family,
                         description=description, parameter_json=raw))

    add("BASE", "現行・全ラボOFF")
    for family, key, label in (("R1", "RsiRSIFlagMaxBars", "RSI極値"),
                               ("R2", "RsiBBFlagMaxBars", "BB逸脱")):
        for n in (2, 4, 8, 16, 32):
            add(family, f"{label}の寿命{n}本", **{key: n})
    for rsi in (4, 16):
        for bb in (4, 16):
            add("R3", f"RSI寿命{rsi}本・BB寿命{bb}本",
                RsiRSIFlagMaxBars=rsi, RsiBBFlagMaxBars=bb)
    add("R4", "MA反転で失効", RsiResetOnMAFlip=True)
    add("R5", "保有中に消費", RsiConsumeWhileHeld=True)
    for n in (4, 16):
        for flip, held in ((True, False), (False, True), (True, True)):
            add("R6", f"両寿命{n}本・MA反転={flip}・保有中消費={held}",
                RsiRSIFlagMaxBars=n, RsiBBFlagMaxBars=n,
                RsiResetOnMAFlip=flip, RsiConsumeWhileHeld=held)
    for mask, name in ((1, "USDJPY"), (2, "EURUSD"), (4, "GBPUSD")):
        for key, value, label in (
                ("RsiRSIFlagMaxBars", 8, "RSI寿命8本"),
                ("RsiBBFlagMaxBars", 8, "BB寿命8本"),
                ("RsiResetOnMAFlip", True, "MA反転で失効"),
                ("RsiConsumeWhileHeld", True, "保有中消費")):
            add("R7", f"{name}のみ・{label}", RsiMemSleeveMask=mask, **{key: value})
    # 測定結果を見て近傍を選ぶ偏りを避け、細分点も事前に固定する。
    for key, label in (("RsiRSIFlagMaxBars", "RSI"), ("RsiBBFlagMaxBars", "BB")):
        for n in (3, 6, 12, 24):
            add("R8", f"{label}寿命の細分{n}本", **{key: n})
    return rows, duplicates


def main():
    rows, duplicates = generate()
    with open(ROOT / "proposals.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"総数={len(rows)}、内訳={dict(Counter(r['family'] for r in rows))}、重複除外={duplicates}")


if __name__ == "__main__":
    main()
