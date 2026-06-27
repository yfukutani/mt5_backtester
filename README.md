# mt5bt — MT5 EA バックテスト CLI ツール

MetaTrader 5 (MT5) の EA（エキスパートアドバイザー）バックテストを自動化する Python 製コマンドラインツールです。
YAML 設定ファイルを書くだけで、MT5 ターミナルの起動・テスト実行・結果の解析・HTML/CSV レポートとチャートの生成までを一気通貫で行います。

- **バージョン**: 1.0.0
- **対応 OS**: Windows（MT5 ターミナルが動作する環境）
- **Python**: 3.9 以上

---

## 主な機能

- 🚀 **バックテスト自動実行** — MT5 ターミナルを INI + SET ファイルで制御し、ヘッドレスでテストを実行
- 🔍 **パラメータ最適化** — 範囲指定でのグリッド最適化（最適化基準を選択可能）
- 📊 **レポート生成** — HTML レポート・CSV サマリー・matplotlib チャート（残高曲線・ドローダウン・損益分布）
- 📋 **結果管理** — 保存済み結果の一覧表示・複数結果の比較
- 🖥️ **ターミナル自動検出** — インストール済み MT5 ターミナルを自動で探索

---

## インストール

```bash
git clone <repository-url>
cd mt5_backtester
pip install -e .
```

`pip install -e .` により `mt5bt` コマンドが使えるようになります（[setup.py](setup.py) の `console_scripts`）。
依存関係: click / PyYAML / MetaTrader5 / pandas / matplotlib / jinja2 / lxml / colorama / tabulate / numpy

> Windows のローカル環境では、ビルド済みの `mt5bt.bat` からも実行できます。

---

## クイックスタート

```bash
# 1. MT5 ターミナルの検出を確認
mt5bt list-terminals

# 2. バックテストを実行（完了後ブラウザでレポートを開く）
mt5bt run configs/example.yaml --open

# 3. 過去の結果を一覧表示
mt5bt list-results
```

---

## コマンド一覧

| コマンド | 説明 | 主なオプション |
|---|---|---|
| `mt5bt run <config>` | バックテストを実行しレポートを生成 | `--open` `--timeout` `--no-charts` `--no-html` `--no-csv` |
| `mt5bt optimize <config>` | パラメータ最適化を実行 | `--top N`（上位件数）`--timeout` |
| `mt5bt report <xml/csv>` | 既存のレポートからHTML/CSV/チャートを再生成 | `--open` `--no-charts` |
| `mt5bt list-results` | 保存済み結果を一覧表示（PF・DD・勝率など） | `--dir`（結果ディレクトリ） |
| `mt5bt compare <xml...>` | 複数のバックテスト結果を比較表示 | — |
| `mt5bt portfolio <config...>` | 複数EAを実行し合算エクイティから真のポートフォリオDDを算出 | `--timeout` |
| `mt5bt list-terminals` | インストール済みMT5ターミナルを検出 | — |

```bash
# 使用例
mt5bt run configs/rsi_bb_reversal.yaml --timeout 7200 --open
mt5bt optimize configs/example.yaml --top 30
mt5bt report results/MyEA/report.xml --open
mt5bt compare results/run1/report.xml results/run2/report.xml
mt5bt portfolio configs/pullback_usdjpy_h4.yaml configs/pullback_gbpjpy_h4.yaml configs/pairtrade_eurusd_gbpusd.yaml
```

> `portfolio` は各EAの全dealの損益を時系列で合算し、ポートフォリオ全体の最大ドローダウン・
> 純利益・分散効果（単独DD合計との差）を算出する。各EAは自前の配分資金を持つ独立サブ口座として扱う。
> EA側に取引明細を書き出す`EquityLogFile`入力が必要（同梱EAは対応済み）。

---

## 設定ファイル（YAML）

設定ファイルの全項目は [configs/example.yaml](configs/example.yaml) を参照してください。スキーマの定義は [mt5bt/config.py](mt5bt/config.py) にあります。

