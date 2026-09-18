# SCA の損益が「リバーサルBoost が乗った部分集合」に依存しているかを取引ログから切り分ける。
# Boost 判定はロット（GBPJPY は 0.01x6=0.06、USDJPY は 0.01x2=0.02）で行う。
import csv, glob, io, os

BASE = r'C:\Users\f\source\repos\mt5_backtester\ml\fxqual4\run_deals'
SCA = {20261000: ('SCA_UJ', 0.02), 20261001: ('SCA_GJ', 0.06)}
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
    for mg, (name, blot) in SCA.items():
        grp = {'Boost': [], 'plain': []}
        for d in pos.values():
            if d['m'] != mg: continue
            risk = abs(d['e'] - d['sl']) * 100000.0 * d['v']
            g = 'Boost' if abs(d['v'] - blot) < 1e-9 else 'plain'
            grp[g].append((d['p'], d['p'] / risk if risk > 0 else 0.0))
        for g in ['plain', 'Boost']:
            v = grp[g]
            if not v: continue
            print('  %s %-6s n=%4d  純益 %+8.0f  平均R %+.3f  合計R %+7.1f' % (
                name, g, len(v), sum(x[0] for x in v),
                sum(x[1] for x in v) / len(v), sum(x[1] for x in v)))
