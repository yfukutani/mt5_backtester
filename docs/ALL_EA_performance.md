# 全EA 性能まとめ（2026-09-15）

このリポジトリで開発・検証した**すべてのEA**の性能を1枚に集約する。
枠別の詳細は [portfolio.md](portfolio.md)、運用統合EAは [portfolio_ea.md](portfolio_ea.md)、
プロジェクト全体の経緯は [project_status.md](project_status.md)。

`CLAUDE.md`「報告に必ず含める数値」に従い、**損益・想定月利・最大ドロップダウン**を必ず併記する。

---

## 0. EAの分類

| 分類 | EA | 役割 |
|---|---|---|
| **本番ポートフォリオ** | `MIX_EA.mq5`（XM版）／`MIX_EA_OANDA.mq5`（OANDA版） | 全枠を1チャートで稼働。**実運用はこれ** |
| 旧ポートフォリオ | `PortfolioEA.mq5`／`PortfolioEA_OANDA.mq5` | MIX_EAの前身（10枠統合） |
| **検証専用** | `MIX_EA_SIMVERIFY.mq5`／`MIX_EA_OANDA_SIMVERIFY.mq5` | 実験枠を足せる版。**本番利用禁止** |
| **検証専用（X2）** | `MIX_EA_X2HR.mq5` | 資金2倍化の検証用。期限意識サイジング＋RSI横展開4枠 |
| **個別戦略EA** | `RSI_Reversal` `PullbackTrend` `PairTrade` `Carry` `VolBreakout` `SCA_EA` `ETH_EA` `FundingRev_EA` `BfxRev_EA` | 各枠の開発・単体検証用 |
| **棄却済み** | `KeltnerBreakout` `DMI_Cross` `FalseBreakout` `GoldSeason` `LondonGapFade` `MomentumRanking` `Seasonal` `USDIndexTrend` `RiskOffGold` `NvtCross_EA` `RSI2Reversal` `RSIDivergence` `DAY_RELAY` `NEW_PLAN_EA` `SCA_BOX/DL/ML_EA` | §5を参照 |
| 補助 | `DataExport.mq5` | 検証用データ書き出し |

---

## 1. 本番ポートフォリオ（MIX_EA・XM版15枠）

### 前提

| 項目 | 値 |
|---|---|
| 入金 | **500,000円**（**実口座の残高ではない**） |
| モデル | every_tick |
| ロット | ほぼ全枠0.01固定。資金連動は3枠のみ（`RefCap=78,000` の固定基準） |
| 想定月利 | **単利**（固定ロットなので複利が効かない） |

### 窓別の成績

| 窓 | 期間 | 月数 | 取引 | **純益** | **単利 月利** | 1取引シャープ |
|---|---|---:|---:|---:|---:|---:|
| **IS** | 2021-06〜2026-06 | 60 | 2,053 | **+814,947円** | **2.72%** | 0.1068 |
| **OOS** | 2016-11〜2021-06 | 55 | 1,842 | **+205,187円** | **0.75%** | 0.0657 |
| 　うち**弱局面** | 2016-11〜2019-12 | 38 | 1,188 | +58,541円 | **0.31%** | 0.0349 |
| 　うち**金大相場** | 2020-01〜2021-06 | 17 | 654 | +146,646円 | 1.73% | 0.1060 |

### 最大ドロップダウン（MT5テスターの最大相対DD%・**確定損益ベース**）

| ブック | FULL（115ヶ月） | IS | OOS |
|---|---|---|---|
| FX側10枠 | +379,084円 / PF1.30 / **DD 5.59%** | +257,817円 / PF1.35 / DD 7.31% | +119,537円 / PF1.22 / DD 5.25% |
| GOLD側5枠 | +729,253円 / PF1.96 / **DD 4.60%** | +610,318円 / PF2.17 / DD 5.46% | +118,935円 / PF1.50 / DD 2.99% |

> [!note] **合算ブックのDDではない。**
> FX側とGOLD側は**別々のバックテスト実行**。合算DDは両者の同時性に依存し、
> 単純な足し算にも最大値にもならない。また**確定損益ベース**で含み損を含まない。

### 本番デプロイ（25万円・リスクパリティ・11枠時点）

| 指標 | 値 |
|---|---|
| 純利益 | +383,409円 |
| 最大DD | 11.62% |
| 資本利回り | 10年 +153%（**年率約9.8%**） |

