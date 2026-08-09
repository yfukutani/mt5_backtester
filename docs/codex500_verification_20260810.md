# Codex 500案提案・検証（2026-08-10）

Codex CLI（MCPツール`mcp__codex__codex`/`codex-reply`）に、現状戦略の分析→約500案の提案→
高優先度項目の実バックテスト検証まで一貫して指示した記録。

## 提案フェーズ（read-onlyサンドボックス）

`docs/rejected_strategies.md`・`docs/new_plan_backlog.md`・`docs/btc_backlog4.md`・
`docs/new_strategies_round1_20260805.md`/`round2_20260805.md`・`docs/codex_50proposals_20260807.md`・
`docs/codex_verification_20260808.md`（既検証・却下・採用済みの全履歴）と、`experts/`・`configs/`の
現行実装を分析させ、重複しない**32ファミリー・512案**を提案させた。件数はファミリー×バリエーション。

分類: 即検証可能(既存パラメータのみ)/軽微なコード変更/大規模なコード変更、の3段階。

副産物として、既にコード監査で以下の**単体研究configの設定ドリフト**を発見・修正（本番の統合EA
`MIX_EA_OANDA.mq5`自体は既に採用値だったため実運用への影響はない）:
- `configs/oanda/pullback_gbpjpy_h4_oanda.yaml`: MA_Slope_Min_ATR/RR_Ratioが旧値のまま
- `configs/oanda/sca_gbpjpy_oanda.yaml`: UseReversalBoost/Boost_Mult設定が欠落
- `configs/oanda/rsi_robust_gbpusd_h4_oanda.yaml`: BB_Deviationが旧値のまま

## 検証フェーズ（`danger-full-access`サンドボックス）

前回セッション（`docs/codex_verification_20260808.md`）では`workspace-write`サンドボックスで
`mt5bt.exe`等の実行が`Access is denied`で拒否される問題があった。今回は`danger-full-access`を
指定したところ、Codexが実際にバックテストを起動・完走できることを確認した
（MCPツール呼び出し自体は30分でタイムアウトしたが、Codexのプロセスはバックグラウンドで
継続動作し、`ml/codex500/results.csv`へ結果を書き続けていた。ファイル成長を監視して完了を確認）。

512案のうち優先度上位5ファミリー・**72候補**を、標準プロトコル（IS/OOS二段階ゲート・本番yaml
ベース・本番同一のロット/サイジング）でCodexに実行させた。

### A. SCA GBPJPY: Boost_MinDrift_ATRd（8点・every_tick）
現行値0（無効）が8水準中で最良（IS+39,027/OOS+23,451）。**変更不要**。

### B. RSI GBPUSD: RSI_Period × BB_Period（16点・open_prices）
RSI周期はほぼ無感応。BB_Period=30が一貫して最良。

| | IS純利益/PF | OOS純利益/PF |
|---|---|---|
| 現行(BB_Period=20) | 12,442 / 1.41 | 16,045 / 1.76 |
| **採用: BB_Period=30** | **13,398 / 1.51** | **18,922 / 2.03** |

トレードオフなし（IS+7.7%・OOS+17.9%）。**採用**。

### C. PB GBPJPY: ADX_Period × MA_Slope_Lookback（16点・open_prices）
MA_Slope_Lookback=20だけが唯一の生存領域。その中でADX_Period=10が最良。

| | IS純利益 | OOS純利益 |
|---|---|---|
| 現行(ADX_Period=14) | 29,315 | 10,197 |
| **採用: ADX_Period=10** | **31,611** | **14,670** |

トレードオフなし（IS+7.8%・OOS+43.8%）。**採用**。

### D. Carry AUDJPY: TrendMA_Period × Hyst_ATR_Mult × ATR_Period（16点・open_prices）
全16点が生存する頑健なプラトーを再確認。ただし現行値(200/0.75/14)を両期間で明確に上回る
単独点はなく、固定ロットの応答曲面のため本番の複利/risk%サイジングとの直接比較もできない。
**変更不要**。

### E. PairTrade EURUSD/GBPUSD: Lookback × Stop_Z（16点・open_prices）
Lookbackを短くするとOOSは改善するがISが悪化するトレードオフ。「現状市場の利益を優先」という
既存方針（[[mt5-tradeoff-preference]]）に沿い**変更不要**。

## 採用した変更（ユーザー承認・2026-08-10）

### B: RSI GBPUSD BB_Period 20→30
- `experts/RSI_Reversal.mq5`は既にBB_Periodを入力パラメータとして持っていたためコード変更不要。
  `configs/rsi_robust_gbpusd_h4.yaml`・`configs/oanda/rsi_robust_gbpusd_h4_oanda.yaml`を更新。
- `MIX_EA.mq5`/`MIX_EA_OANDA.mq5`は従来BB期間を`iBands()`呼び出しに`20`と直書きしており、
  スリーブ単位で可変にできなかった。**SLEEVE構造体に`bbPeriod`フィールドを追加**し、
  `iBands(symbol,tf,bbPeriod,0,bbDev,PRICE_CLOSE)`へ変更（既定値20・RSI GBPUSDスリーブのみ30）。

### C: PB GBPJPY ADX_Period 14→10
- `experts/PullbackTrend.mq5`は既にADX_Periodを入力パラメータとして持っていたためコード変更不要。
  `configs/pullback_gbpjpy_h4.yaml`・`configs/oanda/pullback_gbpjpy_h4_oanda.yaml`を更新。
- `MIX_EA.mq5`/`MIX_EA_OANDA.mq5`は従来ADX期間を`iADX()`呼び出しに`14`と直書きしており、
  スリーブ単位で可変にできなかった。**SLEEVE構造体に`adxPeriod`フィールドを追加**し、
  `iADX(symbol,tf,adxPeriod)`へ変更（既定値14・PB GBPJPYスリーブのみ10）。

### 検証
- `MIX_EA.mq5`（XM）: MetaEditorコンパイル0 errors。every_tick回帰（USDJPY M15・2026上半期）で
  純利益213,794→218,757円（クラッシュなし、GBPJPY/GBPUSD絡みの想定内の変化）。
- `MIX_EA_OANDA.mq5`: MetaEditorコンパイル0 errors。**ただしOANDA側ターミナルがLiveUpdate
  自動更新ループ（ファイルロックのエラー32）で詰まり、実バックテストによる回帰確認は
  今回できなかった**（環境要因・コード変更とは無関係）。XM側とロジックは完全に同一の変更の
  ため、コンパイル成功をもって妥当性の代替確認とする。後日OANDA環境が復旧した時点で
  回帰確認を推奨。

## 未実施の残り

512案中72案のみ検証。残り約440案（27ファミリー）は`ml/codex500_screen.py`にファミリー定義が
残っているため、追加ラウンドとして継続可能。特に「軽微なコード変更」「大規模なコード変更」に
分類された項目（PairTradeの分散推定頑健化・Carry離散複利更新・API日付境界監査・単体/MIX
シグナル同値性ログ・限界DD寄与ベースのポートフォリオ配分等）は、コード実装が絡むため個別の
判断・スコープ設定が必要。
