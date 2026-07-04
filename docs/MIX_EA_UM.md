# MIX_EA ユーザーマニュアル（MIX_EA_UM）

**作成日:** 2026.07.05
**対象:** `experts/MIX_EA.mq5`（XM版）/ `experts/MIX_EA_OANDA.mq5`（OANDA証券版）v1.0
**位置づけ:** 既存ブック（PortfolioEA 11枠）と SCA セッションORBスキャルパー（3枠・
2バックログ計200案の検証を経た最終形）を**1つに合体した統合EA**。1チャートに
アタッチするだけで全枠が稼働する。

---

## 1. 概要

| | XM版 (MIX_EA) | OANDA版 (MIX_EA_OANDA) |
|---|---|---|
| 収録枠数 | **14枠**（既存11+SCA3） | **13枠**（既存10+SCA3、ETHなし） |
| 想定サーバー | XMTrading MT5（GMT+2/+3） | OANDA-Japan MT5 Live（GMT+2/+3・検証済み同一時刻系） |
| 銘柄名 | 固定（GOLD等） | input化（Sym_*でサフィックス差吸収・GOLD→XAUUSD） |
| 特記 | — | ETHUSDは取扱なし（既定OFF）。XAUUSDはCFDアクセス前提 |

### 収録枠一覧

| # | 枠 | 戦略 | 銘柄 | TF | Magic | 既定ロット |
|---|---|---|---|---|---|---|
| 1 | PB USDJPY | PullbackTrend+MTF | USDJPY | H4 | 20260622 | risk2% |
| 2 | PB GBPJPY | PullbackTrend+MTF | GBPJPY | H4 | 20260627 | risk2% |
| 3 | PB AUDJPY | （死に枠・既定OFF） | AUDJPY | H4 | 20260628 | 0.01 |
| 4 | PB GOLD | PullbackTrend | GOLD/XAUUSD | H4 | 20260640 | 0.01 |
| 5 | RSI USDJPY | RSI_Reversal | USDJPY | H4 | 20260610 | 0.01 |
| 6 | RSI EURUSD | RSI_Reversal | EURUSD | H1 | 20260605 | 0.01 |
| 7 | RSI GBPUSD | RSI_Reversal | GBPUSD | H4 | 20260774 | 0.01 |
| 8 | PairTrade | 統計的裁定 | EURUSD/GBPUSD | H1 | 20260629 | 0.01 |
| 9 | Carry AUDJPY | MAヒステリシス | AUDJPY | D1 | 20260650 | 複利0.05 |
| 10 | VBO USDJPY | VolBreakout | USDJPY | H4 | 20260680 | 0.01 |
| 11 | ETH（XMのみ） | 暗号トレンド | ETHUSD | D1 | 20260710 | 0.05 |
| **12** | **SCA GOLD** | **セッションORB最終形** | GOLD/XAUUSD | M15 | 20261002 | 0.01 |
| **13** | **SCA USDJPY** | セッションORB初版形 | USDJPY | M15 | 20261000 | 0.01 |
| **14** | **SCA GBPJPY** | セッションORB初版形 | GBPJPY | M15 | 20261001 | 0.01 |

**SCA枠の中身（ハードコード済み・変更不要）:**
- GOLD: レンジ1-9時→ブレイク9-15時→20時全決済。MinRange0.40×D1ATR・buf0.05・RR1.5・
  **金曜エントリーなし**・**リバーサル型増しロット**（レンジ内ドリフトと逆方向のブレイクは2倍）
- USDJPY/GBPJPY: レンジ0-9時→ブレイク9-12時→22時決済。MinRange0.30・RR2.0・Revブースト

## 2. セットアップ手順

1. **コンパイル**: 各端末のMetaEditorで `MIX_EA.mq5`（XM）/ `MIX_EA_OANDA.mq5`（OANDA）を
   コンパイル（外部ファイル依存なし・0エラーを確認済み）
2. **アタッチ**: 任意の1チャートにEAを1つだけ載せる（推奨: USDJPY M15。チャートは
   新バー検出のトリガーに過ぎず、全枠は内部で各銘柄・各TFを監視する）
