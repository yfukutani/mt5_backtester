# 運用PC引き継ぎ手順書（2026-07-12版）— MIX_EA v1.3への更新

**対象:** フォワードテスト稼働中の運用PC（XM / OANDA FX / OANDA CFDの3端末）
**現状想定:** 2026-07-07開始時点の構成（XM=MIX_EA v1.1・OANDA=MIX_EA_OANDA v1.0・F_test設定）
**本書のゴール:** 本日採用された全変更をXM端末に反映する。**OANDA側2端末は変更なし**（作業不要）。

---

## 0. 本日の変更サマリ（何がどう変わったか）

| # | 変更 | 内容 | 検証 |
|---|---|---|---|
| 1 | **BTC funding枠 新設**（Magic 20260720） | funding悲観極端→踏み上げロング。閾値-0.004・退出=funding>90日中央値・上限20日・災害SL40%・0.01lot基準 | full +39,036/PF2.17/DD9.4%・Bybit独立再現t=2.49・執行/異常系/MC/スリッページ全合格 |
| 2 | **BfxRev枠 新設**（Magic 20260724） | Bitfinexロング建玉5日-10%超急減→リバウンド10日保有・災害SL75%・0.01lot基準 | full +57,812/PF1.98・IS PF4.44（IS取引8の留保はユーザー承認済み） |
| 3 | **ETH枠 刷新**（Magic 20260710・置換） | MA200単独→A2デュアルMA（200/40+クールダウン5日+災害SL45%）・0.05lot基準 | full +7,576/PF1.81(0.02換算)・630格子の応答曲面で台地中心を確認 |
| 4 | **暗号ロット2倍 採用** | Mult_BTC_FUND=2 / Mult_BFXREV=2 / Mult_ETH=2（実効: 0.02/0.02/0.10） | 実測ladder: 2x=DD26.1%（暗号枠のみ・10万基準）でDD30%予算内 |
| 5 | 暗号同時上限ガード実装 | MaxCryptoConcurrent入力（口座横断Magic監視）。**実測で効率劣化のため既定0=無効のまま使う** | cap=1は利益-36%/DD-26% |
| 6 | 統合ブック実測 | XM 15構成: 月+1.74%（対50万・DD9.6%）/ OANDA 12構成: 月+1.32%（対50万・DD6.3%） | docs/MIX_EA_UM.md §10 |

**変更しないもの:** FX/SCA枠の設定・ロット（全てそのまま）。OANDA版EA（暗号CFD非対応のため13枠のまま）。

---

## 1. 事前準備（XM端末・約5分）

1. **リポジトリ更新:** `git pull`（mainに全変更マージ済み）
2. **WebRequest許可URLの追加**（ツール → オプション → エキスパートアドバイザ）:
   - `https://fapi.binance.com` （BTC funding枠）
   - `https://api-pub.bitfinex.com` （BfxRev枠）
   - ※2行とも必要。「WebRequestを許可する」チェックもON
