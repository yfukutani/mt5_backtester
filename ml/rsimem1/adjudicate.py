"""RSI 3枠の両窓純益差で比較する。ブック純益と円建てDDは参考表示のみ。"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import median

from generate_proposals import ROOT, load_proposals, parameters

WINDOWS = ("IS", "OOS")
RSI = {20260610: "rsi_uj", 20260605: "rsi_eu", 20260774: "rsi_gu"}
# 有効サンプルの過大評価を避ける暫定下限であり、統計的有意性は保証しない。
MIN_CHANGED = 10


def read_deals(path):
    sleeves = {k: {"net": 0.0, "n": 0} for k in RSI.values()}
    rows = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"time", "magic", "entry", "profit"} <= set(reader.fieldnames or []):
            raise ValueError(f"dealログの必須列がありません: {path}")
        for r in reader:
            p = float(r["profit"])
            if not math.isfinite(p):
                raise ValueError(f"有限でない損益: {path}")
            t, magic, entry = int(r["time"]), int(r["magic"]), int(r["entry"])
            if entry not in (0, 1, 2, 3):
                raise ValueError(f"不正なentry: {path}")
            if p != 0:
                rows.append((t, magic, p))
            if magic in RSI:
                a = sleeves[RSI[magic]]
                # measureと同じ定義を保ち、集計方式の違いを効果と誤認しない。
                if entry == 0:
                    a["n"] += 1
                else:
                    a["net"] += p
    # fxmult1.curveと同じ同時刻順序で、DDの再集計差を避ける。
    rows.sort()
    peak = cum = worst = 0.0
    for _, _, p in rows:
        cum += p
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return dict(sleeves=sleeves, rsi_net=sum(a["net"] for a in sleeves.values()),
                book_net=cum, dd_yen=worst)


def collect(results, proposals):
    expected = {p["proposal_id"]: p for p in proposals}
    by = {}
    if not results.is_file():
        return by
    with open(results, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"proposal_id", "window", "parameter_json", "status", "deals"} <= set(reader.fieldnames or []):
            raise ValueError("結果CSVの必須列がありません")
        for r in reader:
            pid, win = r["proposal_id"], r["window"]
            if pid not in expected or win not in WINDOWS:
                raise ValueError(f"未知の案または窓: {pid}/{win}")
            if parameters(r["parameter_json"]) != parameters(expected[pid]["parameter_json"]):
                raise ValueError(f"案と結果のパラメータが不一致: {pid}")
            if r["status"] != "OK" or not r["deals"]:
                continue
            path = Path(r["deals"])
            if not path.is_absolute():
                path = results.parent / "run_deals" / path
            if not path.is_file():
                print(f"未完了扱い: {pid}/{win} のdealログがありません")
                continue
            by[pid, win] = read_deals(path)
    for (pid, win), r in by.items():
        base = by.get(("M001", win))
        if base is None:
            continue
        r["gain"] = r["rsi_net"] - base["rsi_net"]
        r["delta_n"] = {k: r["sleeves"][k]["n"] - base["sleeves"][k]["n"] for k in RSI.values()}
        # 枠間の増減相殺で変化を隠さない。ただし同数の取引の入れ替わりは検出できない。
        r["changed"] = sum(abs(n) for n in r["delta_n"].values())
    return by


def paired(by, pid):
    return all((pid, w) in by and "gain" in by[pid, w] for w in WINDOWS)


def both_positive(by, pid):
    return paired(by, pid) and all(by[pid, w]["gain"] > 0 for w in WINDOWS)


def rankings(by, proposals):
    eligible = [p["proposal_id"] for p in proposals if both_positive(by, p["proposal_id"])]
    return sorted(eligible, key=lambda pid: (-min(by[pid, w]["gain"] for w in WINDOWS), pid))


def verdict(by, pid, min_changed):
    if not paired(by, pid):
        return "判定不能（案またはM001の窓が未完了）"
    if pid == "M001":
        return "現行基準"
    sizes = [by[pid, w]["changed"] for w in WINDOWS]
    if max(sizes) == 0:
        return "何も起きていない（取引数差の代理指標上）・判定不能"
    if min(sizes) < min_changed:
        return "判定不能（変更取引数の代理指標が不足）"
    return "両窓改善・候補（有意性は未確認）" if both_positive(by, pid) else "両窓改善せず"


def report(by, proposals, min_changed):
    print("第一判定: RSI 3枠合計純益のM001差がIS/OOSとも正。ブック純益・円建てDDは参考のみ。")
    print(f"変更規模=枠別取引数差の絶対値合計。片窓でも{min_changed}件未満なら判定不能（暫定閾値）。")
    print("差0は同数の取引入れ替わりを検出できないため、効果なしの証明ではありません。")
    complete = all((p["proposal_id"], w) in by for p in proposals for w in WINDOWS)
    print("全案・両窓完了" if complete else "暫定結果：未完了が残るためラウンド全体の結論は保留")
    ranked = rankings(by, proposals)
    print("\n両窓ともRSI 3枠合計が改善した案（弱い窓の改善額で降順・少数案も表示）")
    for pid in ranked:
        print(f"{pid}: IS差={by[pid, 'IS']['gain']:+,.2f}円 / OOS差={by[pid, 'OOS']['gain']:+,.2f}円 / "
              f"{verdict(by, pid, min_changed)}")
    if not ranked:
        print("該当なし（未完了があれば効果なしとは判定しません）")
    print("\n全案の詳細")
    for p in proposals:
        pid = p["proposal_id"]
        print(f"{pid} [{p['family']}] {p['description']} / {verdict(by, pid, min_changed)}")
        for w in WINDOWS:
            r = by.get((pid, w))
            if r is None:
                print(f"  {w}: 未完了")
                continue
            gain = f"{r['gain']:+,.2f}円" if "gain" in r else "M001未完了"
            print(f"  {w}: RSI合計純益={r['rsi_net']:,.2f}円 / M001差={gain}")
            for k, a in r["sleeves"].items():
                dn = f"{r['delta_n'][k]:+d}" if "delta_n" in r else "M001未完了"
                print(f"    {k}: 純益={a['net']:,.2f}円 / 取引数={a['n']} / 取引数差={dn}")
            if "changed" in r:
                print(f"    取引数差合計={sum(r['delta_n'].values()):+d} / 絶対差合計={r['changed']}")
            print(f"    参考: ブック純益={r['book_net']:,.2f}円 / 円建てDD={r['dd_yen']:,.2f}円")
    print("\nファミリー別（両窓比較可能な全案。改善案だけに絞らない）")
    for family in dict.fromkeys(p["family"] for p in proposals):
        members = [p["proposal_id"] for p in proposals if p["family"] == family]
        valid = [pid for pid in members if paired(by, pid)]
        if not valid:
            print(f"{family}: 比較可能=0/{len(members)}・中央値未算出")
            continue
        med = " / ".join(f"{w}純益中央値={median(by[pid,w]['rsi_net'] for pid in valid):,.2f}円"
                         f"・差中央値={median(by[pid,w]['gain'] for pid in valid):+,.2f}円" for w in WINDOWS)
        positive = sum(both_positive(by, pid) for pid in valid)
        enough = sum(both_positive(by, pid) and min(by[pid,w]["changed"] for w in WINDOWS) >= min_changed for pid in valid)
        print(f"{family}: 比較可能={len(valid)}/{len(members)} / {med} / 両窓正={positive} / うち変更規模充足={enough}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results.csv")
    parser.add_argument("--proposals", type=Path, default=ROOT / "proposals.csv")
    parser.add_argument("--min-changed", type=int, default=MIN_CHANGED,
                        help="各窓の枠別取引数絶対差合計の暫定下限（既定10、有意性の保証なし）")
    args = parser.parse_args()
    if args.min_changed < 1:
        parser.error("--min-changedは1以上です")
    proposals = load_proposals(args.proposals)
    report(collect(args.results, proposals), proposals, args.min_changed)


if __name__ == "__main__":
    main()
