# ETH枠 FULL期間履歴欠落 調査報告（2026-08-13）

対象: `docs/round6_phase3_20260813.md` §「FULLデータ監査」で報告された、10年FULL期間
(2016.06.21–2026.06.20) でETH枠(magic 20260710)が全構成から欠落し0取引になった事象。

**結論を先に述べる。**

1. 再現した。ただし**「期間を長くすると消える」という理解は誤り**である。消えるかどうかを
   決めているのは期間の長さではなく、**テスト開始日がブローカーのETHUSD履歴開始日
   2016.11.08 より前かどうか**の一点である。
2. 原因は「履歴が10年分ない」ことそのものではなく、履歴が無い時点で `OnInit` が
   `iMA(ETHUSD,D1,…)` を生成しようとして **エラー4805 で失敗し、EAが戻り値を検査しない**
   ため、ETH枠のMAハンドルが `INVALID_HANDLE` のまま**その run の全期間にわたり無言で
   死ぬ**ことである。
3. **round6_phase3 の FULL だけでなく、round6_phase2 の OOS 48件も同じ理由でETHが
   0取引だった。** phase3レポートの「IS/OOS個別ランではETHを含む全3枠を確認した」は
   誤りで、**OOSもETHは動いていない**（実測で確認）。IS(2021.06.21開始)だけが健全である。
4. フォワード運用で**この事象そのものは起きない**（ライブに開始日は無く、ETHUSDは9年超の
   履歴がある）。ただし**同じ無検査ハンドル生成が本番 `MIX_EA.mq5` にも存在し**、万一
   ハンドル生成に失敗した場合は**新規だけでなく決済ロジックも止まり、かつ何もログに出ない**。
   これは低確率だが実運用上の潜在的な堅牢性欠陥であり、別途の是正を推奨する。

---

## 1. 再現確認

`experts/MIX_EA_SIMVERIFY.mq5` にETH枠のみを有効化し(`En_ETH=true`、他15枠すべてfalse)、
every-tick・GOLD M15駆動・USD 900口座という phase3 と完全に同一の条件で、開始日だけを
変えた3本を逐次実測した。本番EA2ファイルと本番 `configs/*.yaml` は一切変更していない。

| プローブ | 期間 | 期間長 | ETH deal行 | 取引数 | 最終残高 | 4805エラー |
|---|---|---:|---:|---:|---:|---|
| A `a_full_0621` | 2016.06.21–2026.06.20 | 10.0年 | **0** | 0 | 900.00 USD（不変） | **あり ×2** |
| B `b_full_1109` | **2016.11.09**–2026.06.20 | 9.6年 | **88** | 44 | 1,121.47 USD | なし |
| C `c_oos_0621` | 2016.06.21–2021.06.20 | 5.0年 | **0** | 0 | 900.00 USD（不変） | **あり ×2** |

**AとBは終端が同じで期間長もほぼ同じ（10.0年 vs 9.6年）なのに、結果は0取引と44取引に
分かれる。** 一方AとCは期間長が10年と5年で倍違うのに、どちらも同じく0取引で同じエラーを
出す。従って**支配変数は期間長ではなく開始日**である。

Bで復活したETH枠のdealは、開始2017-04-07・終了2025-10-10で、
`docs/deploy_split_20260812.md` §4のETH_EA単独実測表（最初の記録deal 2017-04-07 /
最後の記録deal 2025-10-10）と**完全に一致**する。すなわちBが正しい姿である。

Bの円換算成績（phase3と同一の `converted_metrics` / 初期10万円換算）:

| 枠 | 純利益 | PF | DD | RF | 取引数 | 月利(120ヶ月) |
|---|---:|---:|---:|---:|---:|---:|
| ETH（回復後・FULL） | 27,257円 | 2.3416 | 6.4178% | 4.2471 | 44 | 0.227% |

phase3の個別枠FULL表で「無効（0取引、FULL履歴欠落）」としていた行は、この値で置き換えられる。

---

## 2. 原因の特定