3. **データCSVの初回配置**（以後はEAがAPIで自動更新するため一度だけ）:
   - 開発PCで `python ml/fetch_btc_alt_data.py` → `ml/funding_btc.csv`
   - 開発PCで `python -u ml/fetch_btc_alt_data3.py bitfinex` → `ml/bfx_btc_long.csv`
     （すでに取得済みならそのファイルでよい）
   - 2ファイルを運用PCの `C:\Users\<user>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\` へコピー
   - ※配置しなくてもEAは起動する（API取得にフォールバック）が、初回から履歴を持たせる方が安全

## 2. EA更新（XM端末・約5分）

1. `experts/MIX_EA.mq5` を運用XM端末の `MQL5\Experts\` へコピーし、MetaEditorでコンパイル
   （開発PCで0エラー確認済み）
2. **ETH枠のポジション確認（重要）:** ETHUSDにMagic 20260710の買いポジションが**ある**場合、
   v1.3への切替で退出線がMA200→MA40に変わるため、**MA40を既に割れていれば次のD1バーで
   即決済される**。これは仕様（新ロジックの正しい動作）だが、意図しない即決済を避けたい場合は
   ポジション決済後（フラット時）に切り替える
3. チャートのMIX_EAを再アタッチ（既存チャートのまま。入力を下記に設定）

## 3. 入力設定（変更分のみ・他はF_test設定のまま）

| 入力 | 値 | 備考 |
|---|---|---|
| **Mult_BTC_FUND** | **2.0** | ロット見直し採用値（実効0.02） |
| **Mult_BFXREV** | **2.0** | 同（実効0.02） |
| **Mult_ETH** | **2.0** | 同（実効0.10） |
| En_BTC_FUND / En_BFXREV / En_ETH | true（既定） | |
| MaxCryptoConcurrent | 0（既定） | 実測で効率劣化のため無効のまま |
| EnableOpsLog | true | 従来どおり（mixlogにDEAL/DAILY/SKIP記録） |
| その他（FX/SCA枠・GlobalLotMult等） | 変更なし | F_test設定を維持 |

## 4. 起動確認チェックリスト

エキスパートタブで以下を確認:

```
□ MIX_EA v1.3 (XM) 起動 | 有効枠数=15/16 | Master=ON | LotMult=1.0 | CryptoCap=OFF
□ BTC funding枠: NNNN件ロード | 閾値-0.0040%/8h | 退出=med90(上限20日)
□ BfxRev枠: NNNN日ロード | 急減-10%/5日 | 保有10日
□ funding API取得: 1000件 ...（ライブのみ・数分以内に出る）
□ Bitfinex API取得: N日分マージ ...（同上）
□ err=4014 が出ていない（出たら手順1-2のURL許可を再確認）
```

※有効枠数15/16 = 16スリーブ中PB_AUDJPY（死に枠・既定OFF）を除く15。

## 5. 撤去・排他の確認

- □ **単独版EA（FundingRev_EA / ETH_EA / BfxRev_EA）のチャートが残っていないこと**
  （MIX v1.3と同Magic/同エクスポージャーのため併走すると二重発注になる。
  もし単独版で運用を始めていた場合はそのチャートを削除してからMIX v1.3を有効化）
- □ OANDA FX端末・OANDA CFD端末: **何も変更しない**（暗号3戦略はXM専用）

## 6. 運用監視（変更後の追加ポイント）

- **暗号3枠はイベント型**: BTC funding≈5.6回/年・BfxRev≈6回/年（ゼロの年もある・2022年実績）・
  ETH≈5回/年。**数週間取引がなくても正常**。生存確認はmixlogのDAILY行と
  「funding API取得」「Bitfinex API取得」のログ行（日次）
- 月次レビュー: mixlog DEAL（Magic 20260710/20260720/20260724）とバックテスト再実行
  （configs/eth_ea_d1.yaml・fundingrev_btcusd_d1.yaml・bfxrev_btcusd_d1.yaml）の突合。
  **%リターンを主指標**にする（円建ては年次ムラが大きい: docs/btc_backlog3.md M1）
- 2026年YTDの照合台帳: docs/btc_backlog3.md M6（BTC funding 8取引+5,463円）
- 災害SL（40/45/75%）は**歴史上不発火の保険**。刺さった場合=取引所事故級イベント→状況レビュー
- 四半期: XMの暗号スワップ確認（現行BTC/ETHとも約-24.8%/年。大幅悪化なら再評価）

## 7. 想定成績（参照値・docs/MIX_EA_UM.md §10）

| ブック | 月利（対50万） | 最大DD（対50万） |
|---|---|---|
| XM統合（暗号2x込み・15構成） | +1.74%/月 | 9.6% |
| OANDA統合（12構成） | +1.32%/月 | 6.3% |

※10年月割りの保守値・FX/SCAは基準ロット。実口座残高（XM 6.5万等）に対しては比例読み替え。
※暗号枠の月次寄与は平均+1,048円/月（2x・10万暗号基準）だが0円の月が大半の分布。

## 8. ロールバック手順（問題発生時）

1. 即時停止: MIX_EA入力 `MasterEnable=false`（全枠の新規停止・ポジは手動判断）
2. 暗号枠のみ停止: `En_BTC_FUND=false / En_BFXREV=false`（ETH枠は旧スリーブ相当に戻すなら
   `Mult_ETH=1.0`のうえ`ExitMA変更は不可`のためEn_ETH=falseで停止→旧版が必要なら
   gitの旧コミット（v1.1: タグ相当 2026-07-07時点）からMIX_EA.mq5を取得して再コンパイル）
3. 障害報告: mixlogとエキスパートログを添えて開発側へ（週次レポートPRと同経路）

---

**関連ドキュメント:** MIX_EA_UM.md（§8 v1.2 / §9 ロット・ガード / §10 統合実測）・
fundingrev_live_setup.md・bfxrev_live_setup.md・ETH_EA_UM.md（単独版は参考・運用はMIX統合）
