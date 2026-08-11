import csv

rows = list(csv.DictReader(open('ml/codex500/results2.csv', encoding='utf-8')))
targets = [
    'F9_UseStructureTP-true_StructureLookback-30_StructureMinRR-1.5',
    'F9_UseStructureTP-true_StructureLookback-20_StructureMinRR-2.0',
    'F21_boost3_mode0_sl0.5',
    'F21_boost4_mode0_sl0.5',
    'F5_ma200_ema25-60',
    'F5_ma200_ema20-50',
]
byid = {r['id']: r for r in rows}
for t in targets:
    r = byid.get(t)
    if r:
        print('%-70s IS=%9s(pf%s,dd%s) OOS=%9s(pf%s,dd%s)'
              % (t, r['is_net'], r['is_pf'], r['is_dd'], r['oos_net'], r['oos_pf'], r['oos_dd']))
