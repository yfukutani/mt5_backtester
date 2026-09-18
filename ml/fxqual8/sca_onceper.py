# 「日×方向」あたりの建玉は本当に高々1件か、を約定ログで確かめる。
# ここが1件なら、rev ゲートで止めた日×方向は後ろの足へずれようが無い
# （時間帯ゲートは10時に解除されるが、rev は日内で解除されない）。
import csv, glob, io, os, datetime, collections

BASE = r'C:\Users\f\source\repos\mt5_backtester\ml\fxqual4\run_deals'
SCA = {20261000: 'SCA_UJ', 20261001: 'SCA_GJ'}
found = {}
for f in glob.glob(os.path.join(BASE, '*_W000_*_deals.csv')):
    found['OOS' if os.path.basename(f).startswith('mc_oos') else 'IS'] = f

for w in ['OOS', 'IS']:
    rows = list(csv.DictReader(io.open(found[w], encoding='utf-8', errors='replace')))
    cnt = collections.Counter()
    hours = collections.defaultdict(collections.Counter)
    for r in rows:
        m = int(r['magic'] or 0)
        if int(r['entry']) != 0 or m not in SCA:
            continue
        t = datetime.datetime.fromtimestamp(int(r['time']), datetime.timezone.utc)
        key = (m, t.date(), int(r['type']))
        cnt[key] += 1
        hours[m][t.hour] += 1
    print('====', w)
    for mg, name in SCA.items():
        sub = {k: v for k, v in cnt.items() if k[0] == mg}
        multi = {k: v for k, v in sub.items() if v > 1}
        print('  %s  日x方向の組=%d  建玉合計=%d  **2件以上の組=%d**' % (
            name, len(sub), sum(sub.values()), len(multi)))
        hh = sorted(hours[mg].items())
        print('     発注時刻の内訳: ' + '  '.join('%02d時:%d' % (h, n) for h, n in hh))