### 増レバ設計の到達点（50万円・2026.07.03）

| 構成 | 月利 | 最大DD |
|---|---:|---:|
| 推奨 | **4.51%** | 28.19% |
| 上限 | 4.80% | 29.40% |

> **月利6%（本番運用目標）は、必要リターン/DD ≈ 24 に対し実測14.5で、
> 現行フロンティアでは到達不能と確定**（[leverage_design.md](leverage_design.md)）。

---

## 2. 枠別の性能（入金50万円・倍率1倍）

| 枠 | 戦略EA | 銘柄 | 足 | IS（60ヶ月） | OOS（55ヶ月） | **うち弱局面（38ヶ月）** | うち金大相場（17ヶ月） |
|---|---|---|---|---:|---:|---:|---:|
| **PB GOLD** | PullbackTrend | GOLD | H4 | **+200,470** | +24,063 | +7,314 | +16,749 |
| **SCA GOLD1** | SCA_EA | GOLD | M15 | **+179,120** | +52,540 | **−1,716** | +54,256 |
| **SCA GOLD2** | SCA_EA | GOLD | M15 | +123,237 | +20,733 | +525 | +20,208 |
| **SCA GBPJPY** | SCA_EA | GBPJPY | M15 | +73,773 | +42,219 | **+23,412** | +18,807 |
| BfxRev | BfxRev_EA | BTCUSD | D1 | +60,848 | +11,909 | −4,229 | +16,138 |
| BTC funding | FundingRev_EA | BTCUSD | D1 | +30,201 | +1,401 | −876 | +2,277 |
| Carry AUDJPY | Carry | AUDJPY | D1 | +25,882 | −5,324 | −572 | −4,752 |
| PB GBPJPY | PullbackTrend | GBPJPY | H4 | +22,291 | +22,738 | +5,026 | +17,712 |
| PB USDJPY | PullbackTrend | USDJPY | H4 | +22,267 | −1,812 | −6,005 | +4,193 |
| SCA USDJPY | SCA_EA | USDJPY | M15 | +18,563 | −2,224 | −3,272 | +1,048 |
| ETH TrendHold | ETH_EA | ETHUSD | D1 | +16,442 | +8,289 | +868 | +7,421 |
| **RSI GBPUSD** | RSI_Reversal | GBPUSD | H4 | +13,286 | +16,984 | **+16,136** | +848 |
| PairTrade | PairTrade | EURUSD/GBPUSD | H1 | +13,097 | +1,996 | +4,376 | −2,380 |
| RSI EURUSD | RSI_Reversal | EURUSD | H1 | +8,030 | +3,805 | +8,638 | −4,833 |
| **RSI USDJPY** | RSI_Reversal | USDJPY | H4 | +7,440 | +7,870 | **+8,916** | −1,046 |
| **合計** | — | — | — | **+814,947** | **+205,187** | **+58,541** | **+146,646** |

### 読み取れること

1. **IS窓の上位3枠（PB GOLD・SCA GOLD1/2）でIS純益の62%。GOLD依存が強い。**
2. **弱局面では順位が入れ替わる。** SCA GBPJPY（+23,412）とRSI GBPUSD（+16,136）が上位で、
   IS窓の主力だったSCA GOLD1は**−1,716の赤字**。
3. **弱局面で赤字の枠が6つ**。ただし**他期間では黒字**であり、
   弱局面だけを見て外すのは過学習（V090で確認済み）。
4. RSI枠（USDJPY・EURUSD・GBPUSD）は**IS窓では最下位グループだが弱局面で稼ぐ**。
   → ブックが不毛な月に稼ぐ唯一の型（V099）。

### 収益源の分散

トレンド（PB）／レンジ（RSI）／中立（Pair）／キャリー（Carry）／
セッションORBブレイク（SCA）／暗号トレンド（ETH）／暗号ファンディング（BTC funding・BfxRev）
＝ **7種の異質なメカニズム**。原資産は USDJPY / GBPJPY / EURUSD / GBPUSD / AUDJPY / GOLD / ETHUSD / BTCUSD の8種。

---

## 3. OANDA版（MIX_EA_OANDA・FX 9枠）

OANDA証券はFX口座とCFD口座が分かれるため、**GOLD系・暗号系を持てない**。

