"""予算内月利上位案と現行の最悪期間を分解し、DD支配枠の交代を確認する。"""
from collections import defaultdict

from adjudicate import BUDGETS, MONTHS, arguments, collect, rankings
from generate_proposals import load_proposals, parameters

MAGICS = {
    20260622: "PB USDJPY", 20260627: "PB GBPJPY", 20260610: "RSI USDJPY",
    20260605: "RSI EURUSD", 20260774: "RSI GBPUSD", 20260629: "Pair",
    20260650: "Carry AUDJPY", 20261000: "SCA USDJPY", 20261001: "SCA GBPJPY",
}


def segment(rows):
    # 日時だけの区間では初回損失や同秒約定が漏れるため、curveと同じ順序の位置で切る。
    peak = cum = worst = 0.0
    peak_i, bounds = -1, None
    for i, (_, _, p) in enumerate(rows):
        cum += p
        if cum > peak:
            peak, peak_i = cum, i
        if peak - cum > worst:
            worst, bounds = peak - cum, (peak_i, i)
    stats = defaultdict(lambda: [0.0, 0])
    if bounds:
        for _, magic, p in rows[bounds[0] + 1:bounds[1] + 1]:
            key = MAGICS.get(magic, f"未知magic={magic}")
            stats[key][0] += p
            stats[key][1] += 1
    return stats


def dominant(stats):
    losses = {k: v[0] for k, v in stats.items() if v[0] < 0}
    return min(losses, key=losses.get) if losses else "なし"


def main():
    args = arguments()
    proposals = load_proposals(args.proposals)
    by = collect(args.results, proposals)
    selected = {r["proposal_id"] for w in MONTHS for budget in BUDGETS
                for rank, r in rankings(by, w, budget) if rank <= args.top}
    selected.update(p["proposal_id"] for p in proposals
                    if all(v == 1 for v in parameters(p["parameter_json"]).values()))
    print("予算別月利上位の和集合と現行。片窓上位も診断用に表示し、採用判断とは区別します。")
    for win in MONTHS:
        base = next((r for (pid, w), r in by.items() if w == win and
                     all(v == 1 for v in parameters(r["parameter_json"]).values())), None)
        baseline = dominant(segment(base["rows"])) if base else "基準未測定"
        for pid in sorted(selected):
            r = by.get((pid, win))
            if not r:
                print(f"{pid}/{win}: 未測定")
                continue
            stats = segment(r["rows"])
            print(f"\n{pid}/{win} {r['description']} DD={r['dd_yen']:,.2f}円 "
                  f"支配枠={dominant(stats)}（現行={baseline}）")
            if not r["span"]:
                print("落ち込みなし")
                continue
            a, b = r["span"]
            print(f"期間={a.isoformat()}〜{b.isoformat()} ({(b-a).days}日)")
            loss = sum(v[0] for v in stats.values() if v[0] < 0)
            for name in MAGICS.values():
                stats.setdefault(name, [0.0, 0])
            for name, (net, count) in sorted(stats.items(), key=lambda item: item[1][0]):
                share = f"{100*net/loss:.2f}%" if net < 0 and loss else "—"
                print(f"  {name}: {net:+,.2f}円 / 損益非ゼロ約定={count} / 負寄与合計比={share}")
            print(f"  内訳合計={sum(v[0] for v in stats.values()):+,.2f}円（最大落ち込みの負値と一致）")


if __name__ == "__main__":
    main()
