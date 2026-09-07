"""ロット丸めを推定せず、指定された実測点だけを生成する。"""
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


def parameters(raw):
    p = json.loads(raw)
    if set(p) != {*MULTS, "GlobalLotMult"}:
        raise ValueError("倍率以外の変更、または倍率の指定漏れがあります")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or v <= 0 for v in p.values()):
        raise ValueError("倍率は有限の正数にしてください")
    return p


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids, keys = set(), set()
    for r in rows:
        key = json.dumps(parameters(r["parameter_json"]), sort_keys=True)
        if r["proposal_id"] in ids or key in keys:
            raise ValueError("案IDまたはパラメータが重複しています")
        ids.add(r["proposal_id"])
        keys.add(key)
    if not rows:
        raise ValueError("案がありません")
    return rows


def generate():
    rows, seen = [], set()
    duplicates = 0

    def add(family, mult, **weights):
        nonlocal duplicates
        p = dict.fromkeys(MULTS, 1.0)
        p.update(weights, GlobalLotMult=float(mult))
        raw = json.dumps(p, sort_keys=True, separators=(",", ":"))
        parameters(raw)
        if raw in seen:
            duplicates += 1
            return
        seen.add(raw)
        desc = "、".join(f"{k}={v:g}" for k, v in weights.items()) or "全枠の重み=1"
        rows.append(dict(proposal_id=f"W{len(rows)+1:03d}", family=family,
                         description=f"{desc}、全体倍率={mult}", parameter_json=raw))

    for m in (1, 2, 3, 4):
        add("A", m)
    for w in (0.25, 0.5, 0.75):
        for m in (2, 3, 4, 5, 6):
            add("B", m, Mult_SCA_GBPJPY=w)
    for w in (1.5, 2.0):
        for m in (1, 2, 3):
            add("C", m, Mult_SCA_GBPJPY=w)
    for k in ("Mult_CARRY", "Mult_RSI_EURUSD"):
        for w in (0.5, 1.5):
            for m in (2, 4):
                add("D", m, **{k: w})
    for w in (0.4, 0.6):
        for m in (3, 4, 5, 6):
            add("E", m, Mult_SCA_GBPJPY=w)
    for m in (3, 4, 5, 6):
        add("F", m, Mult_SCA_GBPJPY=0.5, Mult_CARRY=0.5)
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
