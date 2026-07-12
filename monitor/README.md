# forward_monitor — フォワードテスト監視ツール（改善案S-1）

**目的:** EA脱落・自動売買OFF・端末停止による**サイレント取りこぼしを当営業日中に検知**する。
（2026.07.06のXM脱落事件＝OANDAが取った同一シグナルをXMだけ9時間気づかず逃した事象への対策）

**性質:** 完全読み取り専用（発注系API不使用）・EA本体は無改修・戦略検証ゲートの対象外（運用ツール）。

## 検知内容（端末ごと）

| チェック | 判定 | レベル |
|---|---|---|
| mixlogファイル存在（当月+前月） | 両方無し | 🚨 ALERT |
| 最終レコード鮮度 | 平日26h超（月曜は80h超）前 | 🚨 ALERT |
| 当日DAILYハートビート | 平日に無し | ⚠️ WARN（早朝は正常のため） |
| 当日SCA_RANGE行（サーバー9:30以降） | 所定銘柄に欠落 | 🚨 ALERT（セッション窓にEA不在＝取りこぼし進行中） |
| 端末接続 connected ※ | false | 🚨 ALERT |
| 自動売買 trade_allowed ※ | false | 🚨 ALERT |
| 端末プロセスが落ちていた ※ | initializeで自動起動 | ⚠️ WARN（復旧兼用・EA復帰は次回mixlogで確認） |

※=MetaTrader5パッケージがある場合のみ。無い環境ではmixlog監視のみで動作（degraded表示）。
週末（サーバー時刻の土日）は鮮度・DAILY・SCA_RANGEチェックを自動スキップ（誤報防止・検証済み）。

## 出力

- コンソール: 端末ごとに `[OK] / [WARN] / [ALERT]` と詳細
- `monitor_log.csv`: 全実行の履歴（追記）
- `ALERT_YYYYMMDD_HHMM.txt`: ALERTが1件でもあれば `alert_dir`（既定: デスクトップ）に生成
- 終了コード: 0=全OK / 1=ALERTあり / 2=WARNのみ

## セットアップ（ライブVPS上で実施）

1. この `monitor/` フォルダをVPSへコピー（例: `C:\mt5monitor\`）
2. Python 3.x を確認（`python --version`）。可能なら `pip install MetaTrader5`
   （無くてもmixlog監視は動作するが、接続/自動売買OFFの検知が省かれる）
3. `monitor_config.json` を**VPSの実環境に書き換え**:
   - `terminal_path`: 各端末のterminal64.exeのフルパス
   - `files_dir`: 各端末で「ファイル > データフォルダを開く」→ 開いたパス + `\MQL5\Files`
   - `prefix`: EAの `OpsLogPrefix`（XM="mixlog" / OANDA="mixlog_oa"）
   - `sca_symbols`: その口座で稼働するSCA銘柄（CFD口座は `["XAUUSD"]` のみ等）
   - `server_utc_offset`: 夏3 / 冬2（**DST切替の3月・11月に手動更新**）
   - `alert_dir`: アラートファイルを置く場所（気づける場所に）
4. 手動実行して全端末 `[OK]` を確認:
   ```
   python C:\mt5monitor\forward_monitor.py
   ```

## タスクスケジューラ登録（平日2回・管理者PowerShellで）

```powershell
# 朝チェック（日次生存確認・日本時間9:05）
schtasks /Create /TN "FwdMonitor_AM" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:05 `
  /TR "python.exe C:\mt5monitor\forward_monitor.py"

# 午後チェック（サーバー9:30セッション窓の確認・日本時間16:05）
schtasks /Create /TN "FwdMonitor_PM" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:05 `
  /TR "python.exe C:\mt5monitor\forward_monitor.py"
```
※ サーバー9:30(GMT+3) = 日本時間15:30。16:05実行でセッション窓の欠落を**当日中に検知**できる。
※ pythonがPATHに無い場合はフルパス（例 `C:\Python312\python.exe`）を指定。

## ALERT時の対応手順

1. 該当端末を起動（落ちていた場合。本ツールのAPIチェックが自動起動していることもある）
2. チャートにMIX_EA/MIX_EA_OANDAが載っているか確認（消えていたら再アタッチ・設定はF_test_setting.md）
3. 「アルゴリズム取引」ボタンON・ニコちゃんマーク確認
4. 数分後に再実行し、当日mixlog行（DAILY/SCA_RANGE）が出ることを確認

## 制約・注意

- **祝日**（市場休場の平日）は誤ALERTになりうる → その日のアラートは無視でよい
- DST切替（3月/11月）で `server_utc_offset` を 3⇔2 に手動更新
- mt5.initializeは端末未起動時に**起動を試みる**（＝簡易自動復旧を兼ねる）が、
  チャートへのEA復帰までは保証しない。復帰確認は次回実行のmixlog判定で行う
- 検証済み経路（開発機・2026.07）: ログ欠落→ALERT+通知ファイル+exit1 ✓ / 週末スキップ→OK ✓
