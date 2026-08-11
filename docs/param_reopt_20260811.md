# 全戦略・全パラメータ再最適化（2026-08-11）

## 結論

現行本番configを基準に **534候補（IS/OOSで計993回の有効MT5測定＋GOLD OOS失敗75回）** を直列実行した。厳格改善は4スリーブで得られた。GOLD 2スリーブは既知の換算データ制約によりOOSが全件検証不能で、IS参考値のみCSVへ残した。EA・本番config・MIX_EA系は変更していない。

- 採用提案: PB GBPJPY `ADX_Threshold=30`、RSI EURUSD `StopLoss_Pips=25`、SCA USDJPY `Break_Buffer_ATRd=0.10`、ETH `TrendMA_Period=150`。
- 注意: SCA USDJPYは厳格改善ではあるがOOS純利益が110円/PF 1.0024と極薄で、実運用上の頑健性は低い。
- 結果原票: `ml/param_reopt/results.csv`（459件OK、75件GOLD OOS検証不能）。

## 検証条件

IS=2021.06.21–2026.06.20、OOS=2016.06.21–2021.06.20（Bfx/ETH/Fundingは外部データ開始日まで短縮）。SCAはevery_tick、他は本番yamlのmodel。生存は両期間純利益>0。厳格改善は両期間で純利益・PF上昇かつDD非悪化。全候補は本番yamlに対象パラメータだけを上書きした。

## フェーズ1: input棚卸し

分類: (a)=過去に十分探索済み、(b)=今回対象、(c)=既定OFF/構造機能または単独否定済み、(d)=サイジング・識別・入出力・ライブ供給（変更対象外）。enumの時間足は本番スリーブ定義なので固定した。

