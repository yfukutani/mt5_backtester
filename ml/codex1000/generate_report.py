from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'ml'/'codex1000'
p=pd.read_csv(OUT/'proposals.csv')
r=pd.read_csv(OUT/'results.csv')
b=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))

def fmt(x): return f"{x:,.4f}" if abs(x)<100 else f"{x:,.1f}"
def metric_row(name,x):
    return f"| {name} | {x['net']:,.1f} | {x['pf']:.4f} | {x['dd_pct']:.4f}% | {x['net']/x['dd_pct']:,.0f} |"

events=[]
for leg in [
 'pullback_usdjpy_h4','pullback_gbpjpy_h4','pullback_audjpy_h4','rsi_robust_usdjpy_h4',
 'rsi_robust_eurusd_h1','rsi_robust_gbpusd_h4','pairtrade_eurusd_gbpusd','pullback_gold_h4',
 'carry_audjpy_d1','sca_usdjpy_m15','sca_gbpjpy_m15','sca_gold_m15','eth_ea_d1',
 'fundingrev_btcusd_d1','bfxrev_btcusd_d1']:
    cand=leg in {'pullback_usdjpy_h4','pullback_gbpjpy_h4','pullback_audjpy_h4','rsi_robust_usdjpy_h4','carry_audjpy_d1','fundingrev_btcusd_d1','bfxrev_btcusd_d1'}
    d=pd.read_csv(ROOT/'ml'/'tradeoff8'/'deals'/f"t8_pf_{'candidate' if cand else 'baseline'}_{leg}.csv")
    d['time']=pd.to_datetime(d.time,unit='s',utc=True); d['leg']=leg; events.append(d)
d=pd.concat(events)
d['year']=d.time.dt.year; d['month']=d.time.dt.month; d['hour']=d.time.dt.hour; d['weekday']=d.time.dt.day_name()
for col in ['year','month','hour','weekday','leg']:
    q=d.groupby(col).profit.agg(['sum','count']).reset_index().rename(columns={'sum':'net','count':'deal_rows'})
    q.to_csv(OUT/f'quality_by_{col}.csv',index=False,encoding='utf-8-sig')

family=[]
for fid,g in p.groupby('family',sort=False):
    rr=r[r.family==fid]
    first=g.iloc[0]
    family.append(f"| {fid} | {first.family_name} | {len(g)} | {first['class']} | {(rr.status=='OK').sum()} | {rr.survive.sum()} | {rr.strict.sum()} | {rr.tradeoff.sum()} | {first.overview} |")

strict=r[r.strict==True]
strict_lines=[]
for x in strict.itertuples():
    strict_lines.append(f"| {x.proposal_id} | `{x.params}` | {x.is_net:,.1f}/{x.is_pf:.4f}/{x.is_dd_pct:.4f}% | {x.oos_net:,.1f}/{x.oos_pf:.4f}/{x.oos_dd_pct:.4f}% | {x.full_net:,.1f}/{x.full_dd_pct:.4f}%/{x.full_net/x.full_dd_pct:,.0f} |")

trade=r[r.tradeoff==True].sort_values('full_net',ascending=False)
trade.to_csv(OUT/'tradeoff_candidates.csv',index=False,encoding='utf-8-sig')
trade_lines=[]
for x in trade.itertuples():
    bad=[]
    for w in ['is','oos']:
        if getattr(x,f'{w}_net')<=b[w]['net']: bad.append(f'{w.upper()}利益')
        if getattr(x,f'{w}_pf')<=b[w]['pf']: bad.append(f'{w.upper()}PF')
        if getattr(x,f'{w}_dd_pct')>b[w]['dd_pct']: bad.append(f'{w.upper()}DD')
    trade_lines.append(f"| {x.proposal_id} | `{x.params}` | {x.full_net:,.1f} | {x.full_dd_pct:.4f}% | {x.full_net/x.full_dd_pct:,.0f} | {', '.join(bad)} |")

