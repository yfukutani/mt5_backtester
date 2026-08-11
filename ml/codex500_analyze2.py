import csv
from collections import defaultdict

rows = list(csv.DictReader(open('ml/codex500/results2.csv', encoding='utf-8')))
byfam = defaultdict(list)
for r in rows:
    byfam[r['family']].append(r)
for fam in sorted(byfam, key=lambda x: int(x)):
    rs = byfam[fam]
    passed = [r for r in rs if r['verdict'] == 'PASS']
    syms = sorted(set(r.get('symbol', '') for r in rs))
    print('=== Family %s (symbols=%s, n=%d, PASS=%d) ===' % (fam, syms, len(rs), len(passed)))
    for r in sorted(passed, key=lambda r: -(float(r['is_net'] or 0) + float(r['oos_net'] or 0)))[:4]:
        print('  %-75s sym=%-8s IS=%9s OOS=%9s  ov=%s'
              % (r['id'], r.get('symbol', ''), r['is_net'], r['oos_net'], r['overrides'][:70]))
