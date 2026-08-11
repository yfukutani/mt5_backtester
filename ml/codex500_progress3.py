import csv
from collections import Counter

rows = list(csv.DictReader(open('ml/codex500/results3.csv', encoding='utf-8')))
print('完了候補数:', len(rows))
print('verdict:', dict(Counter(r.get('verdict', '') for r in rows)))
fams = Counter(r.get('family', '') for r in rows)
print('ファミリー別進捗:')
for f, n in fams.items():
    print('  %-40s %d' % (f, n))
print('直近3件:', [r['id'] for r in rows[-3:]])