### 2.1 決定的証拠

ブローカー側ETHUSD履歴の開始日はテスターログに明示されている。

```
ETHUSD: history synchronized from 2016.11.08 to 2026.08.01
```

テスト開始日 2016.06.21 は、この 2016.11.08 より**約4.5ヶ月前**である。その結果、
テスト開始時刻の `OnInit` で次が記録される（プローブAの実測ログ、23:06:50）。

```
GOLD,M15: testing of Experts\MIX_EA_SIMVERIFY.ex5 from 2016.06.21 00:00 to 2026.06.20 00:00 started with inputs:
ETHUSD: history synchronized from 2016.11.08 to 2026.08.01
2016.06.21 00:00:00   cannot load indicator 'Moving Average' (ETHUSD) [4805]
2016.06.21 00:00:00   cannot load indicator 'Moving Average' (ETHUSD) [4805]
...
final balance 900.00 USD
```

エラー2件は `TrendMA_Period=150` と `ExitMA_Period=40` の2本のMAに対応する。
4805 = `ERR_INDICATOR_CANNOT_CREATE`。

開始日を 2016.11.09 に動かしただけのプローブB（同23:08:47）では、**4805が消え、
最終残高が動く**。

```
GOLD,M15: testing of Experts\MIX_EA_SIMVERIFY.ex5 from 2016.11.09 00:00 to 2026.06.20 00:00 started with inputs:
ETHUSD: history synchronized from 2016.11.08 to 2026.08.01
ETHUSD,Daily: history cache allocated for 2508 bars and contains 1 bars from 2016.11.08 00:00 to 2016.11.08 00:00
ETHUSD,Daily: history begins from 2016.11.08 00:00
...
final balance 1121.47 USD
```

`ETHUSD,Daily: history cache allocated for 2508 bars` はAとBで同一であり、
**FULL期間分のD1キャッシュ枠は両方とも確保されている**。

### 2.2 EAコードの該当箇所

`experts/MIX_EA_SIMVERIFY.mq5` L431–476「ハンドル生成・銘柄メタ」。ETH枠は
`ST_CARRY` として実装されている（L375–378）。

```
} else if(S[i].strat==ST_CARRY){
   S[i].hTrend=iMA(S[i].symbol,S[i].tf,S[i].trendPeriod,0,MODE_SMA,PRICE_CLOSE);
   if(S[i].useHyst) S[i].hATR=iATR(S[i].symbol,S[i].tf,14);
   if(S[i].exitPeriod>0)
      S[i].hExit=iMA(S[i].symbol,S[i].tf,S[i].exitPeriod,0,MODE_SMA,PRICE_CLOSE);
}
```

- **戻り値を一切検査していない**。`INVALID_HANDLE` でもそのまま進む。
- ハンドル生成は `OnInit` の一度きりで、**再生成もリトライも無い**。
- 失敗しても `Print` が無く、**運用ログにもmixlogにも痕跡が残らない**。

対照的に `ST_FUNDING` / `ST_BFXREV` は同じループ内で初期化失敗を検査し、
`S[i].enabled=false` にしたうえで明示的に `Print` している。ETH枠(`ST_CARRY`)、
および `ST_PULLBACK` / `ST_RSI` / `ST_VBO` / `ST_SCA` にはこの防御が無い。

死んだハンドルが取引を止める経路は `ProcCarry`（L1164–1194）の冒頭である。

```
void ProcCarry(int i)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   double mb[]; ArraySetAsSeries(mb,true);
   if(CopyBuffer(S[i].hTrend,0,1,1,mb)<1) return;   // ← ここで毎バー即return
```

`CopyBuffer` は `INVALID_HANDLE` に対して -1 を返すため、**2016.11.08以降にETHUSDの
データが揃った後も、ハンドルは死んだままなので永久に return し続ける**。これが
「10年分のティック(255,948,814本)は生成・供給されているのに1取引も出ない」ことの説明である。

### 2.3 潰した対立仮説

