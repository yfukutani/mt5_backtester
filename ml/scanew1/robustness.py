"""特定年だけの利益を採用しないため、sca4と同じ建玉年帰属で最良年を除外する。"""
import argparse
import csv
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAGIC = 20261008


def yearly(path, magic):
    ins, outs = {}, defaultdict(list)
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if int(r["magic"]) != magic:
            continue
        pid = int(r["position_id"])
        if r["entry"] == "0":
            ins[pid] = r
        else:
            outs[pid].append(r)
    if set(outs) - set(ins):
        raise ValueError("新枠の決済に対応する建玉がありません: " + str(path))
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


def evaluate(path):
    y, n = yearly(path, MAGIC)
    if not all(math.isfinite(v) for v in y.values()):
        raise ValueError('有限でない年次損益: ' + str(path))
    total = sum(y.values())
    best_year, best_val = max(y.items(), key=lambda kv: kv[1]) if y else ('', 0.0)
    return dict(total=total, n=n, best_year=best_year, best_val=best_val,
                ex_best=total-best_val, years_pos=sum(v > 0 for v in y.values()), years=len(y))


def main():
    from generate_proposals import load_proposals
    from adjudicate import collect, WINDOWS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'results.csv')
    parser.add_argument('--proposals', type=Path, default=ROOT / 'proposals.csv')
    parser.add_argument('--out', type=Path, default=ROOT / 'robustness.csv')
    args = parser.parse_args()
    proposals = load_proposals(args.proposals)
    by = collect(args.results, proposals)
    out = []
    for p in proposals:
        pid = p['proposal_id']
        rec = dict(proposal_id=pid, description=p['description'])
        for win in WINDOWS:
            if (pid, win) not in by:
                break
            values = evaluate(by[pid, win]['path'])
            if abs(values['total'] - by[pid, win]['new_net']) > 0.000001:
                raise ValueError('年次集計と新枠純益が不一致: ' + pid)
            rec.update({f'{win}_{k}': v for k, v in values.items()})
        else:
            rec['worst_ex'] = min(rec[f'{w}_ex_best'] for w in WINDOWS)
            rec['both_positive'] = rec['worst_ex'] > 0
            out.append(rec)
            continue
        print(f'{pid}: 未完了・判定保留')
    out.sort(key=lambda r: (-r['worst_ex'], r['proposal_id']))
    print(f'評価 {len(out)}/{len(proposals)}案 / 最良年除外後も両窓黒字 {sum(r["both_positive"] for r in out)}案')
    print('比較：既存SCA第1の最良年除外後実測 IS +81,175円 / OOS +16,257円')
    print('建玉年（UTC）に部分決済も合算。サンプルゲートはadjudicate.pyで別判定。')
    for r in out:
        values = ' / '.join(f'{w}: 純益={r[w+"_total"]:+,.2f}円・決済済建玉={r[w+"_n"]}・'
                            f'最良年={r[w+"_best_year"]}・除外後={r[w+"_ex_best"]:+,.2f}円'
                            for w in WINDOWS)
        print(f'{r["proposal_id"]} {r["description"]} / {values} / 両窓黒字={r["both_positive"]}')
    fields = ['proposal_id', 'description'] + [f'{w}_{k}' for w in WINDOWS
              for k in ('total', 'n', 'best_year', 'best_val', 'ex_best', 'years_pos', 'years')]
    with open(args.out, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields + ['worst_ex', 'both_positive'], lineterminator='\n')
        writer.writeheader()
        writer.writerows(out)


if __name__ == '__main__':
    main()
