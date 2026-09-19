# Codex による第10ラウンドの案出し（2026-09-19・原文）

**何を聞いたか:** 確認ラウンド（`ml/fxqualcfm`）で「同じ EA 変更が複利では効き幅 11.9〜14.7倍」
と実測されたことを渡し、**前回の棚卸し（`codex_oafx_inventory_20260919.md`）で
「±0.02pt 以下だから価値が低い」と付けた見込みを、複利前提で付け直してほしい**と依頼した。
あわせて (a) 既出・未測定軸の順位づけ直し (b) 新しい軸 を求めた。

**制約として渡したもの:** `rejected_strategies.md` との重複禁止／BE・トレーリング・時間ストップ・
利益トレールの汎用的な守りは棄却済み／`ml/fxqual9` は走行予定なので触らない／
新 input は既定値で完全不変／楽観を書かない／「無い」が正しいなら「無い」と書く。
`backtest.ini` は読まないよう明示した（Codex も冒頭で読んでいないと明記している）。

> [!note] **この回の要点は「(b) 新軸は無い」と明言されたこと。**
> こちらが出した2方向（**最大DD区間だけ枠を軽くする** / **枠どうしの相反ポジションの扱い**）は
> **どちらも未測定ではなく、既に棄却済み**だと出典付きで否定された。
> 一方 **(a) の価値判断の見直しには応じ、順位を付け直している。**

---
# 第10ラウンド案：再較正後の結論

`backtest.ini` は読んでいません。

確認ラウンドの実測から、固定ロットでの小差を理由に棄却する基準は撤回すべきです。ただし、複利で増幅されるのは「各取引のR期待値を上げる」改善であり、単なる取引除外・早利確・一般的な守りは格上げしません。

以下の複利見込みは、確認ラウンドの **6.3〜14.7倍**を機械的に掛けた値ではなく、取引数減・勝ちの裾切り・標本数を控除した保守的な OOS 幾何月利の期待レンジです。

## (a) 既出・未測定軸の再順位付け

| 順位 | 枠 | 機構 | 既存 input で表現 | 未測定の根拠 | 固定ロット見込み | 複利見込み | 複利での性質 | 反証条件 |
|---:|---|---|---|---|---:|---:|---|---|
| 1 | RSI USDJPY | R/B/D 組合せ別の SL/TP。D を含む群・RBD などにだけ異なる初期Rを与える。入口は変えない。`ProcRSI()` の共通 `sld`/`tpd` を機構コード別に分岐。 | なし。`RsiMechExitMode_UJ=0`、`RsiMechSLPips_UJ[1..7]=0`、`RsiMechTPPips_UJ[1..7]=0`。全て 0 なら現行 `slPips/tpPips` をそのまま使う。 | 共通 SL/TP は EA [2609–2610](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2609)。機構別の入口損益だけが測定済みで、出口別は未測定：`oanda_fx_sleeve_quality_round2_20260918.md:103-127`。 | 0〜+0.035pt | 0〜+0.25pt | **増幅候補。** 同じ発火群の損失を小さくし、または期待Rを上げられた場合だけ長期複利に乗る。 | OOS/IS のどちらかでブック幾何月利が対照以下、または DD が上がる。単一コードだけの改善も棄却。 |
| 2 | SCA USDJPY / GBPJPY | ブレイク足終値の overshoot 上限。レンジ端から大きく飛んだ足で、反対端SLのまま追い掛ける注文を禁止する。 | なし。`ScaMaxEntryOvershootATR_UJ/GJ=0`。0 は無効、`>0` 時だけ `abs(close1-range端) <= X×ATR` を追加。 | 現行は `close1 > high + buffer`／`< low - buffer` だけで、上限がない：EA [3322–3354](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3322)。未測定候補として明記：`codex_oafx_inventory_20260919.md` の SCA 行、`oanda_fx_sleeve_quality_round2_20260918.md:251`。 | 0〜+0.025pt | 0〜+0.15pt | **条件付きで増幅。** 悪い遅延ブレイクだけを除ければRを上げるが、単なる取引数減なら増幅しない。 | 両窓で枠の平均Rが上がらない、または減った取引の損益が対照以上。GBPJPY/UJを混ぜず個別判定。 |
| 3 | Pair EURUSD/GBPUSD | `exitZ` へ一直線に回帰した後ではなく、回帰が反転して再拡大した時だけ退出する Z 経路トレール。価格トレールではない。 | なし。`PairExitReexpandZ=0`。0 は現行の即時 `exitZ` 決済、`>0` で最良Zからの再拡大幅を使う。 | 現行の出口は `exitZ`／`stopZ`／保有上限のみ：EA [2768–2794](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2768)。未測定候補として列挙：`codex_oafx_inventory_20260919.md` の Pair 行。 | 0〜+0.010pt | 0〜+0.07pt | **弱い増幅候補。** 平均回帰の取り分を増やせた時だけ増幅するが、OOS 30脚・IS 56脚で標本が薄い。 | OOS/IS のどちらかで純益または DD が悪化。入口・`entryZ` は同時に触らない。 |
| 4 | SCA USDJPY / GBPJPY | TP の R倍率を枠別に掃引。時間強制決済は不変。 | 主枠にはなし。`ScaRROverride_UJ/GJ=0`。0 は現行の `rr=2.0`。 | TP は `rr×dist`：EA [3330–3338](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3330)、主枠の `rr=2.0` は EA [1244, 1265](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1244)。未測定候補：`codex_oafx_inventory_20260919.md`。 | 0〜+0.015pt | 0〜+0.10pt | **増幅は弱い。** TP到達が少なく、利益源の大半が22時強制決済であるため、R改善の母数が小さい。 | TP到達率・平均Rが改善せず、または両窓のブック幾何月利が対照以下。 |
| 5 | RSI GBPUSD | BB系発火だけの部分利確。残りは現行TPまで維持。 | なし。`RsiBBPartialAtR_GU=0` と `RsiBBPartialFrac_GU=0`。両方 0 なら注文変更なし。 | GBPUSD は共通 `SL50/TP110`：EA [1144–1151](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1144)。BB単独部分利確は未測定候補：`codex_oafx_inventory_20260919.md`、`oanda_fx_sleeve_quality_round7_20260919.md:39`。 | -0.010〜+0.005pt | -0.06〜+0.03pt | **原則として増幅しない。** 勝ち取引の尾を削る比率が高く、複利ではむしろ不利になりやすい。 | 平均勝ちRが落ち、両窓で幾何月利が対照以下なら即棄却。これは優先して走らせる案ではない。 |
| 6 | SCA USDJPY / GBPJPY | TP未達で時間経過後にSLを段階縮小。 | なし。ただし新設すべきではない。 | `ScaBETriggerR/ScaBELockR` は既に SCA退出を測る機構：EA [2311–2346](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2311)。第7ラウンドで SCA の後付け一般退出を閉鎖：`oanda_fx_sleeve_quality_round7_20260919.md:119-121`。RSI時間ストップも棄却済み：`codex_oafx_inventory_20260919.md`。 | -0.03pt以下 | 負、または 0pt | **増幅しない／負に増幅。** 勝ちの途中の押し戻しを切る一般的な守りであり、禁止された再訪に当たる。 | 実施しない。第10ラウンド候補から除外。 |