| 仮説 | 判定 | 根拠 |
|---|---|---|
| ETHUSDの履歴が10年分揃っていない | **部分的に真だが原因ではない** | 開始日が2016.11.08より後なら、同じ2508バー枠のFULL窓で44取引が正常に出る（プローブB） |
| MT5テスターがFULL窓のETHティックを供給していない | **偽** | ログに `ETHUSD: generate 255948814 ticks ... passed to tester 255948814 ticks`。これは IS 203,704,273 + OOS 52,244,541 と**完全一致**する。データは全期間供給済み |
| 「データ終端で終わる窓しか実行不可」の既知制約 | **該当せず** | 3プローブとも終端は2026.06.20または2021.06.20で、既存の成功runと同じ形。既知制約（`docs/btc_backlog.md` L333、`docs/deploy_split_20260812.md` L170）は本件とは別事象 |
| MA期間(150)のバー数が期間先頭で不足 | **偽** | IS run のログは `ETHUSD,Daily: history cache allocated for 1685 bars and contains 380 bars from 2020.01.02 to 2021.06.18`。テスト開始前に380本のD1事前履歴が供給されており、150本の要件を満たす。またウォームアップ不足なら開始直後だけ沈黙して後で復活するはずだが、実際は全期間0取引 |
| 複数銘柄を単一テスターで駆動するティック同期問題 | **偽** | プローブBはA・Cと全く同じGOLD M15駆動・多銘柄構成で正常動作する |
| JPY口座でのUSD建て銘柄の換算ペア履歴不足（`docs/new_strategies_round2_20260805.md` のXAUJPY事例） | **該当せず** | 本件はUSD 900口座で、エラー文言も `no history data, stop testing` ではなく `cannot load indicator ... [4805]`。別事象 |

### 2.4 なぜ単体EA `configs/eth_ea_d1.yaml` では起きないか

`configs/eth_ea_d1.yaml` は `from_date: 2016.11.01` で、これも2016.11.08より前である。
それでもETH_EA単独では正常に動く。理由は2つある。

1. `experts/ETH_EA.mq5` は `iMA(_Symbol, …)` すなわち**プライマリ銘柄**を使う。テスターは
   プライマリ銘柄については必ず利用可能な範囲へテスト開始を合わせるため、履歴の無い時点で
   `OnInit` が走らない。ハンドル失敗が起きるのは**セカンダリ銘柄**（GOLD駆動下のETHUSD）に
   限られる。
2. ETH_EAは戻り値を検査している（L60–71）。仮に失敗すれば無言で死なず初期化エラーになる。

つまり本件は**「MIX_EA系で、駆動銘柄と異なるセカンダリ銘柄の枠を、その銘柄のデータ開始日より
前から開始したとき」に限って発生する**。

---

## 3. 影響範囲（過去成果物）

`En_ETH: true` かつ `from_date: 2016.06.21` の設定は次の通り。これらの**ETH枠の寄与はすべて
ゼロとして集計されている**。

| ディレクトリ | 該当設定数 | 影響 |
|---|---:|---|
| `ml/round6_phase2/configs` | **48**（OOS全件） | phase2の「暗号3枠」OOS成績は実際には**BTC funding + BfxRev の2枠**。`crypto_results.csv` のOOS行48件が該当 |
| `ml/round6_phase3/configs` | **14**（FULL全件 + OOS全件） | phase3のFULL列およびOOS列のETH寄与が欠落 |
| `ml/simverify/configs` | 1 | 要個別確認 |

IS窓 (`from_date: 2021.06.21`) は全件健全である（deal CSVにETH行48件を確認済み）。

**phase3レポートの記述の訂正点:**

- 「一方、IS/OOS個別ランではETHを含む全3枠を確認した」→ **誤り**。OOSもETHは0取引。
  実測（プローブC）と、phase3自身のdeal成果物 `r6p3_decomp_oos_*_deals.csv` /
  `r6p3_xm5_oos_*_deals.csv` の**全件でmagic 20260710が0行**であることの両方で確認した。
