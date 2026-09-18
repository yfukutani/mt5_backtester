import csv, glob, io, os, datetime
BASE = r'C:\Users\f\source\repos\mt5_backtester\ml\fxqual4\run_deals'
found = {}
for f in glob.glob(os.path.join(BASE, '*_W000_*_deals.csv')):
    found['OOS' if os.path.basename(f).startswith('mc_oos') else 'IS'] = f
MG = 20260650
for w in ['OOS', 'IS']:
    rows = list(csv.DictReader(io.open(found[w], encoding='utf-8', errors='replace')))
    pos = {}
    for r in rows:
        m = int(r['magic'] or 0); pid = r['position_id']
        if int(r['entry']) == 0:
            if m == MG:
                pos[pid] = {'t0': int(r['time']), 't1': None, 'p': 0.0,
                            'v': float(r['volume']), 'type': int(r['type'])}
        elif pid in pos:
            pos[pid]['p'] += float(r['profit'] or 0)
            pos[pid]['t1'] = int(r['time'])
    print('====', w, 'Carry n=', len(pos))
    for pid, d in sorted(pos.items(), key=lambda x: x[1]['t0']):
        a = datetime.datetime.fromtimestamp(d['t0'], datetime.timezone.utc)
        b = datetime.datetime.fromtimestamp(d['t1'], datetime.timezone.utc) if d['t1'] else None
        days = (d['t1'] - d['t0']) / 86400.0 if d['t1'] else None
        print('  %s -> %s  %6s日  lot %.2f %s  損益 %+9.0f' % (
            a.date(), b.date() if b else '(open)',
            ('%.0f' % days) if days else '-', d['v'],
            'BUY' if d['type'] == 0 else 'SELL', d['p']))