| EA / 対象スリーブ | (a) 過去探索済み | (b) 今回探索 | (c) 原則対象外 | (d) 対象外 |
|---|---|---|---|---|
| PullbackTrend / USDJPY, GBPJPY, AUDJPY, GOLD | `UsePullbackQuality`,`UseMomentumConfirm`,`RequireBullishCandle`,`UseADXFilter`,`UseTrendStrength`,`MA_Slope_Min_ATR`,`UseHigherTFFilter`,`HigherTF`,`HigherTF_MA`,`UseATRStops`、EMA/ADX/slope/ATR/RRの既探索域（R1–R3） | `TrendMA_Period`,`FastEMA_Period`,`SlowEMA_Period`,`ADX_Period`,`ADX_Threshold`,`MA_Slope_Lookback`,`ATR_Period`,`ATR_SL_Mult`,`RR_Ratio`（4銘柄。GBPJPYはADX局所2軸も） | `UseBreakevenR`,`BE_Trigger_R`,`BE_Offset_R`,`UseATRTrail`,`Trail_Mult_ATR`,`MaxHoldBars`,`ExitBeforeWeekend`,`WeekendExitHour`,`WeekendOnlyProfit`,`CooldownLosses`,`CooldownBars`,`UseATRPctFilter`,`ATRPct_Lookback`,`ATRPct_Max`,`UseStructureTP`,`StructureLookback`,`StructureMinRR`; 固定pipsの`StopLoss_Pips`,`TakeProfit_Pips`はATR運用中無効 | `LotSize`,`UseRiskSizing`,`RiskPercent`,`MagicNumber`,`ResultFileName`,`EquityLogFile`,`SignalTimeframe`,`TrendMA_Method` |
| RSI_Reversal / EURUSD H1, USDJPY H4 DP, GBPUSD H4 | BB/RSI/Extreme、固定SL/TP、DP、ATR SL、ADX/range、BE/MaxHold等（R1–R3。ただし全銘柄横断は浅い） | `MA_Period`,`BB_Period`,`BB_Deviation`,`RSI_Period`,`RSI_OverboughtExtreme`,`RSI_Overbought`,`RSI_OversoldExtreme`,`RSI_Oversold`,`Swing_Lookback`,`DP_Pattern_Bars`,`DP_Tolerance_ATR`,`StopLoss_Pips`,`TakeProfit_Pips`（全3銘柄。EURUSDはSL×TP局所2軸） | `UseTrailingStop`,`Trail_Start_Pips`,`Trail_Stop_Pips`,`UseBreakeven`,`BE_Trigger_Pips`,`UseVolatilityFilter`,`ATR_Min_Pips`,`UseATRStopLoss`,`ATR_SL_Multiplier`,`ATR_RR_Ratio`,`UseADXFilter`,`ADX_Period`,`ADX_Threshold`,`UseRangeFilter`,`Range_Slope_Lookback`,`Range_Slope_Max_ATR`,`UseTimeFilter`,`FilterStartHour`,`FilterEndHour`,`UseBreakevenATR`,`BE_Trigger_ATR`,`MaxHoldBars`,`ExitBeforeWeekend`,`WeekendExitHour`,`WeekendOnlyProfit`,`CooldownLosses`,`CooldownBars`,`UseATRPctFilter`,`ATRPct_Lookback`,`ATRPct_Max`,`UseStructureTP`,`StructureLookback`,`StructureMinRR`; `UseDoublePattern`は本番値を維持 | `LotSize`,`UseRiskSizing`,`RiskPercent`,`MagicNumber`,`ResultFileName`,`EquityLogFile`,`MA_Method` |
| SCA_EA / USDJPY, GBPJPY, GOLD | Boost/MinDrift、range mode/shift、wick/opposite-touch、stop orders、SL方式、時間窓/MinRangeの一部（R1–R3） | `RangeStartHour`,`RangeEndHour`,`TradeEndHour`,`ForceCloseHour`,`MinRange_ATRd`,`MaxRange_ATRd`,`Break_Buffer_ATRd`,`RR_Ratio`; `UseD1TrendFilter+D1Trend_MA`（対象別）、USDJPYはBuffer×MinRange局所2軸 | `SL_Mode`,`SL_ATRd_Mult`,`OneShotPerDir`,`UseFailedBreakExit`,`FB_MaxBars`,`UsePartialTP`,`Partial_R`,`Runner_RR`,`UseSwingTrail`,`Swing_Bars`,`UseRetestEntry`,`SkipFriday`,`UseStopOrders`,`UseReversalBoost`,`Boost_Mult`,`Boost_MinDrift_ATRd`,`RangeShiftLow_Pips`,`RangeShiftHigh_Pips`,`RangeMode`,`BreakOnWick`,`UseTiltGate`,`Buf_DecayPerHour`,`RequireOppTouch`,`UseMLFilter`,`ML_Threshold`; 本番ON値（GBPJPY Boost/GOLD Friday等）は維持 | `MaxSpreadPoints`,`LotSize`,`MagicNumber`,`UseRiskSizing`,`RiskPercent`,`ResultFileName`,`EquityLogFile`,`TradeLogFile` |
| Carry / AUDJPY | `TrendMA_Period`,`UseHysteresis`,`ATR_Period`,`Hyst_ATR_Mult`,`ExitMA_Period`,`ReentryCooldown`（R1–R3） | `TrendMA_Method`,`RequirePositiveSwap`,`ExitMA_Period`,`ReentryCooldown`の未探索端 | 機能OFF軸なし（本番ヒステリシスON） | `SignalTimeframe`,`LotSize`,`MagicNumber`,`UseRiskSizing`,`RefDeposit`,`ResultFileName`,`EquityLogFile` |
| PairTrade / EURUSD+GBPUSD | `Lookback`,`Entry_Z`,`Exit_Z`,`Stop_Z`（R1–R3） | 同4軸の未探索端・細刻み（結論再確認） | なし | `SecondSymbol`,`LotSize`,`MagicNumber`,`UseRiskSizing`,`RefDeposit`,`ResultFileName`,`EquityLogFile` |
| BfxRev_EA / BTCUSD | `DropPct`,`LookbackDays`,`HoldDays`,`DisasterSL_Pct`（btc_backlog4/R1–R3） | 前3軸の未探索端 | `DisasterSL_Pct`（災害用、歴史上ほぼ不発火） | `BfxFile`,`UseWebRequest`,`ApiUrl`,`UpdateCsvCache`,`CacheFile`,`LotSize`,`MagicNumber`,`MaxCryptoConcurrent`,`ResultFileName`,`EquityLogFile` |
| FundingRev_EA / BTCUSD | 閾値、Hold、ExitMode、MaxHold、災害SL（btc_backlog4/R1–R3） | `Threshold_Pct8h`,`MaxHoldDays`の未探索端 | `HoldDays`（ExitMode=2では通常無効）、`DisasterSL_Pct` | `FundingFile`,`UseWebRequest`,`ApiUrl`,`UpdateCsvCache`,`CacheFile`,`LotSize`,`MagicNumber`,`ResultFileName`,`EquityLogFile` |
| ETH_EA / ETHUSD | `TrendMA_Period`,`ExitMA_Period`,`ReentryCooldown`,`DisasterSL_Pct`（R2/R3） | `TrendMA_Period`,`ExitMA_Period`,`ReentryCooldown`,`MA_Method`、TrendMA×ExitMA局所2軸 | `DisasterSL_Pct`（災害用） | `SignalTimeframe`,`LotSize`,`MagicNumber`,`MaxCryptoConcurrent`,`EnableOpsLog`,`ResultFileName`,`EquityLogFile` |