- 「FULLでは後述のETH履歴欠落があるため、FULL月利はBTC funding+BfxRevのみ」→ 正しいが、
  **同じ但し書きがOOS列にも必要**。「暗号3枠のみ構成の信頼できる両期間ゲート値はIS/OOS列で
  ある」という結論は、OOS側もETH欠落のため**成立しない**。
- 「暗号3枠のみ」の最大整数倍率1倍の判定は、OOS DD 38.7005%(2倍)がETH抜きの値なので、
  ETHを含めた再実測が必要である。

---

## 4. 実運用（フォワード）への影響評価

### 4.1 本事象そのものは起きない

判定: **バックテスト固有**。

- ライブには「テスト開始日」が存在しない。EAは常に現在時刻で `OnInit` する。
- 現在のETHUSDはブローカー側に 2016.11.08–2026.08.01 の履歴があり、D1・MA150の要件を
  9年分以上満たす。
- 従って `iMA(ETHUSD,D1,150)` が4805で失敗する条件は、通常のフォワード稼働では成立しない。

### 4.2 ただし、露呈したコード欠陥は本番EAにも存在する

判定: **低確率だが実在する潜在リスク。重大度は「無言であること」に由来する。**

`experts/MIX_EA.mq5` L407–434 は `MIX_EA_SIMVERIFY.mq5` と**同一の無検査ハンドル生成
パターン**である（本調査では読み取りのみ、変更していない）。

```
407:   // ハンドル生成・銘柄メタ
418:         S[i].hTrend=iMA(S[i].symbol,S[i].tf,200,0,MODE_SMA,PRICE_CLOSE);
427:         S[i].hTrend=iMA(S[i].symbol,S[i].tf,200,0,MODE_SMA,PRICE_CLOSE);
431:         S[i].hTrend=iMA(S[i].symbol,S[i].tf,S[i].trendPeriod,0,MODE_SMA,PRICE_CLOSE);
```

ライブで `iMA` がセカンダリ銘柄に対し `INVALID_HANDLE` を返しうる現実的な経路:

- EA起動時に当該銘柄が口座の銘柄ツリーに無い、または `SymbolSelect` が通らない
  （ブローカーの銘柄改名・銘柄整理・口座種別変更・暗号銘柄の取扱変更・メンテナンス窓での
  銘柄一覧差し替え）。
- 端末リソース枯渇によるインジケータ生成失敗。

**発生した場合の被害が重い理由:**

1. `ProcCarry` は `CopyBuffer` 失敗時に**エントリー判定の前に return する**。すなわち
   **新規だけでなく決済（ExitMA割れ退出）も止まる**。
2. その時点で建玉があれば、残る防御は**エントリー時に置いた災害SL(-45%)のみ**になる。
   通常のトレンド退出が効かないまま-45%まで放置されうる。
3. `ST_FUNDING`/`ST_BFXREV` と違い**何もPrintしない**ため、mixlogにもエキスパートログにも
   異常が残らない。週次レビューの「mixlog ⇔ MT5履歴の突合」は、**取引が発生しないこと自体は
   検出できない**ので、「今週はシグナルが無かった」と見分けがつかない。

発生確率は低いと評価する。ただし本調査でライブ環境での失敗を実際に再現したわけではなく、
コード経路からの評価である点は明記しておく。

---

## 5. 対処法の提案

### 5.1 バックテスト側（即効・EA変更不要）

**`En_ETH: true` を含む設定の `from_date` を 2016.11.09 以降にする。**

- 2016.11.08 はETHUSDのD1初バーそのもので、`OnInit` 時点では確定していない可能性があるため、
  安全側の 2016.11.09 を推奨する。実測（プローブB）で正常動作を確認済み。
- これは `docs/deploy_split_20260812.md` が既に採っている方針（「暗号は各データ開始日以降」、
  ETH_EA 2016-11-01 / BfxRev 2016-12-01 / FundingRev 2019-09-01）と整合する。