| 検証 | 結論 |
|---|---|
| 倍率余力（2026-09-08） | `GlobalLotMult=1` のままで入金50万に対する円建てDDを9.7%しか使っていなかった（XM側は倍率x4で25.8%）。**OOS月利 +1.22ポイント** |
| 複利化（2026-09-09） | **月利5%目標は到達不能**（OOS最良 2.71%/月・DD57%）。推奨は `RefCap=250,000`／倍率3 で **OOS 1.73%/月・最大DD 27.0%・元本割れなし** |

> **未反映**（本番デプロイへの適用はユーザー判断待ち）。
> 詳細: [oanda_fx_lot_headroom_20260908.md](oanda_fx_lot_headroom_20260908.md)・
> [oanda_fx_compounding_20260909.md](oanda_fx_compounding_20260909.md)

---

## 4. X2_HIGH_RISK（別目的EA・`MIX_EA_X2HR.mq5`）

**本番ブックとは別目的**——DD制約を外し「破綻するまでに資金が2倍になる確率」を最大化する。
詳細は [X2_HIGH_RISK_performance.md](X2_HIGH_RISK_performance.md)。

| 項目 | 値 |
|---|---|
| 資金 | **100,000円** |
| 目標 | **2倍・固定** |
| 破綻ライン | 資金の10% |
| 方針A | 3〜6ヶ月で到達率65%以上 |
| 方針B | 12ヶ月までで到達率90%以上（破綻は限りなく低く） |

### 段階3（MT5バックテスト・弱局面の非重複窓）

| 期限 | 方策 | 本数 | **到達** | 破綻 | **損益 中央** | **月利 中央** | 確定DD 中央 | **含み損込みDD 中央** | 最悪 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 6ヶ月 | 比例 k=4 | 6 | **33%** | 0% | **+12,943円** | 1.65% | 40.2% | **58.9%** | 74.4% |
| 6ヶ月 | HJB k=4 | 6 | 17% | 0% | −10,044円 | −2.80% | 71.7% | 76.0% | 80.2% |
| 12ヶ月 | 比例 k=2 | 3 | 33% | 0% | +20,414円 | 1.40% | 38.7% | 39.9% | 58.6% |
| 12ヶ月 | HJB k=2 | 3 | **67%** | 0% | **+100,032円** | 5.95% | 46.4% | 48.4% | 73.0% |

**IS窓（簡易再生・参考）**：6ヶ月 比例 85.5% / HJB 91.9%、12ヶ月 比例 94.3% / HJB 100.0%。

| 方針 | 実測 | 目標 | 不足 |
|---|---:|---:|---:|
| A | **33%** | 65% | **−32pt** |
| B | **33〜67%** | 90% | **−23pt** |

**どちらも未達。14軸を試して到達していない**
（[X2_HIGH_RISK_status_20260913.md](X2_HIGH_RISK_status_20260913.md) §4）。

---

## 5. 棄却したEA・戦略

詳細は [rejected_strategies.md](rejected_strategies.md)。

| EA / 戦略 | 対象 | 棄却理由 |
|---|---|---|
| `KeltnerBreakout` | USDJPY H4 | 既存枠に対する優位性なし |
| `DMI_Cross` | USDJPY H4 | 同上 |
| `FalseBreakout` | EURUSD/GBPUSD/USDJPY H4 | 偽ブレイク狙い。成立せず |
| `GoldSeason` | GOLD | GOLD別戦略7案の1つ。全滅 |
| `LondonGapFade` | — | 成立せず |
| `MomentumRanking` | マルチ市場 | マルチ市場トレンド。棄却 |
| `Seasonal` | — | 季節性。棄却 |
| `USDIndexTrend` | — | 棄却 |
| `RiskOffGold` | GOLD | 守りのオーバーレイ3形態の1つ。棄却 |
| `NvtCross_EA` | BTCUSD | 暗号横展開。棄却 |
| `RSI2Reversal` | — | RSI2逆張り。棄却 |
| `RSIDivergence` | USDJPY H4 | 全期間 −1,011 / PF0.98 / **IS −3,601**。運用ルール（IS/OOS両プラス）に抵触 |
| **USDCHF RSI** | USDCHF H4 | 全期間 **−20,635 / PF0.66** / 130取引。ドルストレートでも通貨を選ぶと判明 |
| **RSI14 クロスペア展開** | EURJPY等 | **全滅**（ドルストレート限定と判明） |
| **PullbackTrend 横展開** | SILVER / NASDAQ / 原油 / NZDUSD / USDCAD | CFD横展開・コモディティ通貨とも棄却 |
| **VolBreakout 他銘柄横展開** | — | 既存結論の再確認で棄却 |
| **SCA 第2セッション横展開** | USDJPY / GBPJPY | 棄却 |
| **PB GOLD 第2時間軸（H1）** | GOLD H1 | OOS不振で不採用 |
| **RSI横展開4枠**（X2検証） | GOLD / AUDUSD / NZDUSD / USDCAD | **4枠ともOOS赤字**。運用ルール不合格（V100・V101） |

