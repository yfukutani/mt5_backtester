import csv, sys, collections

# ScaFilRangeMin / (仮)ScaFilRangeMax は EA では dist/entry の比で判定される（EA 1927行）。
# 比の空間で、下限／上限それぞれを入れたときの「素朴な合計」を両窓で出す。
# ⚠️ 複利では経路が変わるので、この素朴な合計は実測値ではない。候補の絞り込みにだけ使う。

MAG = {'20261000': 'SCA_UJ', '20261001': 'SCA_GJ'}
GRID = [0.0026, 0.0028, 0.0030, 0.0032, 0.0034, 0.0036, 0.0038, 0.0040,
        0.0042, 0.0045, 0.0048, 0.0052, 0.0056, 0.0060, 0.0065, 0.0070, 0.0080]

def load(path):
    rows = list(csv.DictReader(open(path, newline='', encoding='utf-8')))
    ent, pnl = {}, collections.defaultdict(float)
    for r in rows:
        pid = r['position_id']
        if r['entry'] == '0':
            ent[pid] = r
        pnl[pid] += float(r['profit'] or 0)
    out = collections.defaultdict(list)
    for pid, e in ent.items():
        m = MAG.get(e['magic'])
        if not m:
            continue
        px, sl = float(e['price']), float(e['sl'])
        if sl <= 0 or px <= 0:
            continue
        out[m].append((abs(px - sl) / px, pnl[pid]))
    return out

runs = {lab: load(p) for p, lab in zip(sys.argv[1::2], sys.argv[2::2])}
labels = list(runs)

for name in ('SCA_UJ', 'SCA_GJ'):
    print(f'\n################ {name} ################')
    base = {l: sum(x[1] for x in runs[l][name]) for l in labels}
    print('  基準(全件): ' + '  '.join(f'{l}={base[l]:>12,.0f} (n={len(runs[l][name])})' for l in labels))
    print(f'\n  --- 下限 RangeMin（比 >= thr だけ残す）---')
    print('   thr      ' + '  '.join(f'{l:>26}' for l in labels))
    for thr in GRID:
        cells = []
        for l in labels:
            k = [x for x in runs[l][name] if x[0] >= thr]
            cells.append(f'{sum(x[1] for x in k):>12,.0f} Δ{sum(x[1] for x in k)-base[l]:>+11,.0f}')
        print(f'  {thr:.4f}  ' + '  '.join(cells))
    print(f'\n  --- 上限 RangeMax（比 <= thr だけ残す）---')
    print('   thr      ' + '  '.join(f'{l:>26}' for l in labels))
    for thr in GRID:
        cells = []
        for l in labels:
            k = [x for x in runs[l][name] if x[0] <= thr]
            cells.append(f'{sum(x[1] for x in k):>12,.0f} Δ{sum(x[1] for x in k)-base[l]:>+11,.0f}')
        print(f'  {thr:.4f}  ' + '  '.join(cells))
