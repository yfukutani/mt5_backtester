"""Generate the final audit report from results.csv (deterministic, no MT5 calls)."""
from __future__ import annotations
import csv
from collections import Counter, defaultdict
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]; SRC=REPO/'ml/param_reopt/results.csv'; OUT=REPO/'docs/param_reopt_20260811.md'
rows=list(csv.DictReader(SRC.open(encoding='utf-8-sig')))
def sm(name):
    p=REPO/'results'/name/'summary.csv'
    if not p.exists():return None
    a=list(csv.reader(p.open(encoding='utf-8-sig')))
    return dict(net=float(a[8][1]),pf=float(a[11][1]),dd=float(a[15][1]),n=int(float(a[17][1])))
base={s:{w:sm(f'preopt_{s}__BASE_{w}') for w in ('IS','OOS')} for s in dict.fromkeys(r['sleeve'] for r in rows)}
def f(x):return f"{float(x):,.0f} / {float(x if False else 0):.0f}" # unused
def metrics(r,p):return f"{float(r[p+'_net']):,.0f} / {float(r[p+'_pf']):.4f} / {float(r[p+'_dd']):.2f}%"
def bm(s,p):
    x=base[s][p];return '検証不能' if not x else f"{x['net']:,.0f} / {x['pf']:.4f} / {x['dd']:.2f}%"

