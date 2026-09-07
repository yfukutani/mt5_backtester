"""最大DDを予算の制約だけに使い、実測月利と両窓の一致で評価する。"""
from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime, timezone
from pathlib import Path

from generate_proposals import ROOT, load_proposals, parameters

DEPOSIT = 500000
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}
BUDGETS = (20, 25, 30)


def curve(path):
    rows = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"profit", "time", "magic"} <= set(reader.fieldnames or []):
            raise ValueError(f"dealログの必須列がありません: {path}")
        for r in reader:
            p = float(r["profit"])
            if not math.isfinite(p):
                raise ValueError(f"有限でない損益: {path}")
            if p != 0.0:
                rows.append((datetime.fromtimestamp(int(r["time"]), timezone.utc),
                             int(r["magic"]), p))
    # 元のcurveと同じ同時刻順序を使い、再集計によるDDの差を避ける。
    rows.sort()
    peak = cum = worst = 0.0
    peak_at = rows[0][0] if rows else None
    span = None
    for t, _, p in rows:
        cum += p
        if cum > peak:
            peak, peak_at = cum, t
        if peak - cum > worst:
            worst, span = peak - cum, (peak_at, t)
    return cum, worst, span, rows


def collect(results, proposals):
    expected = {p["proposal_id"]: p for p in proposals}
    by = {}
    if not results.exists():
        return by
    with open(results, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            pid, win = r["proposal_id"], r["window"]
            if pid not in expected or win not in MONTHS:
                raise ValueError(f"未知の案または窓: {pid}/{win}")
            if parameters(r["parameter_json"]) != parameters(expected[pid]["parameter_json"]):
                raise ValueError(f"案と結果のパラメータが不一致: {pid}")
            if r["status"] != "OK" or not r.get("deals"):
                continue
            path = Path(r["deals"])
            if not path.is_absolute():
                path = results.parent / "run_deals" / path
            if not path.is_file():
                print(f"未完了扱い: {pid}/{win} のdealログがありません")
                continue
            net, dd, span, rows = curve(path)
            by[pid, win] = dict(expected[pid], window=win, net=net, dd_yen=dd,
                               deposit_pct=100 * dd / DEPOSIT,
                               monthly_pct=100 * net / DEPOSIT / MONTHS[win],
                               span=span, rows=rows, deals=str(path))
    for (pid, win), r in by.items():
        base = next((v for (p, w), v in by.items() if w == win and
                     all(x == 1 for x in parameters(v["parameter_json"]).values())), None)
        r["gain_pp"] = r["monthly_pct"] - base["monthly_pct"] if base else None
    return by


def rankings(by, win, budget):
    eligible = [r for (pid, w), r in by.items()
                if w == win and r["dd_yen"] <= DEPOSIT * budget / 100]
    # 極値の僅差で優劣を作らず、同率は同順位として残す。
    eligible.sort(key=lambda r: (-r["monthly_pct"], r["proposal_id"]))
    return [(1 + sum(x["monthly_pct"] > r["monthly_pct"] for x in eligible), r)
            for r in eligible]


def report(by, proposals, top):
    print("入金500,000円・非複利。実測点のみ。DDは決済損益曲線の円建て落ち込み。")
    print("最大DDは予算内かの確認だけに使用し、DDの細かい順位は解釈しません。")
    complete = all((p["proposal_id"], w) in by for p in proposals for w in ("IS", "OOS"))
    print("全案・両窓完了" if complete else "暫定結果：未測定・失敗・ログ欠損が残るため採否は保留")
    for win in MONTHS:
        print(f"\n{win}: {sum(w == win for _, w in by)}/{len(proposals)}案")
        for (pid, w), r in sorted(by.items()):
            if w != win:
                continue
            gain = "基準未測定" if r["gain_pp"] is None else f"{r['gain_pp']:+.4f}ポイント"
            print(f"{pid} [{r['family']}] {r['description']} / 純益={r['net']:,.2f}円 "
                  f"月利={r['monthly_pct']:.4f}% DD={r['dd_yen']:,.2f}円 "
                  f"入金比={r['deposit_pct']:.2f}% 現行差={gain}")
        for budget in BUDGETS:
            ranked = rankings(by, win, budget)
            print(f"  予算{budget}% ({DEPOSIT*budget/100:,.0f}円) 月利最大: " +
                  (", ".join(f"{r['proposal_id']} ({r['monthly_pct']:.4f}%)"
                             for rank, r in ranked if rank == 1) or "該当なし"))
    print(f"\n両窓一致：各予算内の月利上位{top}位（同率含む）。片窓のみの上位は候補外。")
    for budget in BUDGETS:
        ranks = {w: {r["proposal_id"]: rank for rank, r in rankings(by, w, budget)}
                 for w in ("IS", "OOS")}
        union = {p for w in ranks.values() for p, rank in w.items() if rank <= top}
        for pid in sorted(union):
            a, b = ranks["IS"].get(pid), ranks["OOS"].get(pid)
            common = a is not None and b is not None and max(a, b) <= top
            label = "両窓最大・FULL確認候補" if a == b == 1 else "両窓上位・参考候補" if common else "片窓のみ・候補外"
            print(f"予算{budget}% {pid}: IS={a or '予算外/未測定'}位 OOS={b or '予算外/未測定'}位 {label}")
        if not union:
            print(f"予算{budget}%: 該当なし")
    print("両窓上位だけでは合格としません。両窓の予算内月利最大が一致しなければ採用を保留。FULLは別途確認。")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results.csv")
    parser.add_argument("--proposals", type=Path, default=ROOT / "proposals.csv")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()
    if args.top < 1:
        parser.error("--topは1以上")
    return args


def main():
    args = arguments()
    proposals = load_proposals(args.proposals)
    report(collect(args.results, proposals), proposals, args.top)


if __name__ == "__main__":
    main()
