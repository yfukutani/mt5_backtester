# Codex の第12ラウンド案（2026-09-19・原文）

> 依頼: 9枠それぞれの「まだ測っていない枠の質の改良案」。**複利レンズ**での事前見込みを要求し、
> 既に閉じた軸の一覧（PB の ADX/slope/armed寿命/分母フロア・RSI の BE/トレール/時間ストップ・
> Pair の entryZ/exitZ/Z転換/回帰ベータ・Carry 凍結・SCA の時間帯/買い限定/リバーサル条件/
> 建値ストップ/レンジ幅下限）を明示して再提案を禁じた。「無いなら無いと書く」ことを明記。
> 依頼文には backtest.ini を読まない指示を入れてある。**文字化けは無かった。**

## この回で Codex がこちらを1つ正した

こちらは依頼文で「同じ EA 変更を全複利で測り直すと効き幅が **12〜121倍**になる」と書いた。
Codex はこれを**予測の道具として使うことを拒否した**——

> 固定ロットの小幅結果を複利へ機械的に「12〜121倍」する根拠はありません
> （増幅は変更した軸・取引時点・equity 経路で異なるためです）。

**これは正しい。** 12〜121倍は**測った後の観測値**であって、**係数ではない。**
第22報で「±0.02pt 以下だから価値が低い」という足切りが崩れたのは事実だが、
**その逆（小さい実測を倍率で引き伸ばして期待値を作る）も同じ誤りである。**
以降、事前見込みは **0.00pt 中心・定量幅なし**として扱う。

## Codex の結論

**第12ラウンドで測る価値が残るのは、指定した3軸だけ。**
**PB 2枠・Pair・Carry には、閉じた軸を踏まずに追加できる案は無い。**

---

結論として、第12ラウンドで測る価値が残るのは、ご指定の3軸だけです。PB 2枠・Pair・Carryには、閉じた軸を踏まずに追加する案はありません。

複利では固定ロット時の `±0.02pt` 足切りは使えません。ただし、固定ロットでの効き幅を 12〜121 倍して予測することもできません。増幅率は変更時点の equity 経路と risk% の SL 距離に依存するためです。以下の「事前見込み」は、根拠のない倍率換算をせず、**0.00pt中心・定量幅は無い**とします。

