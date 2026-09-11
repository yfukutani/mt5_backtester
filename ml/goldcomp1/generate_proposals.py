"""低risk域と固定ロット基準を残し、過去の棄却を公平に再評価する。"""
import csv
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["proposal_id", "family", "description", "parameter_json"]
DEFAULTS = {
    "GszMode": 0, "GszSleeveMask": 0, "GszRiskPct": 0.0,
    "GszRefCap": 0.0, "GszMinLot": 0.0, "GszMaxLot": 0.0,
    "GszApplyBoost": True, "GlobalLotMult": 1,
}


def parameters(raw):
    p = json.loads(raw)
    if not isinstance(p, dict) or set(p) != set(DEFAULTS):
        raise ValueError("比較軸の指定漏れ、または対象外の入力があります")
    if type(p["GszApplyBoost"]) is not bool:
        raise ValueError("Boostは真偽値にしてください")
    for k, v in p.items():
        if k == "GszApplyBoost":
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError("数値は有限かつ非負にしてください")
    if p["GszMode"] not in (0, 1) or p["GszSleeveMask"] not in (0, 1, 2, 3):
        raise ValueError("Modeまたはマスクが設計範囲外です")
    # 当初は1〜4で設計したが、倍率4でも最大DDが10.5%しか使われておらず
    # DD予算がまったく拘束していないと判明したため、上限探索用に広げた
    # （measure_highmult.py が 6/8/10/12/16 を測る）。
    if p["GlobalLotMult"] not in (1, 2, 3, 4, 6, 8, 10, 12, 16):
        raise ValueError("倍率が設計範囲外です")
    if p["GszMode"] == 1 and (p["GszSleeveMask"] == 0 or p["GszRiskPct"] <= 0):
        raise ValueError("ラボ案には対象マスクと正のrisk%が必要です")
    if p["GszMaxLot"] and p["GszMinLot"] > p["GszMaxLot"]:
        raise ValueError("下限が上限を超えています")
    return p


def generate():
    rows, seen = [], set()

    def add(family, **changes):
        p = dict(DEFAULTS)
        if family != "A":
            # GszAppliesはMode<=0で無効になるため、有効案は1に統一する。
            p.update(GszMode=1, GszSleeveMask=3, GszRiskPct=0.5)
        p.update(changes)
        raw = json.dumps(p, sort_keys=True, separators=(",", ":"))
        parameters(raw)
        if raw in seen:
            return
        seen.add(raw)
        # 既定値も併記することで、複利・上下限・Boostの解釈を省略に依存させない。
        desc = " / ".join("{}={}".format(k, str(v).lower() if isinstance(v, bool) else v)
                          for k, v in p.items())
        if not rows:
            desc = "現行構成 / " + desc
        rows.append(dict(proposal_id="G{:03d}".format(len(rows) + 1),
                         family=family, description=desc, parameter_json=raw))

    # G001を先頭に置き、各窓で破綻の比較基準を先に取得できるようにする。
    for mult in (1, 2, 3, 4):
        add("A", GszMode=0, GlobalLotMult=mult)
    for mask in (1, 2):
        for risk in (0.25, 0.5):
            add("B", GszSleeveMask=mask, GszRiskPct=risk)
    for risk in (0.1, 0.25, 0.5, 0.75, 1.0):
        add("C", GszRiskPct=risk)
    for risk in (0.25, 0.5, 1.0):
        for cap in (250000, 500000):
            add("D", GszRiskPct=risk, GszRefCap=cap)
    for risk in (0.25, 0.5):
        for mult in (2, 3):
            add("E", GszRiskPct=risk, GlobalLotMult=mult)
    for maximum in (0.5, 1.0, 2.0):
        for minimum in (0.01, 0.02):
            add("F", GszMinLot=minimum, GszMaxLot=maximum)
    # true側はCと共通なので再測定せず、同じ対照案を使う。
    for boost in (True, False):
        for risk in (0.25, 0.5):
            add("G", GszRiskPct=risk, GszApplyBoost=boost)
    # 有望性は未確認のため、中間値を枠別にも振って改善の場所を決めつけない。
    for risk in (0.15, 0.35, 0.6):
        for mask in (1, 2, 3):
            add("H", GszRiskPct=risk, GszSleeveMask=mask)
    for risk in (0.35, 0.6):
        add("H", GszRiskPct=risk, GszMaxLot=0.5, GszApplyBoost=False)
    return rows


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError("proposals.csvのヘッダーが一致しません")
        rows = list(reader)
    expected = {r["proposal_id"]: r for r in generate()}
    # 再開時の基準差し替えや間引きで、比較条件が変わることを防ぐ。
    if len(rows) != len(expected) or {r["proposal_id"] for r in rows} != set(expected):
        raise ValueError("G001～G042の42案すべてが必要です")
    for r in rows:
        e = expected[r["proposal_id"]]
        if parameters(r["parameter_json"]) != parameters(e["parameter_json"]) or any(
                r[k] != e[k] for k in ("family", "description")):
            raise ValueError("{}が設計と異なります".format(r["proposal_id"]))
    return rows


def main():
    rows = generate()
    with open(ROOT / "proposals.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print("総数={} / 内訳={} / 除外重複=2 / 残存重複={}".format(
        len(rows), dict(Counter(r["family"] for r in rows)),
        len(rows) - len({r["parameter_json"] for r in rows})))


if __name__ == "__main__":
    main()