- 副作用として、暗号枠を含む構成の窓はGOLD枠の窓と厳密には一致しなくなる。合算DDを
  比較する際はこの非対称を明記する必要がある。

**要再実測:** round6_phase3 の FULL 14本と OOS 系、round6_phase2 の OOS 48本。
特に「暗号3枠のみ」の倍率判定（最大整数倍率1倍）はETH抜きの値に基づくため、
採否結論に直結する。

### 5.2 検証ハーネス側（再発防止・推奨度最高）

**run後に「有効化した各枠のmagicがdeal CSVに1行以上あるか」を自動検証し、0件なら
`SLEEVE_SILENT` として status を落とす。**

`ml/round6_phase3/run_decomposition.py` の `run_one` は deal ファイルの存在だけを見て
`status="OK"` にしている。今回の欠落が最終レポートまで通ってしまった直接の原因はここである。
枠ごとのmagic期待値を持たせるだけで、同種の無言死は今後すべて検出できる。

併せて、テスターログに `cannot load indicator` / `[4805]` が出ていないかを run ごとに
grepしてログへ残すのも安価で有効である。

### 5.3 EA側（本番EA修正・フォワード堅牢性）

本調査では**提案のみ**とし、コードは変更していない（フォワード稼働中のため）。

1. **ハンドル生成の戻り値を検査する。** `ST_FUNDING`/`ST_BFXREV` と同じく、
   `INVALID_HANDLE` なら `S[i].enabled=false` にしたうえで `Print` と `OpsWrite` を出す。
   最低限、無言でなくなる。
2. **遅延再生成にする。** `ProcCarry` 等の先頭で `hTrend==INVALID_HANDLE` なら
   その場で `iMA` を再試行する（1日1回などのレート制限付き）。これなら履歴が後から
   揃うケースで自動復旧し、バックテスト側の 5.1 の回避策すら不要になる。
3. **建玉がある枠のハンドル死は最優先で通知する。** 決済ロジックが止まることが最大の
   被害なので、`HasAny(i)` が真かつハンドル無効なら運用ログにERRORとして残す。

いずれも本番2ファイル (`MIX_EA.mq5` / `MIX_EA_OANDA.mq5`) に触れる変更なので、
`MIX_EA_SIMVERIFY.mq5` でOFF完全一致を確認したうえで別途デプロイ手順に載せること。

---

## 成果物・保護確認

- 検証スクリプト: `ml/eth_history_investigation/run_probe.py`（逐次実行・MT5多重起動防止付き）
- 設定 / ログ / deal: `ml/eth_history_investigation/{configs,logs,deals}/`
- 実測結果: `ml/eth_history_investigation/probe_results.json`
- 使用EA: `experts/MIX_EA_SIMVERIFY.mq5`（**読み取りのみ・未変更**）
- `experts/MIX_EA.mq5`, `experts/MIX_EA_OANDA.mq5`, 本番 `configs/*.yaml` は**未変更**
  （MIX_EA.mq5はハンドル生成箇所の読み取りのみ）
- mt5bt実行は常に1本のみ。各run前後に `terminal64`/`metatester64` の不在を確認
- git commit / push / PR なし。`backtest.ini` 等の認証情報は未参照

**並行作業に関する注記（監査用）:** 本調査中、別プロセス（GOLD DD低減作業・
`docs/gold_dd_reduction_20260813.md`）が `experts/MIX_EA_SIMVERIFY.mq5` を 23:05 に
更新している。ただし、
(a) 差分は59行追加・4行削除で、**ETH枠 / `ST_CARRY` / ハンドル生成 / `ProcCarry` の
いずれにも変更は無い**（`git diff` で確認済み）、
(b) プローブA/B/Cは3本とも 23:05 以降（23:06:50 / 23:08:47 / 23:10:37）に**同一バイナリで**
実行されている、
(c) プローブAの4805シグネチャは、更新前バージョンで走ったphase3の09:20:38ログと完全に
同一である。
以上より、A vs B vs C の対照は成立しており結論に影響しない。