| 枠 | 第12ラウンド案 | (a) 機構 | (b) input / 改修 | (c) 未測定の根拠 | (d) 全複利 OOS 幾何月利の事前見込み |
|---|---|---|---|---|---|
| SCA USDJPY | TP の R 倍率 | `TP = entry + rr × 初期SL距離` の `rr` を 2.0 から変える。SL と `LotRisk` の分母は固定のまま、勝率と実現RRだけを変える。 | **EA改修要**。親枠の `x.rr=2.0` はハードコードで input がない。 | 親枠の `rr=2.0` は [EA:1277–1283](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1277)。発注TPは `S[i].rr*dist` [EA:3390](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3390)。棚卸しも未測定の「TP の R 倍率」と明記 [inventory:45](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:45)。 | **0.00pt中心、定量幅は無い。** TP 到達が少なく、強制決済が損益の中心という記録があるため、TPを遠くする方向に正の事前期待は置かない。 |
| SCA GBPJPY | 同上 | USDJPY と同じ。ただしGBPJPYには RevBoost があるので、まず両枠共通RRではなく枠別に測る。 | **EA改修要**。 | 親枠の `x.rr=2.0` は [EA:1298–1304](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1298)、TP計算は [EA:3406](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3406)。未測定として記録済み [inventory:46](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:46)。 | **0.00pt中心、定量幅は無い。** IS の枠別損益が負でも複利ブック寄与を否定できないため、枠別純益から符号予測もしない。 |
| SCA USDJPY | 入口 overshoot 上限 | ブレイク足終値とレンジ端の乖離を ATR 正規化し、行き過ぎた初動を見送る。実装は `max(|close1-edge|, |entry-edge|)/ATR <= cap` が安全。後者も見ることで、終値後のスプレッド拡大を逃さない。 | **EA改修要**。新規 `ScaMaxEntryOvershootATR_UJ` と枠maskが必要。 | 現行入口は「下限のみ」`close1 > high + buffer` / `< low - buffer` [EA:3381](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3381), [EA:3397](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3397)。上限inputは存在せず、未測定と明記 [inventory:45](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:45)。 | **0.00pt中心、定量幅は無い。** 選別は取引数を減らすだけにもなり得る。SL分母を変える `ScaFilRangeMin` の成功を、この軸の先験的プラス根拠にはしない。 |
| SCA GBPJPY | 同上 | 同じ。USDJPYと同じ閾値を強制せず、枠別input。 | **EA改修要**。 | 現行は同じく下限ブレイク判定のみ [EA:3397–3406](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3397)。棚卸しで未測定 [inventory:46](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:46)。 | **0.00pt中心、定量幅は無い。** GBPJPYは複利で equity 経路への影響が大きいので、固定ロットの小幅想定を拡大換算しない。 |
| RSI USDJPY | 発火機構別 TP/SL | R・B・D（併発は RB 等）ごとに退出設計を持たせる。第1段階は**SL固定・TPのみ機構別**にし、risk% の分母を不変にして純粋な退出効果を測る。第2段階でSLも別軸として分離する。 | **EA改修要**。機構タグは既に作れるが、保有中の機構別退出処理と枠別パラメータはない。 | 現行は R/B/D を OR で入口にし [EA:2650–2660](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2650)、共通 `sld/tpd` で発注 [EA:2663–2703](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2663)。未測定と明記 [inventory:40](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:40)。 | **0.00pt中心、定量幅は無い。** RSI USDJPY は機構ゲート自体の寄与が小さかった記録があるため、退出だけに正の数値期待を置かない。 |
| RSI EURUSD | 同上 | R/B（D無効）の発火別TP、SLは後段へ分離。 | **EA改修要**。 | 固定 SL25/TP105 [EA:1175–1177](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1175)、機構別退出は未実装・未測定 [inventory:41](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:41)。 | **0.00pt中心、定量幅は無い。** 入口機構のIS/OOS反転が既知なので、exit 最適化に正の事前期待を載せない。 |
| RSI GBPUSD | 同上 | R/B の発火別TP、SLは後段へ分離。部分利確は同時に入れず、まず全量TPだけを測る。 | **EA改修要**。 | 共通固定 SL50/TP110 [EA:1183–1185](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1183)。BB系部分利確・機構別退出は未測定 [inventory:42](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:42)。 | **0.00pt中心、定量幅は無い。** 早利確は大勝ちを削るリスクがあるため、プラス見込みは置かない。 |
| PB USDJPY | 無い | `PbArmMaxBars` は既に両窓マイナスで閉鎖。ADX・slope・SL分母フロアも閉鎖済み。 | — | 閉鎖条件は依頼文および `oanda_fx_sleeve_quality_round11_20260919.md`。 | **無い。** |
| PB GBPJPY | 無い | 同上。 | — | 同上。 | **無い。** |
| Pair | 無い | Z turning、回帰β、entry/exit/lookback/保有上限は閉鎖済み。原子性ガードは品質対策で収益案ではない。 | — | 棚卸しも原子性ガードの見込みを正常テスターでは 0pt としている [inventory:43](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:43)。 | **無い。** |
| Carry | 無い | 凍結を維持。 | — | 各窓7取引、ISの大半が窓末建玉で、掃引停止と明記 [inventory:44](C:/Users/f/source/repos/mt5_backtester/docs/codex_oafx_inventory_20260919.md:44)。 | **無い。** |

実施順は、(1) SCA の枠別RR、(2) SCA の枠別overshoot、(3) RSIの**TPのみ**機構別退出、です。RSIで最初から機構別SLまで変えると、退出品質と risk% のSL分母変更が混ざるため、今回の問いに対する因果が読めなくなります。

SCA TP-R倍率は特に、`ScaFilRangeMin` と独立です。前者はTP距離だけを変え、後者は `|entry-SL|/entry` を選別してリスク量・取引集合を変えます。[EA:1959–1961](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1959)
