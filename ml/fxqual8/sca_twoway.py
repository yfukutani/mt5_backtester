# SCA の「同じ日に上下どちらも建てる」件数と損益を、既存の取引ログから切り直す。
# バックテストは取らない（簡易検証）。
import csv, datetime, collections, io, sys

BASE = r'C:\Users\f\source\repos\mt5_backtester\ml\fxqual4\run_deals'
RUNS = {'OOS': 'mc_oos_W000_20260918195950_e6e1', 'IS': 'mc_is_W000_20260918200426_dac6'}
import glob, os
# ファイル名が分からないので W000 を探す
found = {}
for f in glob.glob(os.path.join(BASE, '*_deals.csv')):
    b = os.path.basename(f)
    if '_W000_' not in b:
        continue
    w = 'OOS' if b.startswith('mc_oos') else 'IS'
    found[w] = f
SCA = {20261000: 'SCA_UJ', 20261001: 'SCA_GJ'}

for w in ['OOS', 'IS']:
    f = found.get(w)
    if not f:
        print(w, 'not found'); continue
    rows = list(csv.DictReader(io.open(f, encoding='utf-8', errors='replace')))
    # position_id -> {in: row, out_profit: sum}
    pos = {}
    for r in rows:
        m = int(r['magic']) if r['magic'] else 0
        pid = r['position_id']
        e = int(r['entry'])
        if e == 0:
            if m in SCA:
                pos[pid] = {'m': m, 't': int(r['time']), 'type': int(r['type']), 'p': 0.0}
        else:
            # 決済 deal は magic=0 のことがあるので position_id で引き直す
            if pid in pos:
                pos[pid]['p'] += float(r['profit'] or 0)
    print('====', w, 'SCA positions:', len(pos))
    for mg, name in SCA.items():
        byday = collections.defaultdict(list)
        for pid, d in pos.items():
            if d['m'] != mg:
                continue
            day = datetime.datetime.fromtimestamp(d['t'], datetime.timezone.utc).date()
            byday[day].append(d)
        one = [v[0] for k, v in byday.items() if len(v) == 1]
        both = {k: v for k, v in byday.items() if len(v) > 1}
        # 両建てが起きた日の「2本目」（時刻の遅いほう）
        seconds, firsts = [], []
        for k, v in both.items():
            v2 = sorted(v, key=lambda x: x['t'])
            firsts.append(v2[0]); seconds.extend(v2[1:])
        tot = sum(d['p'] for d in pos.values() if d['m'] == mg)
        print(' %s  日数=%d  1方向だけの日=%d(%+.0f)  両方向の日=%d  うち1本目=%+.0f  2本目=%d本 %+.0f  枠合計=%+.0f' % (
            name, len(byday), len(one), sum(d['p'] for d in one),
            len(both), sum(d['p'] for d in firsts), len(seconds), sum(d['p'] for d in seconds), tot))
