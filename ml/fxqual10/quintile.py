import csv, sys, collections

# SCA の「レンジ幅」= エントリ価格と SL の距離。
# risk% サイジングでは lot ∝ 1/距離 なので、狭いレンジほど重く張られる。
# 距離の分位ごとに 1) 取引数 2) 合計損益 3) 平均R を出す。

MAG = {'20261000': 'SCA_UJ', '20261001': 'SCA_GJ'}

def analyze(path, label):
    rows = list(csv.DictReader(open(path, newline='', encoding='utf-8')))
    ent = {}
    pnl = collections.defaultdict(float)
    for r in rows:
        pid = r['position_id']
        if r['entry'] == '0':
            ent[pid] = r
        pnl[pid] += float(r['profit'] or 0)

    for mag, name in MAG.items():
        recs = []
        for pid, e in ent.items():
            if e['magic'] != mag:
                continue
            px, sl = float(e['price']), float(e['sl'])
            if sl <= 0:
                continue
            recs.append((abs(px - sl), float(e['volume']), pnl[pid]))
        if not recs:
            continue
        recs.sort()
        n = len(recs)
        print(f'\n=== {label} / {name}  n={n}  total={sum(r[2] for r in recs):,.0f} ===')
        print(f'{"quintile":>8} {"dist_lo":>9} {"dist_hi":>9} {"n":>4} {"avg_lot":>8} {"sum_pnl":>12} {"avg_pnl":>9}')
        q = 5
        for i in range(q):
            a, b = n * i // q, n * (i + 1) // q
            sub = recs[a:b]
            if not sub:
                continue
            s = sum(x[2] for x in sub)
            print(f'{i+1:>8} {sub[0][0]:>9.5f} {sub[-1][0]:>9.5f} {len(sub):>4} '
                  f'{sum(x[1] for x in sub)/len(sub):>8.3f} {s:>12,.0f} {s/len(sub):>9,.0f}')

        # 累積: 「距離 >= しきい値」だけ残したときの合計
        print('  --- レンジ幅下限を入れたら（距離>=thr だけ残す） ---')
        for thr in (0.0030, 0.0040, 0.00475, 0.00595, 0.0070, 0.0085, 0.0100):
            scale = 1.0 if name == 'SCA_UJ' else 1.0
            kept = [x for x in recs if x[0] >= thr * (100.0 if name == 'SCA_UJ' else 100.0)]
            # 距離は価格単位（USDJPY/GBPJPY は 100 円台なので thr は比率ではない）
        # 価格単位のまましきい値を出す
        lo, hi = recs[0][0], recs[-1][0]
        for k in range(1, 10):
            thr = lo + (hi - lo) * k / 20.0
            kept = [x for x in recs if x[0] >= thr]
            cut = [x for x in recs if x[0] < thr]
            print(f'   thr={thr:8.5f}  残{len(kept):>4}件 {sum(x[2] for x in kept):>12,.0f}   '
                  f'切{len(cut):>4}件 {sum(x[2] for x in cut):>12,.0f}')

for path, label in zip(sys.argv[1::2], sys.argv[2::2]):
    analyze(path, label)
