"""残高増加でリスクを小さく見せないよう、deal損益の円建てDDで比較する。"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from statistics import median

ROOT = Path(__file__).resolve().parent
WINDOWS = ("IS", "OOS")
MAGICS = {20261006: "uj2", 20261007: "gj2", 20261000: "sca_uj", 20261001: "sca_gj"}
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
# 共通ゲートと同じ下限だが、新枠純益の一次判定とは独立に表示する。
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


def target(row):
    params = json.loads(row["parameter_json"])
    enabled = [key for key, prefix in (("uj2", "Sca5"), ("gj2", "Sca6"))
               if params.get(prefix + "Enable") is True]
    if len(enabled) != 1:
        raise ValueError("新枠は片側だけ有効でなければなりません")
    return enabled[0]


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


def ratio(value, baseline):
    # 分母が非正でも純益判定を妨げないよう、参考倍率だけを未定義にする。
    return value / baseline if baseline > 0 else ""


def main():
    by = load_results()
    bases, issues = {}, []
    for win in WINDOWS:
        try:
            row = by["BASE"][win]
            if json.loads(row["parameter_json"]) != {}:
                raise ValueError("BASEのparameter_jsonは空の辞書が必要です")
            bases[win] = metrics(row)
            if any(bases[win][k] != 0 for k in ("uj2_n", "gj2_n", "uj2_net", "gj2_net")):
                raise ValueError("BASEに新枠の約定があります")
        except (KeyError, ValueError, OSError) as exc:
            bases.pop(win, None)
            issues.append(f"BASE {win}: 参考倍率・親枠差は評価不能 {exc}")

    with (ROOT / "proposals.csv").open(encoding="utf-8-sig", newline="") as fh:
        proposals = list(csv.DictReader(fh))
    details, ranked, groups = [], [], defaultdict(list)
    for prop in proposals:
        pid = prop["proposal_id"]
        sleeve = target(prop)
        parent = {"uj2": "sca_uj", "gj2": "sca_gj"}[sleeve]
        rec = dict(proposal_id=pid, family=prop["family"], sleeve=sleeve,
                   parent=parent, description=prop["description"])
        for win in WINDOWS:
            try:
                row = by[pid][win]
                if json.loads(row["parameter_json"]) != json.loads(prop["parameter_json"]):
                    raise ValueError("測定パラメータが提案と不一致です")
                m = metrics(row)
                base = bases.get(win)
                vals = dict(new_net=m[sleeve+"_net"], new_n=m[sleeve+"_n"],
                            parent_net=m[parent+"_net"], parent_n=m[parent+"_n"],
                            book_net=m["net_jpy"], dd_jpy=m["dd_jpy"],
                            net_ratio=ratio(m["net_jpy"], base["net_jpy"]) if base else "",
                            dd_ratio=ratio(m["dd_jpy"], base["dd_jpy"]) if base else "",
                            parent_net_delta=m[parent+"_net"]-base[parent+"_net"] if base else "",
                            parent_n_delta=m[parent+"_n"]-base[parent+"_n"] if base else "")
                rec.update({f"{win}_{k}": v for k, v in vals.items()})
            except (KeyError, OSError, ValueError) as exc:
                issues.append(f"{pid} {win}: 未測定・失敗または評価不能 {exc}")
        complete = all(f"{win}_new_net" in rec for win in WINDOWS)
        rec["status"] = "評価済み" if complete else "評価不能"
        # 極値DDに支配された選別を避け、合否と順位には新枠純益だけを用いる。
        rec["passed"] = all(rec[f"{win}_new_net"] > 0 for win in WINDOWS) if complete else ""
        rec["worst_net"] = min(rec[f"{win}_new_net"] for win in WINDOWS) if complete else ""
        rec["IS_sample_ge60"] = rec["IS_new_n"] >= MIN_TRADES if "IS_new_n" in rec else ""
        details.append(rec)
        groups[prop["family"]].append(rec)
        if rec["passed"] is True:
            ranked.append(rec)
    ranked.sort(key=lambda r: (-r["worst_net"], r["proposal_id"]))
    keys = ("new_net", "new_n", "parent_net", "parent_n", "parent_net_delta",
            "parent_n_delta", "book_net", "dd_jpy", "net_ratio", "dd_ratio")
    fields = ["proposal_id", "family", "sleeve", "parent", "description", "status"]
    fields += [f"{w}_{k}" for w in WINDOWS for k in keys]
    fields += ["passed", "worst_net", "IS_sample_ge60"]
    write_csv("adjudication.csv", details, fields)
    write_csv("adjudication_passed.csv", ranked, fields)
    families = []
    for family, records in groups.items():
        valid = [r for r in records if r["status"] == "評価済み"]
        summary = dict(family=family, proposed=len(records), evaluated=len(valid),
                       both_positive=sum(r["passed"] is True for r in valid))
        for win in WINDOWS:
            summary[f"{win}_median_net"] = median(r[f"{win}_new_net"] for r in valid) if valid else ""
        families.append(summary)
    write_csv("family_summary.csv", families,
              ["family", "proposed", "evaluated", "both_positive", "IS_median_net", "OOS_median_net"])
    lines = ["第一判定: 新枠純益がIS/OOSとも正。順位: 弱い窓の純益降順。",
             "第二の確認: 決済position数（IS 60以上を参考表示、採用確定ではない）。",
             "DD・純益倍率・DD倍率は参考のみ。DDはprofit累積のピークからの最大落ち込み。",
             "倍率の分母は新枠両方OFFの実測BASE。分母非正・BASE欠測時は空欄。",
             "ファミリー中央値は両窓評価済み案の新枠純益。欠測案を黒字扱いしない。",
             f"両窓正: {len(ranked)}案"]
    lines += [f"{r['proposal_id']} {r['sleeve']} 最弱純益={r['worst_net']:,.2f}円" for r in ranked]
    lines.append("全案詳細（損益・DDは円、倍率は参考値）")
    for r in details:
        lines.append(f"{r['proposal_id']} {r['description']} {r['status']} 両窓正={r['passed']}")
        for win in WINDOWS:
            lines.append(win + " " + " / ".join(f"{k}={r.get(win+'_'+k, '')}" for k in keys))
        lines.append(f"ISサンプル60以上={r['IS_sample_ge60']}")
    lines.append("ファミリー集計")
    lines += [" / ".join(f"{k}={v}" for k, v in r.items()) for r in families]
    lines += issues
    report = "\n".join(lines) + "\n"
    (ROOT / "adjudication.txt").write_bytes(report.encode("utf-8"))
    print(report)


if __name__ == "__main__":
    main()