```yaml
# MT5ターミナルのパス（省略時は自動検出）
mt5_path: "C:\\Program Files\\MetaTrader 5\\terminal64.exe"

# ---- EA設定 ----
expert:    "RSI_Reversal"   # EAファイル名（.ex5なし）
symbol:    "USDJPY"         # 通貨ペア
period:    "H1"             # 時間足: M1/M5/M15/M30/H1/H4/D1/W1/MN1
from_date: "2024.01.01"     # 開始日
to_date:   "2025.06.20"     # 終了日

# ---- 口座設定 ----
deposit:  100000            # 初期入金（省略時 10000）
currency: "JPY"             # 通貨（省略時 USD）
leverage: 25                # レバレッジ（省略時 100）

# ---- テストモデル ----
# every_tick / control_points / open_prices / math_calculations / every_tick_real
model: "open_prices"        # 始値のみ＝最速（推奨）

# ---- EAパラメータ（固定値）----
parameters:
  StopLoss_Pips:   45
  TakeProfit_Pips: 105
  MagicNumber:     20260604
  LotSize:         0.01

# ---- 最適化設定（optimize コマンド使用時）----
optimize:
  enabled:   false
  criterion: "profit_factor"  # balance / balance_maxdd / profit_factor /
                              # expected_payoff / drawdown_pct / sharpe / custom
  parameters:
    StopLoss_Pips:   { from: 30, to: 100, step: 10 }
    TakeProfit_Pips: { from: 50, to: 150, step: 10 }

# ---- 出力設定 ----
report_dir:  "results"      # 結果保存ディレクトリ
report_name: ""             # 空ならEA名＋日時を自動付与
```

---

## プロジェクト構成

```
mt5_backtester/
├── mt5bt/                  # CLIパッケージ
│   ├── cli.py             # CLIエントリポイント（clickベース・6コマンド）
│   ├── config.py          # YAML読込・MT5パス自動検出・各種マッピング
│   ├── runner.py          # MT5ターミナルをINI+SETで制御
│   ├── parser.py          # XML / HTML / OnTester CSV のパーサー
│   ├── reporter.py        # HTML・CSVレポート生成
│   └── visualizer.py      # matplotlibチャート生成
├── experts/               # EA（.mq5）ソース
├── configs/               # バックテスト設定（*.yaml）
├── results/               # 実行結果（gitignore対象）
├── tests/                 # サンプルレポート・テスト生成物
├── setup.py
└── requirements.txt
```

---

## 同梱EA（experts/）

| EA | 戦略 | 主な対象 |
|---|---|---|
| **RSI_Reversal** | RSI + ボリンジャーバンド + ダブルパターン逆張り（MA200フィルター） | USDJPY/EURUSD H1, USDJPY H4 |
| **PullbackTrend** | MA200方向 + EMA20/50トレンド + EMA20押し目反発（順張り） | USDJPY H1/H4 |
| **KeltnerBreakout** | ケルトナーチャネル（EMA20±ATR×1.5）ブレイク + MA200 + ADX | USDJPY H4 |
| **DMI_Cross** | +DI/-DIクロス + ADX≥25 + MA200方向（順張り） | USDJPY H4 |
| **PairTrade** | EUR-GBPスプレッドのz-score平均回帰（マーケットニュートラル） | EURUSD/GBPUSD H1 |

> EA の `.mq5` ソースは MT5 の `MQL5/Experts/` にコピーしてコンパイルし、生成された `.ex5` をバックテストで使用します。

---

## 補助スクリプト

- **`run_atr_sl_yearly.ps1`** — RSI_Reversal の3チャート構成（USDJPY H4/H1, EURUSD H1）について、2016〜2026年の年次成績を ATR ストップ（×1.5, RR2.0）で一括集計する PowerShell スクリプト。

---

## 注意事項

- バックテストには MT5 ターミナル本体と、対象シンボルのヒストリカルデータが必要です。
- `configs/*_tmp.yaml` は最適化検証用の使い捨てファイルで、`.gitignore` 対象です。
- 認証情報を含む設定ファイルはコミットしないでください。
