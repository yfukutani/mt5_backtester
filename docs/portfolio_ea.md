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
| 6b | RSI_Reversal（レンジ強化） | GBPUSD | H4 | 20260774 | 固定 | `En_RSI_GBPUSD` |
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

## サイジング制御（per-sleeve 倍率・配分資金）

- **`GlobalLotMult`**: 全枠のロットを一律スケール（資金規模調整）。
- **`Mult_*`**（各枠の倍率・既定1.0）: 枠ごとにロットを増減。固定ロット枠は線形にスケール（検証: GOLD Mult6＝
  純利益ちょうど6倍）。リスクパリティ増レバ配分を1チャートで再現できる。
- **`RefCap_*`**（PB USDJPY/PB GBPJPY/Carry、既定0）: risk%/複利枠のサイズ基準。**0なら口座equity基準
  （＝1口座共有時は口座全体に対し過大化）、>0ならその配分資金で固定**（静的サイズ・過大化を防ぐ）。

> 既定（全Mult=1.0・RefCap=0）では従来挙動と完全一致（各枠が個別EAとビット一致を維持）。

### 増レバ配分デプロイ例：元金50万・月利3%級（高DD覚悟）

`mt5bt portfolio` で設計・実測したリスクパリティ増レバ配分（+1,724,755 / 月利約2.9% / 最大DD24.2% / RD10.38、
全期間open_prices）を、PortfolioEA 1チャートで再現する設定。**口座 500,000 JPY** に投入し：

| 入力 | 値 | 入力 | 値 |
|---|---|---|---|
| `GlobalLotMult` | 1.0 | `Mult_RSI_USDJPY` | 2.0 |
| `Mult_PB_USDJPY` | 3.0 | `Mult_RSI_EURUSD` | 2.0 |
| `RefCap_PB_USDJPY` | 80000 | `Mult_RSI_GBPUSD` | 2.0 |
| `Mult_PB_GBPJPY` | 1.0 | `Mult_PAIR` | 2.0 |
| `RefCap_PB_GBPJPY` | 30000 | `Mult_CARRY` | 2.0 |
| `Mult_PB_GOLD` | 6.0 | `RefCap_CARRY` | 100000 |
| `Mult_VBO` | 2.0 | `Mult_ETH` | 8.0 |

> **実効サイズ:** PB USDJPY=risk6%相当（80k基準）、Carry=複利0.10相当、GOLD=0.06、ETH=0.40、RSI×3/Pair/VBO=0.02、
> PB GBPJPY=risk2%（30k基準）。スケーラブル枠に増レバ集中、負スキュー枠は最小増でDD爆発を回避。
>
> ⚠️ **高DD覚悟の中身:** (1) `RefCap` 指定で risk%/複利は**静的サイズ**（複利しない）＝backtestのサブ口座複利より
> やや保守的→実効月利は約2.5%前後、every_tickでは更に低下（Carry−33%）。(2) 増レバ水準が「綺麗にスケールする点」を
> 超え（PB risk6%・Carry0.10・GOLD0.06・ETH0.40）、**2018型のリスクオフで相関急騰時はDD24%を大きく超え得る**。
> (3) Carryのスワップ近似・ETHの財務/規制リスクが最も増レバした枠に乗る。**まず小さめ（GlobalLotMult=0.7等）で
> 開始しDDを実測しながら上げること。**

## 位置づけ

- **ライブ運用専用。** バックテスト・相関測定・新戦略検証は個別EA＋`mt5bt portfolio` を継続使用。
- 単一障害点（1EAのバグ/クラッシュが全枠に波及）になるため、本番投入前に十分なフォワードテストを推奨。
