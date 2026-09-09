"""RefCap・全体倍率・重みの全組合せを固定し、比較の足場をC001に置く。"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["proposal_id", "family", "description", "parameter_json"]
MULTS = tuple("Mult_" + s for s in (
    "PB_USDJPY", "PB_GBPJPY", "PB_GOLD", "RSI_USDJPY", "RSI_EURUSD",
    "RSI_GBPUSD", "PAIR", "CARRY", "VBO", "ETH", "BTC_FUND", "BFXREV",
    "SCA_GOLD", "SCA_USDJPY", "SCA_GBPJPY"))
REFCAPS = ("RefCap_PB_USDJPY", "RefCap_PB_GBPJPY", "RefCap_CARRY")
WEIGHTED = ("Mult_SCA_GBPJPY", "Mult_CARRY")


def parameters(raw):
    p = json.loads(raw)
    if not isinstance(p, dict) or set(p) != {*MULTS, *REFCAPS, "GlobalLotMult"}:
        raise ValueError("比較軸以外の変更、またはパラメータの指定漏れがあります")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in p.values()):
        raise ValueError("パラメータは有限の数値にしてください")
    if len({p[k] for k in REFCAPS}) != 1 or p[REFCAPS[0]] not in (0, 78000, 250000, 500000):
        raise ValueError("3枠のRefCapは同一の指定値にしてください")
    if p["GlobalLotMult"] not in (1, 2, 3):
        raise ValueError("倍率は1・2・3のいずれかにしてください")
    if tuple(p[k] for k in WEIGHTED) not in ((1.0, 1.0), (0.5, 0.5)):
        raise ValueError("重みは現行または採用形にしてください")
    if any(p[k] != 1.0 for k in MULTS if k not in WEIGHTED):
        raise ValueError("他枠の重みは1.0に固定してください")
    return p


def generate():
    rows = []
    # 現行を先頭にすることで、各窓の破綻判定基準を後続案より先に取得できる。
    for refcap in (78000, 0, 250000, 500000):
        for mult in (1, 2, 3):
            for weight in (1.0, 0.5):
                p = dict.fromkeys(MULTS, 1.0)
                p.update(dict.fromkeys(REFCAPS, refcap))
                p.update(dict.fromkeys(WEIGHTED, weight))
                p["GlobalLotMult"] = mult
                raw = json.dumps(p, sort_keys=True, separators=(",", ":"))
                parameters(raw)
                ref_desc = "0(複利)" if refcap == 0 else f"{refcap}(固定)"
                weight_desc = "全1.0" if weight == 1.0 else "0.5-0.5"
                rows.append(dict(
                    proposal_id=f"C{len(rows) + 1:03d}",
                    family="compounding" if refcap == 0 else "fixed",
                    description=f"RefCap={ref_desc} / 倍率{mult} / 重み{weight_desc}",
                    parameter_json=raw))
    return rows


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError("proposals.csvのヘッダーが一致しません")
        rows = list(reader)
    # 再開時のC001差し替えや間引きで、比較基準が変わることを防ぐ。
    expected = {r["proposal_id"]: parameters(r["parameter_json"]) for r in generate()}
    if len(rows) != 24 or {r["proposal_id"] for r in rows} != set(expected):
        raise ValueError("C001～C024の24案すべてが必要です")
    for r in rows:
        if parameters(r["parameter_json"]) != expected[r["proposal_id"]]:
            raise ValueError(f"{r['proposal_id']}のパラメータが設計と異なります")
    return rows


def main():
    rows = generate()
    with open(ROOT / "proposals.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"総数={len(rows)}（RefCap 4 × 倍率3 × 重み2）")


if __name__ == "__main__":
    main()
