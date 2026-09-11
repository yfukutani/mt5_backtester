"""固定ロット5枠の寄与と複利の影響を分離するため、比較条件を固定する。"""
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
        # 同一設定の二重測定で時間を浪費しないよう、ID採番前に除外する。
        if raw in seen:
            return
        seen.add(raw)
        rows.append(dict(
            proposal_id=f"R{len(rows) + 1:03d}", family=family,
            description=f"マスク={mask} / risk%={risk:g} / FxRiskRefCap={fxref} / RefCap={refcap} / 倍率={mult}",
            parameter_json=raw))

    # 現行を先頭にして、各窓の破綻判定基準を後続案より先に取得する。
    for refcap in (78000, 250000):
        for mult in (1, 3):
            add("A", 0, 0.5, 0, refcap, mult)
    for mask in (1, 2, 4, 8, 16):
        add("B", mask, 0.5, 250000, 250000, 1)
    for family, mask, risks in (("C", 7, (0.25, 0.5, 1.0)),
                                ("D", 24, (0.25, 0.5, 1.0)),
                                ("E", 31, (0.1, 0.25, 0.5))):
        for risk in risks:
            for fxref in (250000, 0):
                add(family, mask, risk, fxref, 250000, 1)
    for risk in (0.25, 0.5):
        for mult in (2, 3):
            add("F", 31, risk, 250000, 250000, mult)
    for risk in (0.1, 0.25, 0.5):
        for mult in (1, 2):
            add("G", 31, risk, 0, 0, mult)
    # 未測定のため有望性は仮説。低リスク全枠と群別中間値を優先し、倍率は1に抑える。
    for mask, risk, fxref in ((31, 0.15, 250000), (31, 0.15, 0),
                              (31, 0.35, 250000), (7, 0.35, 250000),
                              (7, 0.75, 250000), (24, 0.35, 250000),
                              (24, 0.75, 250000)):
        add("H", mask, risk, fxref, 250000, 1)
    return rows


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError("proposals.csvのヘッダーが一致しません")
        rows = list(reader)
    # 再開時の基準差し替えや間引きで比較条件が変わることを防ぐ。
    expected = {r["proposal_id"]: r for r in generate()}
    if len(rows) != len(expected) or {r["proposal_id"] for r in rows} != set(expected):
        raise ValueError("R001〜R044の44案すべてが必要です")
    for r in rows:
        e = expected[r["proposal_id"]]
        if (parameters(r["parameter_json"]) != parameters(e["parameter_json"])
                or any(r[k] != e[k] for k in ("family", "description"))):
            raise ValueError(f"{r['proposal_id']}の設定または説明が設計と異なります")
    return rows


def main():
    rows = generate()
    with open(ROOT / "proposals.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    duplicates = len(rows) - len({r["parameter_json"] for r in rows})
    print(f"総数={len(rows)} / 内訳={dict(Counter(r['family'] for r in rows))} / 重複={duplicates}")


if __name__ == "__main__":
    main()
