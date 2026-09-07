"""残高増加でリスクを小さく見せないよう、deal損益の円建てDDで比較する。"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from generate_proposals import DEFAULTS

ROOT = Path(__file__).resolve().parent
WINDOWS = ("IS", "OOS", "FULL")
MAGICS = {20260720: "fund", 20260724: "bfx", 20260710: "eth"}
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
# 共通ゲートと同じ下限だが、今回指定された倍率判定とは独立に表示する。
MIN_TRADES = 60


def deal_path(row):
    name = row.get("deals")
    if not name:
        raise ValueError("deals列が空です")
    path = Path(name)
    if path.is_absolute():
        return path
    local = ROOT / "run_deals" / path
    # 回収失敗時にもmeasureが記録した同名のCommonファイルを参照できるようにする。
    return local if local.exists() else COMMON / path


def read_deals(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"profit", "entry", "time", "magic", "position_id"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"deal列不足: {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"空のdealログ: {path}")
    for r in rows:
        if not math.isfinite(float(r["profit"])):
            raise ValueError(f"非有限損益: {path}")
        int(r["time"])
        int(r["magic"])
    return rows


def closed_trades(rows):
    # 損益0のIN約定は曲線に不要。同時刻はログ順を保ち人工的な並べ替えを避ける。
    out = [(int(r["time"]), float(r["profit"])) for r in rows if float(r["profit"]) != 0.0]
    return sorted(out, key=lambda x: x[0])


def curve(rows):
    peak = cum = worst = 0.0
    for _, profit in rows:
        cum += profit
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return cum, worst


def metrics(row):
    rows = read_deals(deal_path(row))
    net, dd = curve(closed_trades(rows))
    result = dict(net_jpy=net, dd_jpy=dd)
    for magic, key in MAGICS.items():
        sleeve = [r for r in rows if int(r["magic"]) == magic]
        result[f"{key}_net"] = sum(float(r["profit"]) for r in sleeve)
        # 部分決済を複数取引と誤認しないよう、決済したposition単位で数える。
        result[f"{key}_n"] = len({r["position_id"] for r in sleeve if r["entry"] != "0"})
    return result


def load_results():
    by = defaultdict(dict)
    with (ROOT / "results.csv").open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["status"] == "OK" and row["window"] in WINDOWS:
                by[row["proposal_id"]][row["window"]] = row
    return by


def write_csv(name, rows, fields):
    with (ROOT / name).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    by = load_results()
    # FULL窓は暗号枠を有効にすると1run 321秒かかるため全案では回していない
    # （measure.py のコメント参照）。測れている窓だけで判定する。
    wins = [w for w in WINDOWS if w in by.get("C001", {})]
    if not wins:
        raise ValueError("基準C001が1窓も測れていない")
    bases = {}
    for win in wins:
        row = by["C001"][win]
        params = json.loads(row["parameter_json"])
        if params != DEFAULTS:
            raise ValueError(f"C001 {win}が両枠既定値ではありません")
        bases[win] = metrics(row)
        if bases[win]["net_jpy"] <= 0 or bases[win]["dd_jpy"] <= 0:
            raise ValueError(f"C001 {win}の純益・DDは正でなければ倍率比較できません")

    details, ranked, issues = [], [], []
    for pid, windows in sorted(by.items()):
        records = []
        for win in wins:
            if win not in windows:
                issues.append(f"{pid} {win}: 未測定または失敗")
                continue
            row = windows[win]
            try:
                m = metrics(row)
            except (OSError, ValueError, KeyError) as exc:
                issues.append(f"{pid} {win}: 評価不能 {exc}")
                continue
            net_ratio = m["net_jpy"] / bases[win]["net_jpy"]
            dd_ratio = m["dd_jpy"] / bases[win]["dd_jpy"]
            rec = dict(proposal_id=pid, family=row["family"], window=win,
                       description=row["description"], deals=row["deals"], **m)
            rec.update(net_ratio=net_ratio, dd_ratio=dd_ratio,
                       gap=net_ratio - dd_ratio, passed=net_ratio > dd_ratio)
            records.append(rec)
            details.append(rec)
        if len(records) == len(wins) and all(r["passed"] for r in records):
            rec = dict(proposal_id=pid, worst_gap=min(r["gap"] for r in records),
                       description=windows["IS"]["description"])
            for r in records:
                for key in ("net_ratio", "dd_ratio", "gap"):
                    rec[f"{r['window']}_{key}"] = r[key]
            ranked.append(rec)
    ranked.sort(key=lambda r: (-r["worst_gap"], r["proposal_id"]))
    fields = ["proposal_id", "family", "window", "description", "deals", "net_jpy", "dd_jpy"]
    fields += [f"{key}_{suffix}" for key in MAGICS.values() for suffix in ("net", "n")]
    fields += ["net_ratio", "dd_ratio", "gap", "passed"]
    write_csv("adjudication.csv", details, fields)
    write_csv("adjudication_passed.csv", ranked,
              ["proposal_id", "worst_gap", "description"] +
              [f"{w}_{k}" for w in WINDOWS for k in ("net_ratio", "dd_ratio", "gap")])
    lines = ["基準: C001（XM本番構成＋S2046、両暗号枠既定値）",
             "円建て判定: 純益倍率 > DD倍率。3窓合格のみ最弱窓の差の降順。",
             f"3窓合格: {len(ranked)}案"]
    lines += [f"{r['proposal_id']} 最弱差={r['worst_gap']:.6f} {r['description']}" for r in ranked]
    lines.append("全案・全窓の詳細（枠取引数は決済position数）")
    for r in details:
        sleeves = " / ".join(f"{k} {r[k+'_net']:,.2f}円 {r[k+'_n']}取引" for k in MAGICS.values())
        lines.append(f"{r['proposal_id']} {r['window']}: 純益={r['net_jpy']:,.2f}円 "
                     f"DD={r['dd_jpy']:,.2f}円 純益倍率={r['net_ratio']:.6f} "
                     f"DD倍率={r['dd_ratio']:.6f} 判定={r['passed']} / {sleeves}")
        if r["window"] == "IS":
            lines.append("  サンプル参考（IS 60以上）: " + " / ".join(
                f"{k}={'十分' if r[k+'_n'] >= MIN_TRADES else '不足'}" for k in MAGICS.values()))
    lines += issues
    report = "\n".join(lines) + "\n"
    (ROOT / "adjudication.txt").write_bytes(report.encode("utf-8"))
    print(report)


if __name__ == "__main__":
    main()
