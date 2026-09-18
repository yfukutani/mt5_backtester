# SCA の1取引あたり R 倍率の分布を、既存の取引ログから切り直す（バックテストは取らない）。
# R = 決済損益 / (|entry-sl| * 100000 * lot)   ※JPYクロスなので円建てはこれでよい
import csv, glob, io, os, collections

BASE = r'C:\Users\f\source\repos\mt5_backtester\ml\fxqual4\run_deals'
SCA = {20261000: 'SCA_UJ', 20261001: 'SCA_GJ'}
found = {}
for f in glob.glob(os.path.join(BASE, '*_W000_*_deals.csv')):
    found['OOS' if os.path.basename(f).startswith('mc_oos') else 'IS'] = f

for w in ['OOS', 'IS']:
    rows = list(csv.DictReader(io.open(found[w], encoding='utf-8', errors='replace')))
    pos = {}
    for r in rows:
        m = int(r['magic'] or 0); pid = r['position_id']
        if int(r['entry']) == 0:
            if m in SCA:
                pos[pid] = {'m': m, 'e': float(r['price']), 'sl': float(r['sl']),
                            'v': float(r['volume']), 'p': 0.0}
        elif pid in pos:
            pos[pid]['p'] += float(r['profit'] or 0)
    print('====', w)
    for mg, name in SCA.items():
        rs = []
        for d in pos.values():
            if d['m'] != mg: continue
            risk = abs(d['e'] - d['sl']) * 100000.0 * d['v']
            if risk <= 0: continue
            rs.append(d['p'] / risk)
        if not rs: continue
        buckets = collections.Counter()
        for x in rs:
            if x <= -0.95: b = 'SL(<=-0.95R)'
            elif x < -0.25: b = '-0.95..-0.25R'
            elif x < 0: b = '-0.25..0R'
            elif x < 0.5: b = '0..0.5R'
            elif x < 1.0: b = '0.5..1.0R'
            elif x < 1.9: b = '1.0..1.9R'
            else: b = 'TP(>=1.9R)'
            buckets[b] += 1
        n = len(rs)
        print(' %s n=%d  平均R=%.3f  合計R=%.1f' % (name, n, sum(rs) / n, sum(rs)))
        for b in ['SL(<=-0.95R)', '-0.95..-0.25R', '-0.25..0R', '0..0.5R', '0.5..1.0R', '1.0..1.9R', 'TP(>=1.9R)']:
            sub = [x for x in rs if (
                (b == 'SL(<=-0.95R)' and x <= -0.95) or
                (b == '-0.95..-0.25R' and -0.95 < x < -0.25) or
                (b == '-0.25..0R' and -0.25 <= x < 0) or
                (b == '0..0.5R' and 0 <= x < 0.5) or
                (b == '0.5..1.0R' and 0.5 <= x < 1.0) or
                (b == '1.0..1.9R' and 1.0 <= x < 1.9) or
                (b == 'TP(>=1.9R)' and x >= 1.9))]
            print('    %-14s %4d本 (%4.1f%%)  R計 %+7.1f' % (b, len(sub), 100.0 * len(sub) / n, sum(sub)))