3. **アルゴリズム取引を許可**、自動売買ボタンON
4. 入力を下記「推奨設定値」に合わせる → OK
5. エキスパートログに「MIX_EA v1.0 起動 | 有効枠数=14/14」が出れば正常
6. **禁止事項**: 同一口座でPortfolioEA/SCA_EA単体と併用しない（Magic重複で二重発注）

## 3. 推奨設定値

### シナリオA: XM 50万円（既存第5案 + SCAミックスB）— 標準推奨

| 入力 | 値 | 入力 | 値 |
|---|---|---|---|
| `GlobalLotMult` | 1.0（**開始時0.7**） | `Mult_RSI_USDJPY` | 2.0 |
| `Mult_PB_USDJPY` | 3.0 | `Mult_RSI_EURUSD` | 2.0 |
| `RefCap_PB_USDJPY` | 70000 | `Mult_RSI_GBPUSD` | 3.0 |
| `Mult_PB_GBPJPY` | 1.0 | `Mult_PAIR` | 5.0 |
| `RefCap_PB_GBPJPY` | 30000 | `Mult_CARRY` | 3.0 |
| `Mult_PB_GOLD` | 9.0 | `RefCap_CARRY` | 100000 |
| `Mult_VBO` | 2.0 | `Mult_ETH` | 12.0 |
| **`Mult_SCA_GOLD`** | **3.0** | **`Mult_SCA_USDJPY/GBPJPY`** | **1.0** |

- 成績（決済ベース合算・2016-2026）: **月平均+5.57%（対50万）/ 最大DD約19.3万円**
  （既存第5案単独: 月4.51%/DD18.7万円 → SCA追加で+1.06pt・DD+3%）
- DD増を許容しない場合: `GlobalLotMult=0.95`（全体5%縮小）→ 月約5.3%/DD18.4万円（現行同等）

### シナリオB: XM 80万円（第5案フル + SCAミックスB）— 保守推奨

入力はシナリオAと同一（口座残高だけ80万）。
**月平均+3.48%（対80万）/ 対資金DD 24.1%** ・月次相関+0.13の分散効果
（XMのみ稼働+遊休30万に対し月利+0.66pt）。

### シナリオC: OANDA 50万円（OANDA第1案 + SCA3枠）

| 入力 | 値 | 補足 |
|---|---|---|
| 既存枠 | [portfolio_ea.md](portfolio_ea.md)のOANDA第1案表の通り | PB GOLD 9.0/PAIR 5.0/CARRY 3.0等 |
| `Mult_SCA_GOLD` | 3.0 | XAUUSD=CFDアクセス必要。なければ`En_SCA_GOLD=false` |
| `Mult_SCA_USDJPY/GBPJPY` | 1.0〜2.0 | **OANDAのタイトスプレッドでXM比+64〜139%の検証実績** |

参考: OANDA第1案単独=月6.33%/DD23.8%（ツール実測・2026.07.03凍結値）。SCA JPYは
10年で+45,736円/0.01lot（OANDA実測）の上乗せ+分散。

### シナリオD: SCA単独 30万円（既存ブックなしでSCAだけ運用）

既存枠を全て`En_*=false`、SCA3枠のみON、`Mult_SCA_GOLD=3.0`/JPY 1.0。
- XM: **月+2.13% / DD 26.1%**（対30万・Boost込み）
- 推奨: **GOLDはXM版・JPY2枠はOANDA版に分けた混成**＝**月+2.18% / DD 24.8%**（最良効率）
- 複利参考: +20%毎に段階増ロットで10年 30万→約280万（9.3倍・対ピークDD16.8%・月次勝率63%）

## 4. バックテスト結果（サマリー）

**検証原則: 成績の正は各戦略の個別EAによるevery_tick検証**（スキャルピングはスプレッド
実費込み必須）。統合EAはライブ運用用で、以下は個別検証済み結果の合算（決済ベース・2016-2026）。