RSI EURUSD の機構別SL/TPは、同じ表の第1案と同じ実装に含められますが、優先度は最低です。入口組合せの符号が OOS/IS で反転しているため（`oanda_fx_sleeve_quality_round2_20260918.md:125-127`）、出口最適化で不安定性を増やす可能性が高いです。見込みは固定・複利とも **0pt近傍** とします。

## (b) 新軸について

結論として、ここで「新規の実行変更」として追加できる有望案はありません。依頼に挙がった二つの方向は、未測定ではなく、既に反証または棄却されています。

| 枠 | 機構 | 既存 input で表現 | 未測定の根拠／実際の既測定根拠 | 固定ロット見込み | 複利見込み | 結論・反証条件 |
|---|---|---|---|---:|---:|---|
| 全枠 | 最大DD区間だけ枠を軽くする／止める | なし | **既測定・不採用。** `oanda_fx_risk_sizing_20260915.md:708-712` は Carry と SCA GBPJPY をDD主因として減量する案を否定。`rejected_strategies.md:501-509` も最大DDが単一イベントに支配され、枠を抜く対象が窓ごとに入れ替わると記録。 | 負〜0pt | 負〜0pt | 出さない。事後的なDD期間選別は「早い損失を避ける質改善」ではなく、未知の次DDに再現できない停止規則。 |
| RSI EURUSD / RSI GBPUSD / Pair | 同時・相反通貨ポジションの相殺、抑制、ネット化 | なし | **既測定・棄却。** 月次相関では36組中、閾値超過は PB USDJPY×Pair のみ：`oanda_fx_risk_sizing_20260915.md:691-706`。反対建玉の証拠金相殺は全期間0.277%、OOS 0.819%に過ぎない：`rejected_strategies.md:600-628`。 | 0pt | 0pt | 出さない。相関抑制ではなく、収益機会を減らすだけになる根拠が既にある。 |
| 全枠（診断のみ） | 次回から、最大DDの開始・底・回復時刻、各magicの確定／含み寄与、同時通貨デルタをログ化する | 新 input `DDTraceFileName=""`。空文字なら一切書かず完全不変。 | 現行 `OnTester()` はDDの統計値のみを出力し、時刻・magic寄与を出していない：EA [3407–3446](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3407)。ポジション保有判定もmagic単位：EA [1593–1606](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1593)。 | 0pt | 0pt | これは改善案ではなく、将来「DD区間だけ」を主張するための最低限の計測。ログを取っても上記棄却済みの停止・相殺案を復活させる根拠にはしない。 |

したがって、第10ラウンドとして実際に測る順序は、**RSI USDJPY の発火組合せ別SL/TP → SCA overshoot → PairのZ経路退出 → SCA RR** が妥当です。GBPUSD部分利確とSCA段階SLは、再較正後でも優先順位を上げません。
