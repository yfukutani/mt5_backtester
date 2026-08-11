import csv

rows = list(csv.DictReader(open('ml/codex500/results2.csv', encoding='utf-8')))
targets = [
    'F4_ema20-50_q1m1',
    'F9_UseStructureTP-true_StructureLookback-30_StructureMinRR-1.5',
    'F9_UseStructureTP-true_StructureLookback-20_StructureMinRR-2.0',
    'F21_boost3_mode0_sl0.5',
    'F21_boost4_mode0_sl0.5',
    'F24_ExitMA_Period-80_ReentryCooldown-5',
    'F29_entry200_exit40_cd5',
]
byid = {r['id']: r for r in rows}
for t in targets:
    r = byid.get(t)
    if r:
        print('%-70s IS=%9s OOS=%9s verdict=%s' % (t, r['is_net'], r['oos_net'], r['verdict']))
    else:
        print('%-70s NOT FOUND' % t)