注: `input group`宣言も全て確認したが、値を持たないUI見出しなので表では各配下のinput名に展開した。上表に8 EAの値を持つ全inputを一度以上列挙している。

## フェーズ2: 実行件数

| スリーブ | 件数 | パラメータ別 |
|---|---:|---|
| PB_USDJPY | 37 | `TrendMA_Period` 4, `FastEMA_Period` 5, `SlowEMA_Period` 5, `ADX_Period` 4, `ADX_Threshold` 4, `ATR_Period` 4, `ATR_SL_Mult` 4, `RR_Ratio` 4, `MA_Slope_Lookback` 3 |
| PB_GBPJPY | 46 | `TrendMA_Period` 4, `FastEMA_Period` 5, `SlowEMA_Period` 5, `ADX_Period` 4, `ADX_Threshold` 4, `ATR_Period` 4, `ATR_SL_Mult` 4, `RR_Ratio` 4, `ADX_Threshold_x_ADX_Period` 12 |
| PB_AUDJPY | 37 | `TrendMA_Period` 4, `FastEMA_Period` 5, `SlowEMA_Period` 5, `ADX_Period` 4, `ADX_Threshold` 4, `ATR_Period` 4, `ATR_SL_Mult` 4, `RR_Ratio` 4, `MA_Slope_Lookback` 3 |
| RSI_EURUSD | 57 | `MA_Period` 4, `BB_Period` 5, `BB_Deviation` 5, `RSI_Period` 5, `RSI_levels` 4, `StopLoss_Pips` 5, `TakeProfit_Pips` 5, `Swing_Lookback` 5, `DP_Pattern_Bars` 5, `DP_Tolerance_ATR` 5, `StopLoss_x_TakeProfit` 9 |
| RSI_USDJPY | 48 | `MA_Period` 4, `BB_Period` 5, `BB_Deviation` 5, `RSI_Period` 5, `RSI_levels` 4, `StopLoss_Pips` 5, `TakeProfit_Pips` 5, `Swing_Lookback` 5, `DP_Pattern_Bars` 5, `DP_Tolerance_ATR` 5 |
| RSI_GBPUSD | 48 | `MA_Period` 4, `BB_Period` 5, `BB_Deviation` 5, `RSI_Period` 5, `RSI_levels` 4, `StopLoss_Pips` 5, `TakeProfit_Pips` 5, `Swing_Lookback` 5, `DP_Pattern_Bars` 5, `DP_Tolerance_ATR` 5 |
| SCA_USDJPY | 47 | `RangeStartHour` 3, `RangeEndHour` 4, `TradeEndHour` 5, `ForceCloseHour` 4, `MinRange_ATRd` 5, `MaxRange_ATRd` 4, `Break_Buffer_ATRd` 4, `RR_Ratio` 5, `D1Trend_MA` 4, `Buffer_x_MinRange` 9 |
| SCA_GBPJPY | 38 | `RangeStartHour` 3, `RangeEndHour` 4, `TradeEndHour` 5, `ForceCloseHour` 4, `MinRange_ATRd` 5, `MaxRange_ATRd` 4, `Break_Buffer_ATRd` 4, `RR_Ratio` 5, `D1Trend_MA` 4 |
| SCA_GOLD | 38 | `ForceCloseHour` 4, `MinRange_ATRd` 5, `MaxRange_ATRd` 4, `Break_Buffer_ATRd` 4, `RR_Ratio` 5, `D1Trend_MA` 4, `RangeStartHour` 3, `RangeEndHour` 4, `TradeEndHour` 5 |
| CARRY_AUDJPY | 12 | `TrendMA_Method` 3, `RequirePositiveSwap` 1, `ExitMA_Period` 4, `ReentryCooldown` 4 |
| PAIR_EURGBP | 23 | `Lookback` 7, `Entry_Z` 5, `Exit_Z` 5, `Stop_Z` 6 |
| BFX_BTC | 20 | `DropPct` 6, `LookbackDays` 7, `HoldDays` 7 |
| FUNDING_BTC | 14 | `Threshold_Pct8h` 7, `MaxHoldDays` 7 |
| ETH_ETHUSD | 32 | `TrendMA_Period` 7, `ExitMA_Period` 7, `ReentryCooldown` 6, `MA_Method` 3, `TrendMA_x_ExitMA` 9 |
| PB_GOLD | 37 | `ADX_Period` 4, `ADX_Threshold` 4, `ATR_Period` 4, `ATR_SL_Mult` 4, `RR_Ratio` 4, `MA_Slope_Lookback` 3, `TrendMA_Period` 4, `FastEMA_Period` 5, `SlowEMA_Period` 5 |

