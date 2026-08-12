from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DEALS=ROOT/'ml/tradeoff8/deals'
OUT=ROOT/'ml/simverify'
LEGS=["pullback_usdjpy_h4","pullback_gbpjpy_h4","pullback_audjpy_h4",
"rsi_robust_usdjpy_h4","rsi_robust_eurusd_h1","rsi_robust_gbpusd_h4",
"pairtrade_eurusd_gbpusd","pullback_gold_h4","carry_audjpy_d1","sca_usdjpy_m15",
"sca_gbpjpy_m15","sca_gold_m15","eth_ea_d1","fundingrev_btcusd_d1","bfxrev_btcusd_d1"]
CAND={"pullback_usdjpy_h4","pullback_gbpjpy_h4","pullback_audjpy_h4","rsi_robust_usdjpy_h4","carry_audjpy_d1","fundingrev_btcusd_d1","bfxrev_btcusd_d1"}
PB={x for x in LEGS if x.startswith('pullback_')}

def base(exclude=set()):
 rows=[]
 for leg in LEGS:
  if leg in exclude: continue
  v='candidate' if leg in CAND else 'baseline'
  d=pd.read_csv(DEALS/f't8_pf_{v}_{leg}.csv')[['time','profit']]
  rows.append(d)
 return pd.concat(rows,ignore_index=True)
def met(d):
 d=d.sort_values('time'); p=d.profit.to_numpy(float); eq=1_500_000+np.r_[0,np.cumsum(p)]
 pk=np.maximum.accumulate(eq); dd=(pk-eq)/pk*100
 return {'net':p.sum(),'dd_pct':dd.max()}
def actual(name): return pd.read_csv(OUT/f'deals/{name}_virtual.csv')[['time','profit']]

b=met(base())
pb_off=met(pd.concat([base(PB),actual('pb_off')],ignore_index=True))
pb_on=met(pd.concat([base(PB),actual('pb_on')],ignore_index=True))
adjusted={'net':b['net']+(pb_on['net']-pb_off['net']),
          'dd_pct':b['dd_pct']+(pb_on['dd_pct']-pb_off['dd_pct'])}
rows=[{'case':'baseline_round4',**b},{'case':'pb_hybrid_off',**pb_off},{'case':'pb_hybrid_on',**pb_on},
      {'case':'F14_actual_matched_delta',**adjusted}]
pd.DataFrame(rows).to_csv(OUT/'simverify_portfolio_summary.csv',index=False,encoding='utf-8-sig')
print(pd.DataFrame(rows).to_string(index=False))