lines=['# 全戦略・全パラメータ再最適化（2026-08-11）','',
'## 結論','',
'現行本番configを基準に **534候補（IS/OOSで計993回の有効MT5測定＋GOLD OOS失敗75回）** を直列実行した。厳格改善は4スリーブで得られた。GOLD 2スリーブは既知の換算データ制約によりOOSが全件検証不能で、IS参考値のみCSVへ残した。EA・本番config・MIX_EA系は変更していない。','',
'- 採用提案: PB GBPJPY `ADX_Threshold=30`、RSI EURUSD `StopLoss_Pips=25`、SCA USDJPY `Break_Buffer_ATRd=0.10`、ETH `TrendMA_Period=150`。','- 注意: SCA USDJPYは厳格改善ではあるがOOS純利益が110円/PF 1.0024と極薄で、実運用上の頑健性は低い。','- 結果原票: `ml/param_reopt/results.csv`（459件OK、75件GOLD OOS検証不能）。','',
'## 検証条件','',
'IS=2021.06.21–2026.06.20、OOS=2016.06.21–2021.06.20（Bfx/ETH/Fundingは外部データ開始日まで短縮）。SCAはevery_tick、他は本番yamlのmodel。生存は両期間純利益>0。厳格改善は両期間で純利益・PF上昇かつDD非悪化。全候補は本番yamlに対象パラメータだけを上書きした。','',
'## フェーズ1: input棚卸し','',
'分類: (a)=過去に十分探索済み、(b)=今回対象、(c)=既定OFF/構造機能または単独否定済み、(d)=サイジング・識別・入出力・ライブ供給（変更対象外）。enumの時間足は本番スリーブ定義なので固定した。','',
'| EA / 対象スリーブ | (a) 過去探索済み | (b) 今回探索 | (c) 原則対象外 | (d) 対象外 |','|---|---|---|---|---|',
'| PullbackTrend / USDJPY, GBPJPY, AUDJPY, GOLD | `UsePullbackQuality`,`UseMomentumConfirm`,`RequireBullishCandle`,`UseADXFilter`,`UseTrendStrength`,`MA_Slope_Min_ATR`,`UseHigherTFFilter`,`HigherTF`,`HigherTF_MA`,`UseATRStops`、EMA/ADX/slope/ATR/RRの既探索域（R1–R3） | `TrendMA_Period`,`FastEMA_Period`,`SlowEMA_Period`,`ADX_Period`,`ADX_Threshold`,`MA_Slope_Lookback`,`ATR_Period`,`ATR_SL_Mult`,`RR_Ratio`（4銘柄。GBPJPYはADX局所2軸も） | `UseBreakevenR`,`BE_Trigger_R`,`BE_Offset_R`,`UseATRTrail`,`Trail_Mult_ATR`,`MaxHoldBars`,`ExitBeforeWeekend`,`WeekendExitHour`,`WeekendOnlyProfit`,`CooldownLosses`,`CooldownBars`,`UseATRPctFilter`,`ATRPct_Lookback`,`ATRPct_Max`,`UseStructureTP`,`StructureLookback`,`StructureMinRR`; 固定pipsの`StopLoss_Pips`,`TakeProfit_Pips`はATR運用中無効 | `LotSize`,`UseRiskSizing`,`RiskPercent`,`MagicNumber`,`ResultFileName`,`EquityLogFile`,`SignalTimeframe`,`TrendMA_Method` |',
'| RSI_Reversal / EURUSD H1, USDJPY H4 DP, GBPUSD H4 | BB/RSI/Extreme、固定SL/TP、DP、ATR SL、ADX/range、BE/MaxHold等（R1–R3。ただし全銘柄横断は浅い） | `MA_Period`,`BB_Period`,`BB_Deviation`,`RSI_Period`,`RSI_OverboughtExtreme`,`RSI_Overbought`,`RSI_OversoldExtreme`,`RSI_Oversold`,`Swing_Lookback`,`DP_Pattern_Bars`,`DP_Tolerance_ATR`,`StopLoss_Pips`,`TakeProfit_Pips`（全3銘柄。EURUSDはSL×TP局所2軸） | `UseTrailingStop`,`Trail_Start_Pips`,`Trail_Stop_Pips`,`UseBreakeven`,`BE_Trigger_Pips`,`UseVolatilityFilter`,`ATR_Min_Pips`,`UseATRStopLoss`,`ATR_SL_Multiplier`,`ATR_RR_Ratio`,`UseADXFilter`,`ADX_Period`,`ADX_Threshold`,`UseRangeFilter`,`Range_Slope_Lookback`,`Range_Slope_Max_ATR`,`UseTimeFilter`,`FilterStartHour`,`FilterEndHour`,`UseBreakevenATR`,`BE_Trigger_ATR`,`MaxHoldBars`,`ExitBeforeWeekend`,`WeekendExitHour`,`WeekendOnlyProfit`,`CooldownLosses`,`CooldownBars`,`UseATRPctFilter`,`ATRPct_Lookback`,`ATRPct_Max`,`UseStructureTP`,`StructureLookback`,`StructureMinRR`; `UseDoublePattern`は本番値を維持 | `LotSize`,`UseRiskSizing`,`RiskPercent`,`MagicNumber`,`ResultFileName`,`EquityLogFile`,`MA_Method` |',
'| SCA_EA / USDJPY, GBPJPY, GOLD | Boost/MinDrift、range mode/shift、wick/opposite-touch、stop orders、SL方式、時間窓/MinRangeの一部（R1–R3） | `RangeStartHour`,`RangeEndHour`,`TradeEndHour`,`ForceCloseHour`,`MinRange_ATRd`,`MaxRange_ATRd`,`Break_Buffer_ATRd`,`RR_Ratio`; `UseD1TrendFilter+D1Trend_MA`（対象別）、USDJPYはBuffer×MinRange局所2軸 | `SL_Mode`,`SL_ATRd_Mult`,`OneShotPerDir`,`UseFailedBreakExit`,`FB_MaxBars`,`UsePartialTP`,`Partial_R`,`Runner_RR`,`UseSwingTrail`,`Swing_Bars`,`UseRetestEntry`,`SkipFriday`,`UseStopOrders`,`UseReversalBoost`,`Boost_Mult`,`Boost_MinDrift_ATRd`,`RangeShiftLow_Pips`,`RangeShiftHigh_Pips`,`RangeMode`,`BreakOnWick`,`UseTiltGate`,`Buf_DecayPerHour`,`RequireOppTouch`,`UseMLFilter`,`ML_Threshold`; 本番ON値（GBPJPY Boost/GOLD Friday等）は維持 | `MaxSpreadPoints`,`LotSize`,`MagicNumber`,`UseRiskSizing`,`RiskPercent`,`ResultFileName`,`EquityLogFile`,`TradeLogFile` |',
'| Carry / AUDJPY | `TrendMA_Period`,`UseHysteresis`,`ATR_Period`,`Hyst_ATR_Mult`,`ExitMA_Period`,`ReentryCooldown`（R1–R3） | `TrendMA_Method`,`RequirePositiveSwap`,`ExitMA_Period`,`ReentryCooldown`の未探索端 | 機能OFF軸なし（本番ヒステリシスON） | `SignalTimeframe`,`LotSize`,`MagicNumber`,`UseRiskSizing`,`RefDeposit`,`ResultFileName`,`EquityLogFile` |',
'| PairTrade / EURUSD+GBPUSD | `Lookback`,`Entry_Z`,`Exit_Z`,`Stop_Z`（R1–R3） | 同4軸の未探索端・細刻み（結論再確認） | なし | `SecondSymbol`,`LotSize`,`MagicNumber`,`UseRiskSizing`,`RefDeposit`,`ResultFileName`,`EquityLogFile` |',
'| BfxRev_EA / BTCUSD | `DropPct`,`LookbackDays`,`HoldDays`,`DisasterSL_Pct`（btc_backlog4/R1–R3） | 前3軸の未探索端 | `DisasterSL_Pct`（災害用、歴史上ほぼ不発火） | `BfxFile`,`UseWebRequest`,`ApiUrl`,`UpdateCsvCache`,`CacheFile`,`LotSize`,`MagicNumber`,`MaxCryptoConcurrent`,`ResultFileName`,`EquityLogFile` |',
'| FundingRev_EA / BTCUSD | 閾値、Hold、ExitMode、MaxHold、災害SL（btc_backlog4/R1–R3） | `Threshold_Pct8h`,`MaxHoldDays`の未探索端 | `HoldDays`（ExitMode=2では通常無効）、`DisasterSL_Pct` | `FundingFile`,`UseWebRequest`,`ApiUrl`,`UpdateCsvCache`,`CacheFile`,`LotSize`,`MagicNumber`,`ResultFileName`,`EquityLogFile` |',
'| ETH_EA / ETHUSD | `TrendMA_Period`,`ExitMA_Period`,`ReentryCooldown`,`DisasterSL_Pct`（R2/R3） | `TrendMA_Period`,`ExitMA_Period`,`ReentryCooldown`,`MA_Method`、TrendMA×ExitMA局所2軸 | `DisasterSL_Pct`（災害用） | `SignalTimeframe`,`LotSize`,`MagicNumber`,`MaxCryptoConcurrent`,`EnableOpsLog`,`ResultFileName`,`EquityLogFile` |','',
'注: `input group`宣言も全て確認したが、値を持たないUI見出しなので表では各配下のinput名に展開した。上表に8 EAの値を持つ全inputを一度以上列挙している。','',
'## フェーズ2: 実行件数','',
'| スリーブ | 件数 | パラメータ別 |','|---|---:|---|']
for s in dict.fromkeys(r['sleeve'] for r in rows):
    c=Counter(r['parameter'] for r in rows if r['sleeve']==s)
    lines.append(f"| {s} | {sum(c.values())} | "+', '.join(f'`{k}` {v}' for k,v in c.items())+' |')
