# 後処理シミュレーション裏取りと新データ40案（2026-08-12）

## 結論

**Round 4のdeal後処理は、実EAの高速スクリーニング代替としては信頼できない。**
F15-17は実注文の最小lot丸めにより効果がゼロ、F14-01は見送りによって将来の取引列と
履歴フィードバック自体が変わり、後処理の増益から実測では大幅減益へ符号反転した。

## タスク②: 実装

- 本番の `MIX_EA.mq5` / `MIX_EA_OANDA.mq5` は変更せず、検証専用
  `experts/MIX_EA_SIMVERIFY.mq5` を作成した。
- inputは既定OFF。モード0=OFF、1=RSI群、2=PB群、lookback、risk scaleを指定できる。
- entry直前に `HistorySelect/HistoryDealsTotal/HistoryDealGet*` で、対象magicごとの直近N件の
  `DEAL_ENTRY_OUT/OUT_BY` の profit+swap+commissionだけを読む。未来dealは読まない。
- Round 4実装の厳密な挙動に合わせ、「群全体の最新8件」ではなく
  **各magicの最新8件を連結した平均**とした（Round 4の `hist_values()` の実装）。
- PBのOFF照合では、個別EA各10万円口座の複利sizingを統合EA内のmagic別実現損益で再現した。
- position ID、deal type、volume、price、SLも検証ログへ追加した。
- 指定MetaEditorでコンパイルし、**0 errors / 0 warnings**を確認した。

期間は2016-06-21～2026-06-20。公式baselineはRound 4と同じ15config・初期資金150万円。
影響群だけを検証EAでON/OFF測定し、他群はRound 4保存dealを使用した。PBはOFF実測との差分を
公式baselineへ適用するmatched-delta方式（raw hybridも保存）でポートフォリオ化した。

### OFF同一性

| 群 | Round 4保存deal | SIMVERIFY OFF | 差 | ポートフォリオ換算差 |
|---|---:|---:|---:|---:|
| RSI3 | 58,380 | 58,562 | +182 (+0.31%) | +0.016% |
| PB4 | 307,280 | 302,424 | -4,856 (-1.58%) | -0.427% |

両方とも利益数%以内で、検証EAのOFF照合として許容した。PB差の主因は複数銘柄を単一テスターで
駆動する時刻差、終了時決済、swap/commissionの再評価差で、取引数はOFFで269件と一致した。

### 後処理値 vs 実バックテスト

| ケース | 純利益 | 最大DD% | baseline差（利益 / DD） | 後処理値との差 |
|---|---:|---:|---:|---:|
| baseline | 1,137,149 | 2.3745% | — | — |
| F15-17 後処理 | 1,139,755.5 | 2.3573% | +2,606.5 / -0.0172pt | — |
| **F15-17 実測** | **1,137,149** | **2.3745%** | **0 / 0pt** | **利益 -2,606.5 (-0.2287%)、DD +0.0172pt** |
| F14-01 後処理 | 1,154,391 | 2.2534% | +17,242 / -0.1211pt | — |
| **F14-01 実測（matched-delta）** | **833,560** | **2.2504%** | **-303,589 / -0.1240pt** | **利益 -320,831 (-27.79%)、DD -0.0030pt** |

F14 raw hybridはOFF 1,132,293 / DD 2.3793%、ON 828,704 / DD 2.2553%。
matched-deltaはそのON-OFF差を公式baselineへ加えた値である。

### 原因と判定

1. **F15-17:** RSI3は通常0.01 lotで、XMの最小volume/stepも0.01。0.5倍の0.005は
   `Clamp()` で0.01へ丸め戻るため、ON/OFFの909取引と損益が完全一致した。
   後処理だけが架空の0.005 lotを許していた。
2. **F14-01:** 後処理はbaselineの将来entry/exit列を固定したまま損益を0倍にする。
   実EAはentryを見送るので対応exitも発生せず、確定deal履歴が更新されない。
   最初の負平均後にブレーキ解除材料がほぼ生まれず、実測は269取引から4取引へ減少した。
3. 後処理の「scaled profitを次の履歴へ入れる」処理も、実際の未発注・lot丸め後の履歴とは一致しない。

したがって、純利益差が小さく見えるF15も「改善を再現した」のではなく**機構が一度も実効化しなかった**。
F14は利益の符号まで逆であり、総合判定は明確に**信頼不可**である。

影響範囲はRound 4のB分類960案全体。特にF15-17の唯一の厳格改善、F14-01を含む15 tradeoff、
scale=0を含む全gate、最小lotスリーブへの0.25/0.5/0.75/0.9縮小は採用根拠を失う。
「改善なし」の案も固定されたbaseline取引列上の結果にすぎず、実EAでの非改善を証明しない。
今後は後処理を探索ヒントに限定し、候補判定はvolume stepを含む検証EAで行う。

## タスク①: (C)40案の実現可能性

Round 4の各family内10案はvariant番号以外の定義が同一だったため、調査では具体的な10段階へ展開した。
費用は既存XMヒストリと公開endpointを対象とし、有料feed・API key・stooq・Yahoo range=maxには依存しない。

### C01 entry-side spread feed（10案）

| 案 | gate | 無料・認証不要 | テスター再現 | 規模 | 判定 |
|---|---|---|---|---|---|
| C01-01～10 | entry spreadの過去percentile 50,55,…,95超を見送る | brokerのreal tickは追加料金/API key不要。ただし既存MT5接続は必要 | 「real ticks」ならbid/ask可 | 中（tick exporter＋15枠再測定、2～4日） | **着手可、未着手** |