## 厳格改善候補

数値は `純利益 / PF / 最大相対DD`。粗探索と局所2軸で同じ最良点が再現されたため、重複行を除き4候補を示す。

| スリーブ / 変更 | IS 現行 | IS 候補 | OOS 現行 | OOS 候補 |
|---|---:|---:|---:|---:|
| PB_GBPJPY `{'ADX_Threshold': 30.0, 'ADX_Period': 10}` | 33,133 / 3.1179 / 5.93% | 34,242 / 3.3412 / 4.94% | 20,763 / 1.6392 / 14.68% | 22,692 / 2.1649 / 11.32% |
| RSI_EURUSD `{'StopLoss_Pips': 25, 'TakeProfit_Pips': 105}` | 8,253 / 1.0869 / 9.76% | 8,400 / 1.1195 / 9.65% | -1,867 / 0.9764 / 13.10% | 2,582 / 1.0431 / 7.79% |
| SCA_USDJPY `{'Break_Buffer_ATRd': 0.1, 'MinRange_ATRd': 0.3}` | 16,913 / 1.1410 / 11.06% | 18,563 / 1.2162 / 7.71% | -4,875 / 0.9324 / 10.26% | 110 / 1.0024 / 6.44% |
| ETH_ETHUSD `{'TrendMA_Period': 150, 'ExitMA_Period': 40}` | 4,128 / 1.4919 / 3.84% | 4,419 / 1.5065 / 3.14% | 3,410 / 4.6471 / 0.67% | 3,664 / 5.3775 / 0.57% |

SCA USDJPY以外の3候補は利益改善に加えてPF/DDにも余裕がある。RSI EURUSDは現行OOS赤字を黒字化、ETHは両期間で改善。PB GBPJPYのADX=30は最も明瞭。

## トレードオフ候補

機械判定は6指標中4つ以上改善かつ両期間生存。局所2軸の重複も原票どおり掲載する。交換内容欄は、現行より悪化した指標を示す。

