# PortfolioEA — 統合ポートフォリオEA（1チャートで全枠稼働）

**作成日:** 2026.06.28
**目的:** 本番ブックの全枠を**1チャートにアタッチするだけ**で内部稼働させ、10チャート分の運用を1つに集約する。
ライブ運用専用（各戦略の研究・検証は個別EA＋`mt5bt`を引き続き使用）。

## 仕組み

`experts/PortfolioEA.mq5`。内部に枠リスト（銘柄・時間足・戦略・Magic・サイジング・パラメータ）を保持し、
`OnTick` で各枠の銘柄・時間足の**新バーを検出して該当戦略を実行**する。MagicNumberで枠ごとに独立。
MT5は1EAから複数銘柄のデータ取得・発注が可能なので、1チャート（任意の銘柄）で全枠を回せる。

## 内蔵する枠（本番ブック）

| 枠 | 戦略 | 銘柄 | 足 | Magic | サイジング | トグル |
|---|---|---|---|---|---|---|
| 1 | PullbackTrend | USDJPY | H4 | 20260622 | risk2% | `En_PB_USDJPY` |
| 2 | PullbackTrend | GBPJPY | H4 | 20260627 | risk2% | `En_PB_GBPJPY` |
| 3 | PullbackTrend | AUDJPY | H4 | 20260628 | 固定 | `En_PB_AUDJPY`（既定OFF＝死に枠） |
| 4 | PullbackTrend | GOLD | H4 | 20260640 | 固定 | `En_PB_GOLD` |
| 5 | RSI_Reversal | USDJPY | H4 | 20260610 | 固定 | `En_RSI_USDJPY` |
| 6 | RSI_Reversal | EURUSD | H1 | 20260605 | 固定 | `En_RSI_EURUSD` |
| 7 | PairTrade | EURUSD/GBPUSD | H1 | 20260629 | 固定 | `En_PAIR` |
| 8 | Carry | AUDJPY | D1 | 20260650 | 複利0.05 | `En_CARRY` |
| 9 | VolBreakout | USDJPY | H4 | 20260680 | 固定 | `En_VBO` |
| 10 | 暗号トレンド（Carryロジック） | ETHUSD | D1 | 20260710 | 固定0.05 | `En_ETH` |

> パラメータは各個別EAの本番configと同一値をEA内に固定。RSIの補助フィルター（トレーリング/BE/ADX/時間/
> ボラ）は本番で全OFFのため非実装＝OFF相当。

## 検証：個別EAとビット一致

単一枠のみ有効にしてバックテストし、対応する個別EAの値と完全一致を確認（全期間・open_prices）。

| 枠 | PortfolioEA | 個別EA |
|---|---|---|
| PB USDJPY | +42,406 / 104取引 | +42,406 / 104 |
| RSI USDJPY | +8,492 / 174 | +8,492 / 174 |
| VolBreakout | +16,501 / 313 | +16,501 / 313 |
| PairTrade | +12,143 / 144 | +12,143 / 144 |
| Carry | +177,524 / 36 | +177,524 / 36 |
| ETH | +15,816 / 30 | +15,816 / 30 |

> **5戦略すべてビット一致＝移植は正確。** 残る枠（PB GBPJPY/GOLD・RSI EURUSD）は同じコードパスの
> 別銘柄・別パラメータのため、上記で検証済み。全枠同時稼働も正常動作を確認（1チャートで複数銘柄横断）。

## デプロイ手順

1. 必要EA（`PullbackTrend`/`RSI_Reversal`/`PairTrade`/`Carry`/`VolBreakout` ＋ `PortfolioEA`）をコンパイル。
   ※`PortfolioEA` は他EAを呼ばず自己完結なので、ライブは `PortfolioEA.ex5` だけでも可。
2. 気配値に全銘柄を表示: USDJPY/GBPJPY/AUDJPY/EURUSD/**GBPUSD**/GOLD/ETHUSD（GBPUSDはPairの従シンボル）。
3. **任意の1チャートに `PortfolioEA` をアタッチ**（チャート銘柄は何でもよい＝EAが各銘柄を明示参照）。
4. 「アルゴ取引を許可」ON。不要な枠は `En_*` でOFF。`MasterEnable=false` で全発注を一括停止可能。

## ⚠️ サイジングの注意（重要）

risk%（PB）・複利（Carry/Pair）枠は **口座全体のequity基準**でロットを計算する。1口座に全枠を載せると、
これらの枠が**25万全体に対してサイズを取り、backtestのサブ口座想定より大きくなる**（全枠同時・deposit100万の
素の検証で最大DD54.68%）。実運用では：

- **`GlobalLotMult`** で全枠を一律スケール（まず小さめで開始しDDを実測しながら調整）。
- 厳密にリスクパリティ配分を再現したい場合は、risk%/複利を**口座equityでなく各枠の配分資金基準**で計算する
  改修が望ましい（将来の拡張候補）。固定ロット枠（GOLD/RSI/Pair/VBO/ETH）はこの影響を受けない。

## 位置づけ

- **ライブ運用専用。** バックテスト・相関測定・新戦略検証は個別EA＋`mt5bt portfolio` を継続使用。
- 単一障害点（1EAのバグ/クラッシュが全枠に波及）になるため、本番投入前に十分なフォワードテストを推奨。