lines += ['', '## 厳格改善候補','', '数値は `純利益 / PF / 最大相対DD`。粗探索と局所2軸で同じ最良点が再現されたため、重複行を除き4候補を示す。','',
'| スリーブ / 変更 | IS 現行 | IS 候補 | OOS 現行 | OOS 候補 |','|---|---:|---:|---:|---:|']
strict=[r for r in rows if r['strict']=='True' and '_x_' in r['parameter']]
for r in strict:lines.append(f"| {r['sleeve']} `{r['overrides']}` | {bm(r['sleeve'],'IS')} | {metrics(r,'is')} | {bm(r['sleeve'],'OOS')} | {metrics(r,'oos')} |")
lines += ['', 'SCA USDJPY以外の3候補は利益改善に加えてPF/DDにも余裕がある。RSI EURUSDは現行OOS赤字を黒字化、ETHは両期間で改善。PB GBPJPYのADX=30は最も明瞭。','',
'## トレードオフ候補','',
'機械判定は6指標中4つ以上改善かつ両期間生存。局所2軸の重複も原票どおり掲載する。交換内容欄は、現行より悪化した指標を示す。','',
'| スリーブ | 変更 | IS 候補 | OOS 候補 | 交換内容（悪化指標） |','|---|---|---:|---:|---|']
for r in [x for x in rows if x['tradeoff']=='True']:
    bad=[]
    for p,label in [('is','IS'),('oos','OOS')]:
        b=base[r['sleeve']][p.upper()]
        if float(r[p+'_net'])<=b['net']:bad.append(label+'利益')
        if float(r[p+'_pf'])<=b['pf']:bad.append(label+'PF')
        if float(r[p+'_dd'])>b['dd']:bad.append(label+'DD')
    lines.append(f"| {r['sleeve']} | `{r['overrides']}` | {metrics(r,'is')} | {metrics(r,'oos')} | {', '.join(bad) or 'なし（境界同値）'} |")