| スリーブ | 変更 | IS 候補 | OOS 候補 | 交換内容（悪化指標） |
|---|---|---:|---:|---|
| PB_USDJPY | `{'ADX_Period': 20}` | 33,088 / 1.5695 / 7.59% | 3,548 / 1.1669 / 10.75% | IS利益, ISPF |
| PB_USDJPY | `{'ADX_Threshold': 27.5}` | 41,850 / 1.6446 / 7.47% | 3,332 / 1.1551 / 10.95% | IS利益, ISPF |
| PB_USDJPY | `{'MA_Slope_Lookback': 10}` | 23,484 / 3.2239 / 3.44% | 293 / 1.1048 / 2.71% | IS利益 |
| PB_GBPJPY | `{'FastEMA_Period': 30}` | 34,704 / 3.1417 / 5.04% | 15,998 / 1.5359 / 12.50% | OOS利益, OOSPF |
| PB_GBPJPY | `{'SlowEMA_Period': 35}` | 35,946 / 3.8015 / 4.69% | 20,684 / 1.8218 / 14.16% | OOS利益 |
| PB_GBPJPY | `{'SlowEMA_Period': 40}` | 34,507 / 3.4181 / 5.93% | 20,655 / 1.8197 / 14.16% | OOS利益 |
| PB_AUDJPY | `{'ATR_SL_Mult': 3.0}` | 2,880 / 1.2072 / 3.88% | 187 / 1.0110 / 7.32% | ISPF, ISDD |
| PB_AUDJPY | `{'RR_Ratio': 3.0}` | 4,077 / 1.3639 / 2.60% | 793 / 1.0481 / 7.35% | ISDD |
| PB_AUDJPY | `{'RR_Ratio': 5.0}` | 6,157 / 1.7406 / 2.54% | 5,619 / 1.4029 / 8.21% | ISDD |
| PB_AUDJPY | `{'MA_Slope_Lookback': 10}` | 318 / 1.3067 / 1.02% | 499 / 2.1089 / 0.45% | IS利益 |
| RSI_EURUSD | `{'StopLoss_Pips': 40}` | 5,807 / 1.0636 / 9.16% | 2,842 / 1.0383 / 10.74% | IS利益, ISPF |
| RSI_EURUSD | `{'StopLoss_Pips': 60}` | 7,871 / 1.0789 / 9.01% | 2,921 / 1.0351 / 9.75% | IS利益, ISPF |
| RSI_EURUSD | `{'TakeProfit_Pips': 75}` | 1,054 / 1.0118 / 7.38% | 4,404 / 1.0611 / 7.37% | IS利益, ISPF |
| RSI_USDJPY | `{'MA_Period': 100}` | 2,516 / 1.0980 / 6.61% | 4,126 / 1.1469 / 3.48% | OOS利益, OOSPF |
| RSI_USDJPY | `{'BB_Deviation': 2.75}` | 1,397 / 1.0497 / 9.22% | 7,169 / 1.3071 / 5.40% | OOS利益 |
| RSI_USDJPY | `{'BB_Deviation': 3.0}` | 1,334 / 1.0514 / 7.57% | 6,479 / 1.2965 / 5.22% | OOS利益 |
| RSI_USDJPY | `{'StopLoss_Pips': 25}` | 4,048 / 1.2035 / 5.77% | 2,785 / 1.1285 / 5.96% | OOS利益, OOSPF |
| RSI_USDJPY | `{'StopLoss_Pips': 40}` | 491 / 1.0184 / 8.51% | 7,618 / 1.3074 / 6.68% | OOS利益, OOSDD |
| RSI_USDJPY | `{'TakeProfit_Pips': 50}` | 5,127 / 1.2340 / 5.32% | 621 / 1.0258 / 4.32% | OOS利益, OOSPF |
| RSI_USDJPY | `{'DP_Pattern_Bars': 40}` | 458 / 1.0158 / 10.28% | 7,741 / 1.2768 / 6.12% | OOS利益, OOSPF |
| RSI_USDJPY | `{'DP_Tolerance_ATR': 0.75}` | 2,519 / 1.0805 / 10.01% | 7,146 / 1.2408 / 5.74% | OOS利益, OOSPF |
| RSI_USDJPY | `{'DP_Tolerance_ATR': 1.5}` | 7,915 / 1.2278 / 5.96% | 7,925 / 1.2555 / 4.57% | OOSPF |
| RSI_USDJPY | `{'DP_Tolerance_ATR': 2.0}` | 8,229 / 1.2180 / 6.46% | 7,766 / 1.2360 / 4.17% | OOSPF |
| SCA_USDJPY | `{'MinRange_ATRd': 0.5}` | 11,343 / 1.2053 / 4.64% | 943 / 1.0306 / 5.25% | IS利益 |
| SCA_USDJPY | `{'Break_Buffer_ATRd': 0.075}` | 14,173 / 1.1379 / 10.96% | 2,471 / 1.0468 / 6.95% | IS利益, ISPF |
| SCA_GBPJPY | `{'RangeEndHour': 10}` | 87,562 / 1.3071 / 15.32% | 41,924 / 1.1367 / 17.96% | OOS利益, OOSPF |
| CARRY_AUDJPY | `{'ReentryCooldown': 10}` | 105,817 / 3.5057 / 28.54% | 37,325 / 2.4953 / 20.94% | IS利益, ISPF |
| PAIR_EURGBP | `{'Stop_Z': 6.0}` | 11,399 / 1.1628 / 8.37% | 9,506 / 1.6821 / 3.60% | OOS利益 |
| PAIR_EURGBP | `{'Stop_Z': 7.0}` | 11,399 / 1.1628 / 8.37% | 9,506 / 1.6821 / 3.60% | OOS利益 |
| BFX_BTC | `{'DropPct': 15}` | 5,845 / 1.7963 / 6.49% | 27,826 / 2.5899 / 11.87% | IS利益, ISPF |
| BFX_BTC | `{'LookbackDays': 10}` | 55,156 / 4.3131 / 7.52% | 19,376 / 1.4478 / 13.05% | ISPF |
| FUNDING_BTC | `{'Threshold_Pct8h': -0.003}` | 57,087 / 2.6583 / 9.16% | 3,081 / 2.0523 / 1.06% | OOS利益, OOSPF |
| FUNDING_BTC | `{'Threshold_Pct8h': -0.005}` | 27,906 / 2.5785 / 5.87% | 3,279 / 2.2011 / 1.06% | IS利益 |
| FUNDING_BTC | `{'Threshold_Pct8h': -0.006}` | 23,405 / 2.3239 / 5.87% | 3,168 / 2.1604 / 1.06% | IS利益 |
| FUNDING_BTC | `{'Threshold_Pct8h': -0.008}` | 11,858 / 2.1808 / 4.23% | 3,503 / 2.3442 / 1.06% | IS利益 |
| FUNDING_BTC | `{'Threshold_Pct8h': -0.01}` | 10,704 / 3.3194 / 2.67% | 3,751 / 2.4394 / 1.06% | IS利益 |
| ETH_ETHUSD | `{'TrendMA_Period': 175}` | 4,025 / 1.4491 / 3.30% | 3,576 / 4.9955 / 0.63% | IS利益, ISPF |
| ETH_ETHUSD | `{'ExitMA_Period': 30}` | 3,193 / 1.3165 / 2.75% | 4,008 / 6.1057 / 0.35% | IS利益, ISPF |
| PB_GBPJPY | `{'ADX_Threshold': 28.0, 'ADX_Period': 7}` | 43,149 / 4.6129 / 2.91% | 14,372 / 1.5239 / 14.24% | OOS利益, OOSPF |
| PB_GBPJPY | `{'ADX_Threshold': 30.0, 'ADX_Period': 7}` | 33,249 / 3.1254 / 5.92% | 18,750 / 1.6783 / 14.24% | OOS利益 |
| PB_GBPJPY | `{'ADX_Threshold': 32.0, 'ADX_Period': 10}` | 26,449 / 3.3396 / 4.32% | 14,061 / 1.8624 / 8.37% | IS利益, OOS利益 |
| RSI_EURUSD | `{'StopLoss_Pips': 20, 'TakeProfit_Pips': 105}` | 2,851 / 1.0461 / 9.24% | 3,634 / 1.0709 / 5.63% | IS利益, ISPF |
| RSI_EURUSD | `{'StopLoss_Pips': 25, 'TakeProfit_Pips': 75}` | 3,534 / 1.0520 / 7.90% | 1,836 / 1.0327 / 8.26% | IS利益, ISPF |
| RSI_EURUSD | `{'StopLoss_Pips': 30, 'TakeProfit_Pips': 75}` | 2,410 / 1.0317 / 7.73% | 68 / 1.0011 / 8.69% | IS利益, ISPF |
| SCA_USDJPY | `{'Break_Buffer_ATRd': 0.075, 'MinRange_ATRd': 0.3}` | 14,173 / 1.1379 / 10.96% | 2,471 / 1.0468 / 6.95% | IS利益, ISPF |
| SCA_USDJPY | `{'Break_Buffer_ATRd': 0.075, 'MinRange_ATRd': 0.5}` | 9,974 / 1.2036 / 4.58% | 6,537 / 1.3028 / 2.25% | IS利益 |
| SCA_USDJPY | `{'Break_Buffer_ATRd': 0.1, 'MinRange_ATRd': 0.4}` | 4,386 / 1.0681 / 7.84% | 2,962 / 1.0964 / 4.38% | IS利益, ISPF |
| SCA_USDJPY | `{'Break_Buffer_ATRd': 0.1, 'MinRange_ATRd': 0.5}` | 13,262 / 1.3368 / 4.51% | 6,696 / 1.3611 / 2.73% | IS利益 |
| SCA_USDJPY | `{'Break_Buffer_ATRd': 0.125, 'MinRange_ATRd': 0.5}` | 1,928 / 1.0504 / 6.31% | 4,529 / 1.2654 / 2.41% | IS利益, ISPF |
| ETH_ETHUSD | `{'TrendMA_Period': 150, 'ExitMA_Period': 30}` | 2,610 / 1.2310 / 3.15% | 4,094 / 5.4548 / 0.42% | IS利益, ISPF |
| ETH_ETHUSD | `{'TrendMA_Period': 175, 'ExitMA_Period': 30}` | 2,216 / 1.1921 / 3.23% | 4,004 / 5.0650 / 0.48% | IS利益, ISPF |
| ETH_ETHUSD | `{'TrendMA_Period': 175, 'ExitMA_Period': 40}` | 4,025 / 1.4491 / 3.30% | 3,576 / 4.9955 / 0.63% | IS利益, ISPF |

