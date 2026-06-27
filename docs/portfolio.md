# 最終ポートフォリオ構成（本番運用リファレンス）

**更新日:** 2026.06.27
**検証:** `mt5bt portfolio`（全dealの時系列合算）/ 全期間 2016-2026 / 各EA配分資金100,000

トレンド・レンジ・中立の3種・低相関6チャートで構成する分散ポートフォリオ。
各検証の詳細は [research_log.md](research_log.md) / [position_sizing.md](position_sizing.md) /
[rsi_robustness.md](rsi_robustness.md) / [pair_trade.md](pair_trade.md) を参照。

## 構成（6チャート）

| 役割 | EA | config | サイジング | Magic | 純利益 | 単独DD |
|---|---|---|---|---|---|---|
| 順張り | PullbackTrend USDJPY H4 | `pullback_usdjpy_h4.yaml` | risk2% | 20260622 | +42,406 | 23,152 |
| 順張り | PullbackTrend GBPJPY H4 | `pullback_gbpjpy_h4.yaml` | risk2% | 20260627 | +17,263 | 13,404 |
| 順張り | PullbackTrend AUDJPY H4 | `pullback_audjpy_h4.yaml` | 固定 | 20260628 | +44 | 8,826 |
| 逆張り | RSI_Reversal USDJPY H4 | `rsi_robust_usdjpy_h4.yaml` | 固定 | 20260610 | +8,492 | 17,436 |
| 逆張り | RSI_Reversal EURUSD H1 | `rsi_robust_eurusd_h1.yaml` | 固定 | 20260605 | +6,180 | 13,616 |
| 中立 | PairTrade EUR/GBP H1 | `pairtrade_eurusd_gbpusd.yaml` | 固定 | 20260629 | +12,340 | 12,284 |

> 注: `pullback_usdjpy_h4.yaml` は本番configが2021起点のIS構成。上表のUSDJPY純利益は
> 期間を揃えた全期間(2016-2026)版での値。

## 合算成績（全期間2016-2026, `mt5bt portfolio`実測）

| 指標 | 値 |
|---|---|
| 合計配分資金 | 600,000 |
| 純利益 | **+86,725** |
| 最大DD（額） | 34,557 |
| 最大DD（%） | **5.50%** |
| リターン/最大DD | **2.51** |
| 単独DDの単純和 | 88,718 |
| 分散効果（DD削減） | **-54,161（61%減）** |

> **分散効果が圧巻:** 単独DD合計88,718に対しポートフォリオDDは34,557（61%減）。
> トレンド・レンジ・中立が同時にDDしないため、リスクが大きく相殺される。
> 6本中4本は最小ロット（≈0.5%リスク）稼働で、DD5.5%とまだスケール余地が大きい保守的構成。

## 再現コマンド

```bash
mt5bt portfolio \
  configs/pullback_usdjpy_h4.yaml \
  configs/pullback_gbpjpy_h4.yaml \
  configs/pullback_audjpy_h4.yaml \
  configs/rsi_robust_usdjpy_h4.yaml \
  configs/rsi_robust_eurusd_h1.yaml \
  configs/pairtrade_eurusd_gbpusd.yaml
```

（USDJPY PBを全期間で揃える場合は from_date を 2016.06.21 にした版を使う）

## 設計原則（検証で確立した知見）

| 原則 | 根拠 |
|---|---|
| サイジングは「真のエッジ(PF>1)＋滑らかなカーブ」のEAのみ | PullbackTrend(順張り)は増益＋PF改善。RSI(逆張り)はDD爆発、PairTrade(中立)は破綻、AUDJPY(PF1.0)は負転落 |
| 逆張り・中立・エッジ無しは固定ロット | 複利レバレッジがDDを増幅 or ボラドラッグでマイナス化 |
| ロバスト化は環境フィルターで | PB=MA200傾き≥1.2（強トレンド時）、RSI=傾き≤0.2（レンジ時）。過学習を克服し全期間プラス |
| 分散は「異質な収益源」で | トレンド/レンジ/中立。同種(Keltner/DMI 相関0.58)は冗長。AUD/NZD(無相関だが負け期待値)は不採用 |
| 最適化は追わない | パラメータ最適化のスパイクは過剰最適化。OOS検証必須 |

## MT5での運用

各チャートに対応EAをアタッチ（MagicNumberが異なるため独立動作）。
- PullbackTrend: USDJPY/GBPJPY は `UseRiskSizing=true, RiskPercent=2.0`、AUDJPY は固定。
- RSI_Reversal: 両チャートとも `UseRangeFilter=true, Range_Slope_Max_ATR=0.2`、固定ロット。
- PairTrade: EURUSD（主）/GBPUSD（従）、固定ロット。