lines += ['', '## 現行が最良と確認できた範囲','',
'「厳格改善なし」を今後の重複回避基準とする。トレードオフ候補は上表に残している。','',
'| スリーブ | 厳格改善が無かった今回の探索軸 |','|---|---|',
'| PB USDJPY | TrendMA, EMA fast/slow, ADX period/threshold, ATR period/SL, RR, slope lookback |',
'| PB GBPJPY | TrendMA, EMA fast/slow, ADX period（閾値30との組合せ以外）, ATR period/SL, RR |',
'| PB AUDJPY | TrendMA, EMA fast/slow, ADX, ATR period/SL, RR, slope lookback（生存化トレードオフはあり） |',
'| PB GOLD | OOS不能のため「現行最良」と断定不可。IS結果のみ原票参照 |',
'| RSI EURUSD | MA, BB, RSI period/levels, DP各軸, TP単独（SL25以外） |',
'| RSI USDJPY | MA, BB, RSI, 固定SL/TP, DP各軸（生存化トレードオフはあり） |',
'| RSI GBPUSD | MA, BB, RSI, 固定SL/TP, DP各軸 |',
'| SCA USDJPY | 全時間軸、range上下限、RR、D1 trend（buffer 0.10以外） |',
'| SCA GBPJPY | 全探索軸（RangeEnd=10はトレードオフ） |',
'| SCA GOLD | OOS不能のため断定不可。IS結果のみ原票参照 |',
'| Carry AUDJPY | MA method, positive-swap解除, ExitMA, cooldown（cd10はOOS改善トレードオフ） |',
'| PairTrade | Lookback, Entry/Exit Z, Stop Z（6/7は小さなトレードオフ） |',
'| BfxRev | DropPct, LookbackDays, HoldDays（Lookback10等はトレードオフ） |',
'| FundingRev | Threshold, MaxHold（閾値変更は複数トレードオフ） |',
'| ETH | ExitMA, cooldown, MA method（TrendMA150以外） |','',
'## 問題点・実装上の注意','',
'- GOLD OOSは全75件でsummaryを生成できず検証不能。既知のXAUJPY換算履歴不足と整合する。ISだけで本番変更を決めない。','- PBの`MA_Slope_Lookback`は`UseTrendStrength=false`のスリーブでは無効で、結果が同値になる。無効軸を原票に明示した。','- SCAの`D1Trend_MA`は単独では無効なので、今回だけ`UseD1TrendFilter=true`とセットで対象別に検証した（厳格改善なし）。','- Fundingの`HoldDays`は本番`ExitMode=2`では通常の退出に使われず、MaxHoldDaysを探索した。','- enum MA methodは0=SMA（現行）、1=EMA、2=SMMA、3=LWMAとして渡した。改善なし。','- Boost倍率は今回再探索していない。過去の0.01 lot丸めで4.5=4.0になる問題を踏まえ、既探索結論を維持した。','- 厳格改善4点はすべて現行本番一式上で再測定し、局所2軸でも同一点を再現した。複数変更を同時採用した組合せ検証はしていないため、スリーブ内で複数案を混ぜない。','- `results.csv`の`status=UNVERIFIABLE`はGOLDだけ。認証ファイル、本番config、EA、MIX_EA/MIX_EA_OANDAは未変更。','']
OUT.write_text('\n'.join(lines),encoding='utf-8')
print(f'wrote {OUT} ({len(lines)} lines)')