## 現行が最良と確認できた範囲

「厳格改善なし」を今後の重複回避基準とする。トレードオフ候補は上表に残している。

| スリーブ | 厳格改善が無かった今回の探索軸 |
|---|---|
| PB USDJPY | TrendMA, EMA fast/slow, ADX period/threshold, ATR period/SL, RR, slope lookback |
| PB GBPJPY | TrendMA, EMA fast/slow, ADX period（閾値30との組合せ以外）, ATR period/SL, RR |
| PB AUDJPY | TrendMA, EMA fast/slow, ADX, ATR period/SL, RR, slope lookback（生存化トレードオフはあり） |
| PB GOLD | OOS不能のため「現行最良」と断定不可。IS結果のみ原票参照 |
| RSI EURUSD | MA, BB, RSI period/levels, DP各軸, TP単独（SL25以外） |
| RSI USDJPY | MA, BB, RSI, 固定SL/TP, DP各軸（生存化トレードオフはあり） |
| RSI GBPUSD | MA, BB, RSI, 固定SL/TP, DP各軸 |
| SCA USDJPY | 全時間軸、range上下限、RR、D1 trend（buffer 0.10以外） |
| SCA GBPJPY | 全探索軸（RangeEnd=10はトレードオフ） |
| SCA GOLD | OOS不能のため断定不可。IS結果のみ原票参照 |
| Carry AUDJPY | MA method, positive-swap解除, ExitMA, cooldown（cd10はOOS改善トレードオフ） |
| PairTrade | Lookback, Entry/Exit Z, Stop Z（6/7は小さなトレードオフ） |
| BfxRev | DropPct, LookbackDays, HoldDays（Lookback10等はトレードオフ） |
| FundingRev | Threshold, MaxHold（閾値変更は複数トレードオフ） |
| ETH | ExitMA, cooldown, MA method（TrendMA150以外） |

## 問題点・実装上の注意

- GOLD OOSは全75件でsummaryを生成できず検証不能。既知のXAUJPY換算履歴不足と整合する。ISだけで本番変更を決めない。
- PBの`MA_Slope_Lookback`は`UseTrendStrength=false`のスリーブでは無効で、結果が同値になる。無効軸を原票に明示した。
- SCAの`D1Trend_MA`は単独では無効なので、今回だけ`UseD1TrendFilter=true`とセットで対象別に検証した（厳格改善なし）。
- Fundingの`HoldDays`は本番`ExitMode=2`では通常の退出に使われず、MaxHoldDaysを探索した。
- enum MA methodは0=SMA（現行）、1=EMA、2=SMMA、3=LWMAとして渡した。改善なし。
- Boost倍率は今回再探索していない。過去の0.01 lot丸めで4.5=4.0になる問題を踏まえ、既探索結論を維持した。
- 厳格改善4点はすべて現行本番一式上で再測定し、局所2軸でも同一点を再現した。複数変更を同時採用した組合せ検証はしていないため、スリーブ内で複数案を混ぜない。
- `results.csv`の`status=UNVERIFIABLE`はGOLDだけ。認証ファイル、本番config、EA、MIX_EA/MIX_EA_OANDAは未変更。