Python MetaTrader5 APIで2020-01-02 USDJPYを実査したが取得0件で、端末の通常履歴APIから10年tickを
一括prescreenできなかった。一方、Strategy Testerのreal-tick DBは利用可能。
したがってC01-01～10は検証専用EAでentry spreadを書き出す前処理が必要で、今回の
「EA前にPython t検定」には直ちに入れない。データ捏造やOHLC spread代用はしなかった。

### C02 true concurrent exposure（10案）

| 案 | gate候補 | データ | テスター再現 | 規模 | 判定 |
|---|---|---|---|---|---|
| C02-01～10 | entry時の同方向通貨重複scoreの50,55,…,95 percentile | `DEAL_POSITION_ID/type/volume/SL`、外部データ不要 | 完全可 | 中（実装・全tickログ・Python、実施済み） | **着手・事前検証完了** |

### C03 macro event blackout（10案）

| 案 | blackout例 | 無料・認証不要データ | テスター再現 | 規模 | 判定 |
|---|---|---|---|---|---|
| C03-01～05 | High impactの前後15/30/60/120/240分 | 2016～26、全対象通貨、発表予定時刻、impact、改訂履歴を満たす無認証feedなし | CSV化できれば可 | 大（1～3週＋保守） | **着手不可** |
| C03-06～10 | High+Medium、surprise/forecast/previous条件付き | 同上。point-in-time forecast/revisionが特に不足 | ライブCalendar APIの直接依存は再現性不足 | 大～特大 | **着手不可** |

Forex Factoryの無認証JSONは取得成功したが2026-08-09週だけで、10年履歴ではない。
FRED APIのrelease datesはAPI keyなしでHTTP 400、無認証series CSVも発表時刻・当時forecastを
与えない。MT5 Economic Calendarはライブ取得面としては有用だが、テスターへ固定した
point-in-timeスナップショットなしでは再現不能。よって代理データでの検定は行わない。

### C04 intrabar execution optimizer（10案）

| 案 | 比較 | 無料・認証不要 | テスター再現 | 規模 | 判定 |
|---|---|---|---|---|---|
| C04-01～04 | market vs limit（0.1/0.25/0.5 ATR retrace、TTL） | L1 bid/ask real tickはbroker DBで可 | L1約定はreal ticksで可 | 大（専用EA、1～2週） | **縮退版のみ可** |
| C04-05～07 | stop entry offset/TTL/slippage比較 | L1 real tickで可 | real ticksで可 | 大 | **縮退版のみ可** |
| C04-08～10 | DOM imbalance/queue/depthを使うlimit/stop/market | 過去L2板の無料無認証10年feedなし | `MarketBookGet` はライブsnapshotで履歴再生不可 | 特大 | **原案は着手不可** |

原案は「全tick板情報」を要求するため、L1だけの縮退版を同じ案として検定するのは不適切。
履歴DOMがない以上、C04-01～10の原案は今回着手しない。

## C02 Python事前検証

検証専用EAをevery-tickで2016～26実行し、3,846 positionのposition ID・方向・volume・SLを取得。
entry直前に開いていたpositionから通貨方向vectorを作り、新規vectorとの同方向重複scoreを計算した。
各percentile超過群と非超過群のposition損益をWelch t検定した（先読みなし）。

| 案 | percentile / score閾値 | high n / low n | high平均 / low平均 | t | p | 判定 |
|---|---:|---:|---:|---:|---:|---|
| C02-01 | 50% / 0 | 1,810 / 2,036 | 360.7 / 920.2 | -0.703 | 0.482 | 棄却 |
| C02-02～07 | 55～80% / 1 | 730 / 3,116 | 1,042.4 / 566.6 | +0.477 | 0.633 | 全棄却 |
| C02-08～09 | 85～90% / 2 | 278 / 3,568 | 2,404.5 / 520.8 | +0.802 | 0.423 | 全棄却 |
| C02-10 | 95% / 3 | 105 / 3,741 | 208.9 / 669.5 | -1.008 | 0.313 | 棄却 |

最大でも |t|=1.008で、規約の |t|<2.0 により**C02全10案をEA gate実装前に棄却**した。
なおdirection重複の単純仮説の検定であり、通貨ごとのJPY換算delta、SL risk換算、netting効果を
別仮説として探索する場合は新しい事前登録が必要。

## 成果物と参照

- `experts/MIX_EA_SIMVERIFY.mq5`
- `ml/simverify/configs/*.yaml`（本番configsは未変更）
- `ml/simverify/c02_exposure_prescreen.py`
- `ml/simverify/c02_prescreen_results.csv`
- `ml/simverify/c02_position_features.csv`
- `ml/simverify/simverify_portfolio_summary.csv`
- `ml/simverify/summarize_simverify.py`

外部仕様確認（2026-08-12取得）:

- MQL5 CopyTicksRange: https://www.mql5.com/en/docs/series/copyticksrange
- MQL5 deal properties（position ID等）: https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties
- MQL5 MarketBookGet: https://www.mql5.com/en/docs/marketinformation/marketbookget
- MQL5 Economic Calendar: https://www.mql5.com/en/docs/calendar
- Forex Factory current-week JSON: https://nfs.faireconomy.media/ff_calendar_thisweek.json

本番EA2ファイル、本番 `configs/*.yaml`、認証情報は変更していない。commit/push/PRも行っていない。
