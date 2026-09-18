# Codex による「まだ測っていない軸」の棚卸し（2026-09-19・原文）

第5ラウンド（`ml/fxqual5`）までの実測を全部渡し、**新案ではなく網羅性**を求めた回。
条件は「『まだ測っていない』の根拠を必ず書く（推測禁止・`docs/` のファイル名か EA の行番号）」
「入口と退出を分けて列挙」「楽観を書かない」「**『無い』が正しいなら『無い』と書く**」。

## この回でこちらの誤りが1件正された

私は「**RSI 3枠の退出は固定SL/TP ひとつだけで保有中の管理が無い＝未測定の軸ではないか**」
と問うた。**これは誤りだった。** Codex が出典付きで否定し、**3件すべて実在を確認した**:

| 施策 | 対象 | 結果 | 出典 |
|---|---|---|---|
| ブレークイーブン移動（BE 20-25pips） | RSI 3チャート・10年 | 累計 −24,273 → **−36,107** | [research_log.md](research_log.md) v2.7 |
| トレーリングストップ（30/20pips） | 同上 | **−40,029** | [research_log.md](research_log.md) v2.8 |
| 時間ストップ（最大保有バー） | RSI USDJPY H4・10年 | **全水準悪化**（最良18バーで利益 −40%） | [profit_giveback_proposals_20260803.md](profit_giveback_proposals_20260803.md) |
| 利益トレール（`UseProfitTrail`・FX限定掃引） | FX枠 | **採用水準に達しない** | [profit_trail_20260805.md](profit_trail_20260805.md) §7.4 |

> **プロジェクトの教訓（`new_ea_strategies.md`）:「損益管理の後付け（BE/トレーリング）は
> 勝率を上げても RR・総利益を下げた実績あり → 最初から TP/SL 設計に織り込む」**

また **`守りのオーバーレイ3形態` は枠別の RSI 出口試験ではない**（PB の入口ゲートと
口座全体スロットルが中心）という指摘も正しく、`rejected_strategies.md` を読み直して確認した。

> [!warning] **これは走行中の `ml/fxqual7`（SCA の建値ストップ）の事前確率を下げる。**
> 「建値ストップはこの枠で未測定」は正しいが、**同じ機構は RSI 3枠と Carry で既に棄却されている。**
> `profit_trail` の口座全体トレールは SCA では「ほぼ不活性」だったので `fxqual7` は
> 別物の試験ではあるが、**このプロジェクトの事前分布は明確に負けである。**
> 測る前にこれを書いておく。

---
文字化けあり：`oanda_fx_sleeve_quality_round2_20260918.md` など一部は文字コード不整合で読みにくく、根拠は主に正常に読める EA・`rejected_strategies.md`・関連検証記録で照合しました。

9枠は EA の初期化で確認した PB×2 / RSI×3 / Pair / Carry / SCA×2 です。[MIX_EA_SIMVERIFY.mq5](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1022)