| 構成 | 資金 | 純利益(10年) | 最大DD | 月平均利 |
|---|---|---|---|---|
| XM既存11枠（第5案） | 50万 | +2,707,703円 | 187,200円(37%) | +4.51% |
| **XM MIX（第5案+SCA B）= シナリオA** | 50万 | **+3,341,570円** | 192,939円(39%) | **+5.57%** |
| XM MIX = シナリオB | 80万 | +3,341,570円 | 192,939円(24%) | +3.48% |
| SCA3枠のみ（ミックスB・XM） | 30万 | +766,815円 | 78,250円(26%) | +2.13% |
| SCA3枠のみ（混成: XM GOLD+OANDA JPY） | 30万 | +784,198円 | 74,425円(25%) | +2.18% |

SCA単体の品質（個別every_tick・0.01lot）:

| 銘柄 | 純益(10年) | PF | DD% | 検証 |
|---|---|---|---|---|
| GOLD(XM・最終形) | +239,109円 | 1.73 | 13.9% | IS+163,827/PF1.83・OOS+39,490・モンテカルロDD P95=16.2%・PF95%CI[1.11,1.48] |
| USDJPY(XM/OANDA) | +12,286 / +20,529円 | 1.06 / 1.13 | 16.8 / 7.6% | OANDA優位+139% |
| GBPJPY(XM/OANDA) | +39,576 / +25,207円 | 1.09 / 1.07 | 18.9 / 19.4% | XMはBoost込み |

※注意: 既存ブックのバックテストはリスク%複利込みのため後年の伸びが大きい（実運用の
RefCap固定サイジングでは線形寄りになる）。利益の約6割が2025-26年に集中する構造は
両ブック共通（2025-26除外でもプラスは維持・I-6検証済み）。

## 5. 運用ノート

- **開始時は `GlobalLotMult=0.7`** で1-2ヶ月運用し、挙動確認後に1.0へ（全ブック共通規律）
- **DDレビュー**: 口座DDが20%到達で状況レビュー（ただし「DD後に停止・減量」はしない——
  検証でDD直後の取引はPF3.27と回復力こそ収益源。レビューは異常検知目的）
- **金曜・NY午後**: SCA GOLDは金曜と20時以降を自動回避（設定不要）
- **スプレッドガード**: 個別EAのMaxSpreadPointsに相当する機能はMIX_EAのSCA枠には未搭載
  （指標時の異常スプレッドはSL/TP距離が大きいため実害は限定的。気になる場合は
  経済指標の時間帯のみMasterEnable=falseで手動停止可）
- **年末年始**: 効果は中立と検証済み（自動対応不要）だが、流動性極薄の12/24・12/31は
  手動でMasterEnable=false推奨
- **VPS時刻**: サーバー時刻がGMT+2/+3系であることが前提。ブローカー変更時はセッション
  時刻の再検証が必要

## 6. 制約・既知事項

1. **バックテストするならチャートはM15**: open_pricesモードではチャートTFより下位の
   データを参照できないため、H4チャートだとSCA枠が動かない（`wrong timeframe request`）。
   M15チャート+open_pricesで全14枠の動作確認が可能（ただし成績評価は個別EAのevery_tickが正）
2. **OANDAのXAUUSD**: 商品CFDアクセスが必要。FX専用口座の場合は`En_SCA_GOLD=false`・
   `En_PB_GOLD=false`とし、GOLD系はXM側で運用する
3. **OANDA JPYのRevブースト**: XM実測+ログ合成（E2-3混成評価）で検証。OANDA単体での
   Boost込みEA実測は未実施（原理は同一市場・同一ドリフトのため有効性は同等と評価）
4. **ETHUSD**: OANDAは取扱なし（既定OFF）。XM版のみ
5. 個別EA（SCA_EA/PortfolioEA等）との**同一口座併用禁止**（Magic重複）

## 7. 関連ドキュメント

- [sca_ea.md](sca_ea.md) — SCAの開発ログ・全検証結果・OANDA比較
- [sca_scalping_backlog.md](sca_scalping_backlog.md) / [sca_scalping_backlog2.md](sca_scalping_backlog2.md) — 200案の検証記録
- [portfolio_ea.md](portfolio_ea.md) — 既存ブックの構成・第5案/OANDA第1案の詳細
- [forward_test_baseline.md](forward_test_baseline.md) — フォワードテスト基準