year=d.groupby('year').profit.sum().sort_values()
weak='、'.join(f'{int(k)}年 {v:,.0f}' for k,v in year.head(3).items())
c_lines=[]
for x in p[p['class']=='C'].itertuples(): c_lines.append(f"| {x.proposal_id} | {x.family_name} | {x.overview} | {x.test_method} |")

txt=f"""# Codex 1000案 Round 4 検証（2026-08-12）

## 結論

重複を除いた新規案を **1,000案**作成した。内訳は、既存inputだけの(A) 0案、検証専用のdeal時系列後処理で実行可能な(B) **960案**、追加データまたは大規模開発が必要な(C) **40案**である。(B)は全960案を実行し、IS/OOS生存936案、厳格改善1案、ポートフォリオ全期間の利益/DD比が改善するトレードオフ15案だった。

唯一の厳格改善は **F15-17: RSI群の直近8完了dealの平均損益が負なら次のentry lotを50%に縮小**。現行比で全期間純利益 **+{strict.iloc[0].full_net-b['full']['net']:,.1f}**、DD **{strict.iloc[0].full_dd_pct-b['full']['dd_pct']:+.4f}pt**、純利益÷DD% **{strict.iloc[0].full_net/strict.iloc[0].full_dd_pct-b['full']['net']/b['full']['dd_pct']:+,.0f}**。ただしdealログにはposition IDがないため、同一スリーブ内のentry/exitはFIFO対応である。採用前には検証専用EAまたはposition ID付きログで再現確認が必要で、今回の結果だけで本番採用とはしない。

## 方法と境界

- `tradeoff8` の保存済みMT5 deal列から現行15configを再構成。SCA GBPJPY RangeEnd10は除外し、Funding -0.003、PB USDJPY ADX27.5、PB GBPJPY Slow35、PB AUDJPY RR5、RSI USDJPY tolerance1.5、Carry cooldown10、Bfx lookback10を反映した列を採用した。
- 再構成baselineは純利益 **1,137,149**、最大DD **2.3745%**で依頼記載値と一致した。よって候補は最新パラメータ一式の上で比較されている。
- 各案はentryのゼロ損益deal時点で、それ以前に確定した損益だけからrisk倍率を決定。exit損益にその倍率を乗じ、IS/OOS/全期間をイベント順に再生した。未来情報は使っていない。
- IS=2021-06-21〜2026-06-20、OOS=2016-06-21〜2021-06-20。生存・厳格改善定義は依頼どおり。全候補は15スリーブ合算で最初から評価した。
- MT5は起動していない。本番yaml、`MIX_EA.mq5`、`MIX_EA_OANDA.mq5`、認証情報は未変更。GOLD単独OOSも実行していない。
- (A)を無理に水増ししなかった理由は、全inputが直前の534候補棚卸し対象で、単純な再走は重複になるため。(C)は今回未検証。

## baseline

| 期間 | 純利益 | PF | 最大DD% | 純利益÷DD% |
|---|---:|---:|---:|---:|
{metric_row('IS',b['is'])}
{metric_row('OOS',b['oos'])}
{metric_row('全期間',b['full'])}

## 全ファミリー

各ファミリーの40バリエーションは原則 `lookback={{8,12,20,30,45,60,90,120}} × risk_scale={{0,0.25,0.5,0.75,0.9}}`。Cは10個ずつ、データ源・対象群・閾値・処理方法を分解した。全案の個別記述は `proposals.csv` にある。

| ID | ファミリー | 案数 | 分類 | 実行 | 生存 | 厳格 | tradeoff | 概要／テスト |
|---|---|---:|:---:|---:|---:|---:|---:|---|
{chr(10).join(family)}

## 厳格改善候補

表記は `純利益/PF/DD%`。

| 案 | パラメータ | IS候補 | OOS候補 | 全期間 利益/DD/比 |
|---|---|---:|---:|---:|
{chr(10).join(strict_lines)}

F15-17の全期間PFは **{strict.iloc[0].full_pf:.4f}**（baseline {b['full']['pf']:.4f}）。利益、PF、DDはIS/OOSの両方で厳格条件を満たす。

## トレードオフ候補

次の15案は両期間生存かつ全期間の利益と純利益÷DD%がbaselineを超えるが、IS/OOS六条件のどれかを満たさない。交換内容にはbaselineより悪い指標を列挙した。

| 案 | パラメータ | 全期間利益 | DD | 利益÷DD% | 交換内容 |
|---|---|---:|---:|---:|---|
{chr(10).join(trade_lines)}

## ポートフォリオ合算で確認した効果

| 構成 | 純利益 | 最大DD% | 純利益÷DD% | baseline差 |
|---|---:|---:|---:|---|
| baseline 15config | {b['full']['net']:,.1f} | {b['full']['dd_pct']:.4f}% | {b['full']['net']/b['full']['dd_pct']:,.0f} | — |
| F15-17 | {strict.iloc[0].full_net:,.1f} | {strict.iloc[0].full_dd_pct:.4f}% | {strict.iloc[0].full_net/strict.iloc[0].full_dd_pct:,.0f} | 利益 {strict.iloc[0].full_net-b['full']['net']:+,.1f}, DD {strict.iloc[0].full_dd_pct-b['full']['dd_pct']:+.4f}pt |

これは個別スリーブの結果を後から良く見せたものではなく、15本の全dealを時刻順に合算した結果である。

## 収益源の質と弱点

現行deal列を年、月、曜日、時刻、スリーブ別に集計し、`quality_by_*.csv`へ保存した。利益の弱い3年は **{weak}**。F07〜F10/F23/F24はこの偏りをpoint-in-time規則だけで補えるか直接検証したが、厳格改善は0だった。つまりカレンダー依存は事後には見えても、翌期へ安定して移植できなかった。一方、RSI群の短期確定損益悪化は8deal窓の50%縮小だけが両期間で再現した。

## 「現行が最良」と確認できた範囲

- portfolio/sleeve DD throttle 160通り（F01,F02,F21,F22）: 厳格改善なし。
- rolling expectancy/PF/勝率 120通り（F04〜F06）: 厳格改善なし。
- 曜日/月/時刻/四半期・前年/前四半期 240通り（F07〜F10,F23,F24）: 厳格改善なし。
- JPY/crypto/SCA/PB/GOLD cluster 200通り（F11〜F14,F16）: 厳格改善なし。RSI clusterだけ上記1案。
- rank/concentration/実現vol 160通り（F17〜F20）: 厳格改善なし。
- この確認範囲は保存dealに対する因果的lot制御であり、真の同時position exposure、spread、方向deltaまでは含まない。

## (C) 未検証案

| 案 | family | 概要 | 必要な検証 |
|---|---|---|---|
{chr(10).join(c_lines)}

## コード監査で気づいた問題

1. `mt5bt` が保存するdeal CSVは `time, profit` が中心で、position ID、entry/exit種別、方向、SL距離、spread、slippageがない。D01/D03/D05/D09/D11の厳密検証には不足する。
2. ゼロ損益行をentryとしてFIFOで非ゼロ損益行へ対応させた。同一スリーブで重複positionや部分決済がある場合は対応誤差が生じ得る。F15-17の再確認が必要な主因である。
3. portfolio DD%は全15本の初期資金150万に対するdeal確定時equityで、含み損DDではない。同時保有リスクを完全には表さない。
4. D10/D11/D13はbroker時刻、tick cost、point-in-time eventデータが保存されておらず、deal列だけでの代理検証を避けた。
5. 既存deal列で現行純利益/DDを完全再現できたため、入力選択と合算式の基準整合性には問題がなかった。

## 成果物

- `ml/codex1000/proposals.csv`: 全1,000案
- `ml/codex1000/results.csv`: 960実行結果＋40未検証記録
- `ml/codex1000/tradeoff_candidates.csv`: tradeoff 15案
- `ml/codex1000/quality_by_*.csv`: 収益源の質
- `ml/codex1000/baseline.json`: baseline指標
- `ml/codex1000/run_round4.py`, `generate_report.py`: 再現スクリプト
"""
(ROOT/'docs'/'codex1000_round4_20260812.md').write_text(txt,encoding='utf-8')
print('written',len(p),len(r),len(txt))