| 枠 | 未測定の軸 | なぜ未測定と言えるか（根拠） | 既存 input で表現できるか | 事前の見込み |
|---|---|---|---|---|
| PB USDJPY | 入口：`armed` の寿命（`PbArmMaxBars_UJ`） | `armedBuy/Sell` は set/clear されるだけで時刻・バー齢を保存していない。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2378) LOO でも IS で170バーと slope に次ぐ律速で、未実装と明記。[round3](C:/Users/f/source/repos/mt5_backtester/docs/oanda_fx_sleeve_quality_round3_20260919.md:138) | いいえ | **±0.014pt以下**。現在の OOS は4往復なので、正の一点が出ても採用根拠にならない。 |
| PB GBPJPY | 入口：`armed` の寿命（`PbArmMaxBars_GJ`） | 同上。`armed` は古い押し目でも trend が壊れるまで残る実装で、既存の slope/ADX 掃引とは別軸。第3ラウンド時点で未実装・未測定候補だった。[round2](C:/Users/f/source/repos/mt5_backtester/docs/oanda_fx_sleeve_quality_round2_20260918.md:253) | いいえ | **−0.01〜+0.02pt程度以下**。取引数が極小で、局所最適を作りやすい。 |
| RSI USDJPY | 退出：発火機構別の利確・損切り（R→RSI中立、B→BB中心、D→パターン目標） | 現行は R/B/D が OR で入口に同居し、共通の固定 SL/TP だけを使う。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2550) [初期値](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1101) 機構別退出は提案のみで、結果記録は見当たらない。[sleeve_quality](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_sleeve_quality_20260918.md:86) | いいえ | **±0.02pt以下**。V001 の全体効き幅自体が OOS +0.008pt。 |
| RSI EURUSD | 退出：機構別目標、または枠別の保有期限 | 固定 SL25/TP105 とドテン以外の保有中管理は MIX に無い。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1108) EURUSD の機構別 TP/SL は未実装提案に留まる。[round3 proposal](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_round3_20260918.md:88) | いいえ | **期待薄**。入口機構が IS/OOS で反転しているため、退出を最適化しても同じ不安定性を増幅しやすい。 |
| RSI GBPUSD | 退出：BB系の部分利確、または機構別目標・保有期限 | 現行は SL50/TP110 の共通固定出口。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1116) BB単独の部分利確は未実装提案のみ。[round7](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_round7_20260919.md:39) | いいえ | **±0.02pt以下**。BB単独が両窓プラスでも、早利確は TP 側の大きな勝ちを削る公算が大きい。 |
| Pair EURUSD/GBPUSD | 入口：乖離が縮小へ転じた後だけ入る `PairRequireZTurning`。退出：`exitZ` 到達後の再拡大を切る回帰後トレール。執行：片脚だけ約定した際の原子性ガード。 | 現行の退出は `exitZ` / `stopZ` / 保有上限だけ。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2703) `entryZ`、`exitZ`、lookback、240/480時間上限は既測定なので除外し、上記は未実装・未測定候補として残る。[round7](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_round7_20260919.md:75) | すべていいえ | 収益は **±0.03pt以下**。原子性ガードは収益案ではなく、正常テスターなら **0pt** の品質対策。 |
| Carry AUDJPY | 入口：ヒステリシス幅、Trend MA期間、クールダウン。執行：D1 シグナルの発注時刻をずらす設計。退出ではなく評価：窓末建玉の別評価。 | 現行値は `hystMult=0.75`、MA200、cd10 のハードコード相当。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1128) ただし各窓7取引、IS の68%が窓末1建玉で、既に「パラメータ掃引は当面やらない」と結論済み。[rejected](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:704) | いいえ。`CarryHoldBars` はあるが閉鎖済み、退出SMAも閉鎖済み。 | **測る価値は実質ない**。収益改善の期待は0、やるなら窓末評価の計測品質だけ。 |
| SCA USDJPY | 入口：ブレイク終値の overshoot 上限。退出：TP の R倍率、TP未達・時間経過後の段階的 SL 縮小。 | 現行はレンジ端＋bufferで入って、SL は反対端、TP は固定2R、22時まで保有。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3258) BE は `fxqual7` 実行中、Rev gate は `fxqual8` 実行中のため「未測定」ではなく**保留中**。overshoot／時間経過型SLは未実装候補。[round7](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_round7_20260919.md:165) | いいえ（BEのみ既存 input） | **±0.03pt以下、主にマイナス予想**。USDJPY は元の絶対利益が薄い。 |
| SCA GBPJPY | 入口：overshoot 上限。退出：TP の R倍率、TP未達・時間経過後の段階的 SL 縮小。 | 同上。時間帯・締切・強制決済・買い限定は既に閉鎖。現行コードには段階SLもovershootも無い。[EA](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3230) | いいえ（BEのみ既存 input） | **−0.03〜+0.03pt程度**。22時強制決済が利益源なので、SLを早く寄せる案は特に悪化寄り。 |

補足です。

- RSI 3枠について、「保有中の管理が何も無い」は**現行 MIX のコード状態としては正しい**です。固定 SL/TP と反対シグナルのドテンだけです。
- ただし「建値・トレーリング・時間ストップが未測定」は**誤り**です。RSI単体 EA では建値移動とトレーリングが10年検証で棄却済み。[research_log.md](C:/Users/f/source/repos/mt5_backtester/docs/research_log.md:441) RSI USDJPY の時間ストップも全水準悪化でした。[profit_giveback_proposals.md](C:/Users/f/source/repos/mt5_backtester/docs/profit_giveback_proposals_20260803.md:96) さらに `UseProfitTrail` の FX限定掃引も採用水準に達していません。[profit_trail.md](C:/Users/f/source/repos/mt5_backtester/docs/profit_trail_20260805.md:202)  
  したがって残るなら「一般的な守り」ではなく、上表の**機構別退出**のような狭い別軸だけです。

- `守りのオーバーレイ3形態` は枠別の RSI 出口試験ではありません。PB の入口ゲートと口座全体スロットルが中心で、RSI の BE/Trail 棄却の根拠には使えません。[rejected_strategies.md](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:399)

- `PbArmMaxBars` は、**測る資格はあります**。LOO で実際に律速であり、slope・ADXの再試験ではないからです。ただし「採用価値が高い」ではありません。PB USDJPY の少数性を踏まえると、これは次の収益探索というより、PB の状態機械に残った最後の入口棚卸しです。

結論として、この主題を続ける価値は「月利を上げる探索」としては、ほぼ残っていません。今日の最大の成果はご指摘どおり方法論です。

残っている合理的な作業は、`fxqual6`〜`8` の確定を待つこと、その後に必要なら `PbArmMaxBars` と Pair の `Z turning` を各少数点で反証することまでです。Carry は凍結、RSI の汎用的な守りは再訪不要、SCA は BE/Rev gate の結果を先に確定、が妥当です。
