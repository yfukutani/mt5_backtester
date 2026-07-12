# FundingRev_EA ライブ設置手順（運用PC用）

BTC funding逆張り（バックログG1・2026-07-12採用）をXMライブ口座で稼働させる手順。
**v1.1はEA単体で完結**: Binance APIから資金調達率を自動取得するため、日次スクリプトは原則不要。

## 1. WebRequestの許可（必須・一度だけ）

MT5（XM）で: **ツール → オプション → エキスパートアドバイザ**
1. 「次のURLのWebRequestを許可する」にチェック
2. リストに追加: `https://fapi.binance.com`

これを忘れるとEAログに `err=4014 →WebRequest許可URLに...` が出て、新規エントリーだけが止まる
（決済は影響なし）。

## 2. EAの配置とチャート設置

1. `experts/FundingRev_EA.mq5` を運用端末の `MQL5\Experts\` へコピーしMetaEditorでコンパイル
   （0エラー確認済み・2026-07-12）
2. **BTCUSD D1** チャートを開き、EAをアタッチ（自動売買ON）

## 3. 入力（10万円テスト水準は既定のまま）

| 入力 | 値 | 備考 |
|---|---|---|
| Threshold_Pct8h | -0.004 | 5%分位・事前決定値。**変更しない** |
| HoldDays | 5 | 同上 |
| LotSize | 0.01 | 10万円テスト水準 |
| UseWebRequest | true | API自動更新（既定） |
| UpdateCsvCache | true | 取得成功時にキャッシュ保存（既定） |
| DisasterSL_Pct | 0.0 | SL無しが仕様（分析準拠）。付けるなら20〜30 |
| MagicNumber | 20260720 | MIX_EAと重複しない |

## 4. 起動確認

エキスパートタブに以下が出ればOK:

```
funding API取得: 1000件 2025.XX.XX..2026.XX.XX
FundingRev v1.1 起動 | funding 1000件 ... | ライブ(API自動更新)
```

`起動時API失敗→CSV代替` が出た場合は手順1のURL許可を確認。

## 5. 動作仕様（監視のポイント）

- 判定は**新D1バー時のみ**（サーバー0:00頃）。前日のfunding日平均 < -0.004%/8h でロング、
  5営業バー後に成行クローズ。
- **シグナル頻度は約5.6回/年**。数ヶ月無取引は正常（2024-25はfundingプラス常態）。
  生存確認はログの `funding API取得` 行（日次）で行う。
- **フェイルセーフ設計**: API失敗→1時間ごとに再試行→キャッシュCSV→手動CSVの順で代替。
  全滅時は**新規エントリーのみ停止**（安全側）。**決済はデータ非依存で必ず実行**される。
- 端末再起動に頑健: 保有日数はポジションのオープン時刻から再計算（カウンタ持ち越し不要）。

## 6. フォールバック（WebRequestが使えない環境のみ）

EA入力 `UseWebRequest=false` にすると、EAは毎D1バーで `Common\Files\funding_btc.csv` を
再読込する外部更新モードになる。その場合のみ日次スクリプトを登録:

```
schtasks /Create /TN "MT5\UpdateFunding" /SC DAILY /ST 06:30 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\repo\ops\update_funding.ps1"
```

`ops/update_funding.ps1` がBinanceから取得→Common\Filesへコピーし、`ops/update_funding.log` に
結果を残す（要Python）。

## 7. バックテストする場合（開発PC）

テスターは常にCSV参照（WebRequestはテスター不可）。事前に:
```
python ml/fetch_btc_alt_data.py   # → ml/funding_btc.csv
```
を `C:\Users\<user>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\` へコピー。
config: `configs/fundingrev_btcusd_d1.yaml`

## 8. 成績（採用根拠・0.01lot・スワップ実費込み）

| 期間 | 純益 | PF | DD |
|---|---|---|---|
| full 2019.09-2026.06 | +24,819 | 1.81 | 11.0% |
| IS 2021.06- | +23,585 | 1.84 | 11.1% |

プラトー: 隣接値（th-0.003/-0.005、hold3/7）全プラス。対ETH相関+0.138。
詳細: docs/btc_backlog.md フェーズ2セクション。

## 9. 定期確認

- 月次: mixlogと同様に取引履歴を確認（Magic 20260720）。シグナル頻度の推移。
- 四半期: XMのBTCUSDスワップ確認（現行ロング-65円/日/0.01lot。大幅悪化なら再評価）。
