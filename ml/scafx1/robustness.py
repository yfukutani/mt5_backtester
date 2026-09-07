"""特定年への依存を見逃さないよう、USDJPYとGBPJPYを別々に最良年除外で評価する。"""
import csv
from collections import defaultdict
from datetime import datetime, timezone

from adjudicate import ROOT, deal_path, load_results, read_deals, write_csv, target

MAGICS = {20261006: "uj2", 20261007: "gj2"}


def yearly(path, magic):
    ins, outs = {}, defaultdict(list)
    for r in read_deals(path):
        if int(r["magic"]) != magic:
            continue
        pid = int(r["position_id"])
        if r["entry"] == "0":
            ins[pid] = r
        else:
            outs[pid].append(r)
    y = defaultdict(float)
    n = 0
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        y[datetime.fromtimestamp(int(i["time"]), timezone.utc).year] += \
            sum(float(x["profit"]) for x in o)
        n += 1
    return y, n


def main():
    by = load_results()
    out, lines = [], []
    for magic, sleeve in MAGICS.items():
        records = []
        for pid, windows in sorted(by.items()):
            if pid == "BASE":
                continue
            try:
                if target(next(iter(windows.values()))) != sleeve:
                    continue
            except (ValueError, KeyError) as exc:
                lines.append(f"{pid}: 評価不能 {exc}")
                continue
            rec = dict(proposal_id=pid, sleeve=sleeve)
            try:
                for win in ("IS", "OOS"):
                    path = deal_path(windows[win])
                    read_deals(path)
                    # 元ラウンドと比較可能にするため、年は決済年でなく建玉の開始年に帰属させる。
                    years, n = yearly(path, magic)
                    if not years:
                        raise ValueError(f"{win}の決済済み取引なし")
                    best_year, best_val = max(years.items(), key=lambda kv: kv[1])
                    total = sum(years.values())
                    for key, val in dict(total=total, n=n, best_year=best_year,
                                         best_val=best_val, ex_best=total-best_val,
                                         years_pos=sum(v > 0 for v in years.values()),
                                         years=len(years)).items():
                        rec[f"{win}_{key}"] = val
                rec["description"] = windows["IS"]["description"]
                rec["worst_ex"] = min(rec["IS_ex_best"], rec["OOS_ex_best"])
                rec["passed"] = rec["worst_ex"] > 0
                records.append(rec)
            except (KeyError, OSError, ValueError) as exc:
                lines.append(f"{pid} {sleeve}: 評価不能 {exc}")
        records.sort(key=lambda r: -r["worst_ex"])
        lines.append(f"{sleeve}: 評価{len(records)}案 / 最良年除外後も両窓黒字{sum(r['passed'] for r in records)}案")
        for r in records:
            lines.append(f"{r['proposal_id']} {sleeve}: " + " / ".join(
                f"{win} 純益={r[win+'_total']:,.2f}円 取引={r[win+'_n']} "
                f"最良年={r[win+'_best_year']} 除外後={r[win+'_ex_best']:,.2f}円"
                for win in ("IS", "OOS")) + f" 両窓黒字={r['passed']}")
        out.extend(records)
    fields = ["proposal_id", "sleeve", "description"] + [
        f"{win}_{key}" for win in ("IS", "OOS")
        for key in ("total", "n", "best_year", "best_val", "ex_best", "years_pos", "years")]
    write_csv("robustness.csv", out, fields + ["worst_ex", "passed"])
    report = "\n".join(lines) + "\n"
    (ROOT / "robustness.txt").write_bytes(report.encode("utf-8"))
    print(report)


if __name__ == "__main__":
    main()