---

## 6. 全体の要約

| 見方 | 数字 |
|---|---|
| **本番ブック（XM 15枠・入金50万円）** | IS 月利 **2.72%** / OOS 月利 **0.75%** / 最大DD 4.6〜7.3% |
| 　うち不利な時期（弱局面38ヶ月） | 月利 **0.31%**・**12ヶ月窓の26%がマイナス** |
| 　うち有利な時期（金大相場17ヶ月） | 月利 1.73% |
| **本番デプロイ（25万円・リスクパリティ）** | 10年 +153%（**年率約9.8%**）／最大DD 11.62% |
| **増レバ設計の到達点（50万円）** | 月利 **4.51%** ／ 最大DD 28.19% |
| **OANDA FX 9枠（推奨構成・未反映）** | OOS 月利 **1.73%** ／ 最大DD 27.0% |
| **X2_HIGH_RISK（資金10万円・2倍狙い）** | 到達 33〜67% ／ **含み損込みDD 58.9〜80.2%** |
| **本番運用目標（月利6%）との距離** | 増レバ後の実測 4.51% が最良。**6%は現行フロンティアでは到達不能と確定** |

### 全体を通じて分かっていること

1. **時期の偏りが大きい。** 同じOOS窓の中で、期間の31%が純益の71%を稼いでいる（月利で5.6倍差）。
   「平均して月0.75%」ではなく「**稼ぐ時期に集中し、稼がない時期が1年単位で続く**」形。
2. **GOLD依存。** IS純益の62%が上位3枠のGOLD系。ただし弱局面ではGOLD枠が振るわず、
   RSI枠とSCA GBPJPYが支える。**枠の分散は「時期の分散」として機能している。**
3. **新規枠の追加は収穫逓減の底。** 2026.06.29にブック確定。以後の横展開はほぼ全滅。
4. **月利6%は現行フロンティアでは到達不能。** 増レバでも4.51%@DD28%。
5. **資金2倍化（X2_HIGH_RISK）も未達。** 14軸を試して方針A −32pt / 方針B −23pt。

---

## 7. 数字の出どころと限界

| 節 | 出どころ |
|---|---|
| §1・§2 | `ml/x2hr/perf_summary.py`（V107）／`ml/fxmult1/results.csv`・`ml/goldcomp1/results.csv` |
| §1 デプロイ・増レバ | [portfolio.md](portfolio.md)・[portfolio_ea.md](portfolio_ea.md)・[leverage_design.md](leverage_design.md) |
| §3 OANDA | [oanda_fx_lot_headroom_20260908.md](oanda_fx_lot_headroom_20260908.md)・[oanda_fx_compounding_20260909.md](oanda_fx_compounding_20260909.md) |
| §4 X2 | `ml/x2hr/bt_deadline/`（MT5バックテスト18本）・[X2_HIGH_RISK_performance.md](X2_HIGH_RISK_performance.md) |
| §5 棄却 | [rejected_strategies.md](rejected_strategies.md)・[project_status.md](project_status.md) |

### 限界

- **最大DDはFX側・GOLD側の別々の実行の値**で、合算ブックのDDではない
- 枠別の損益は決済ログの `profit` 合計（スワップ・手数料はログの定義に従う）
- §1〜§3 は入金50万円・倍率1倍、§4 は資金10万円・倍率k。**直接比較できない**
- すべてXM端末・XM銘柄（OANDA版を除く）。**本番ブローカーが違えば結果も違う**
- **フォワードテストは限定的**（[forward_test_baseline.md](forward_test_baseline.md)・
  `docs/forward_reports/` を参照）。本書の数字はバックテストのもの
- `every_tick` 実効では Carry が約 −33%（[model_validation.md](model_validation.md)）
