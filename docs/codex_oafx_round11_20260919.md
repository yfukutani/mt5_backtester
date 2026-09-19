# Codex への第11ラウンドの依頼と回答（2026-09-19・原文）

主題は「**固定ロットでの効き幅が小さいから低価値**」という従来の基準を、
複利レンズで並べ直すこと。第20報で同じ EA 変更の効き幅が固定ロットの 6.3〜155倍に
なることが実測されたため、Codex 自身が `docs/codex_oafx_inventory_20260919.md` で
各軸に付けた「±0.02pt 以下」という見込みの前提が崩れている。

依頼文は `ml/fxqualjfl/` のラウンドを設計する前に投げた。
`backtest.ini` は読まないよう明記し、Codex も冒頭で読んでいないと明記している。

**この回で Codex と結論が割れた点**（詳細は
[round11](oanda_fx_sleeve_quality_round11_20260919.md) §3）:

| 論点 | Codex | こちらの実測 |
|---|---|---|
| SCA GBPJPY の狭い分母 | 「損失を増幅している仮説は強い」 | **3窓すべてで最狭分位が最良**。フロアは一番良い部分を削る |
| PB 2枠の ATR 分母フロア | 「最優先で複利検証すべき」 | **最狭側が悪いという証拠が無い**。見込みは低いと見る |
| 分母フロア（ロットだけ抑える） | 「固定ロットでは no-op。複利の歪みだけを切り分けられる」 | **同意。本ラウンドの主軸に採った** |

---

文字化けありです。`docs/oanda_fx_sleeve_quality_confirm_20260919.md` 等には `?` への置換が、EA には一部 Shift-JIS 由来の文字化けがあります。ただし、今回の判断根拠にした SL 計算・input・検証結果の数値行は UTF-8 で読めています。`backtest.ini` は読んでいません。

## まず結論

固定ロットで小さかったという理由だけで、次を低優先度に固定するのは誤りです。

- **最優先で複利検証すべき**: PB 2枠の低 ATR 側（SL 分母が小さい側）の選別・分母下限。
- **次点**: SCA GBPJPY のレンジ幅下限。ただし現状の固定ロット結果は悪く、USDJPY の結果を横展開する根拠にはならない。
- RSI 3枠、Pair、Carry は、現在の注文時 SL の分母が変動しない／存在しないため、今回の「SL 分布を変えるとロット重みが変わる」レンズの直接対象ではありません。

全複利では枠損益をブック寄与として足し引きできません。SCA GBPJPY を risk% から外すと、枠自身は IS で改善してもブックは OOS/IS とも悪化した実測があります。[compounding attribution](docs/oanda_fx_compounding_attribution_20260919.md)。以下の「複利見込み」は、必ず同一ブック・同一サイジングで対照との差として判定すべきです。

## 9枠：SL 分母の構造

| 枠 | 初期 SL 距離と根拠 | 分布を変える既存軸 | input で可能か |
|---|---|---|---|
| PB USDJPY | `2.0 × ATR`。`atrSLmult=2.0` は [1056行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1056)、発注用 `sld=atr*atrSLmult` は [2485行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2485)。 | ATR の低値側を入口で除外、または分母に下限を置く。 | **無い**。PB 用 ATR 下限・分母クリップは改修要。 |
| PB GBPJPY | 同上。[1056行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1056)、[2485行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2485)。 | 同上。 | **無い**。改修要。 |
| RSI USDJPY | 固定 50 pips。[1135行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1135)、SL 距離計算は [2609行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2609)。 | **無い**（取引ごとに一定）。 | 無い。 |
| RSI EURUSD | 固定 25 pips。[1141-1143行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1141)。 | **無い**。 | 無い。 |
| RSI GBPUSD | 固定 50 pips。[1149-1151行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1149)。 | **無い**。 | 無い。 |
| Pair EURUSD/GBPUSD | 注文 SL=0、`trade.Buy/Sell(...,0,0,...)`。[2762-2766行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2762) | **無い**。 | 無い。 |
| Carry AUDJPY | 通常 SL を置かない設計。初期化は `disasterSL=0` [1381行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1381)、発注も SL=0。[2829-2831行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:2829) | **無い**。 | 無い。 |
| SCA USDJPY | 買いは `ask - scaRangeLow`、売りは `scaRangeHigh - bid`。[3330-3338行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3330)、[3346-3354行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3346)。レンジ採否は `MinRange/MaxRange × D1 ATR`。[3305-3308行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3305) | レンジ幅の下限・上限、`dist/entry` の下限。 | レンジ幅下限・上限は枠定義値だが親枠には個別 input 無し。`ScaFilRangeMin` は既存 input [167-168行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:167)。分母クリップは改修要。 |
| SCA GBPJPY | 同上。[3330-3354行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:3330) | 同上。 | `ScaFilMask=2` で単独適用は可能。ただし閾値は USDJPY と共有。 |

`LotRisk()` は `lot = risk額 / SL距離` を実装しています。[1974-1987行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1974)。したがって PB/SCA の「低 ATR・狭レンジ」は、採否を変えなくても大ロットになります。

## 未測定案の再棚卸し

「複利見込み」は、固定ロットの効果を単純に 6.3〜155 倍する意味ではありません。符号も含めて未測定です。

### PB USDJPY

- **H4 ATR の下限ゲート**  
  改修: 小。`ATR/価格` または「過去 N 本 ATR に対する比率」が下限未満なら新規を出さない。  
  固定ロット見込み: 小さいか不明。  
  複利見込み: **優先して測る価値あり**。低 ATR＝小分母＝過大ロットを取引ごと除外できるため、DD 側には大きく効き得る。ただし低 ATR 取引が良質なら利益も落ちる。  
  棄却との差: ADX/slope を緩める試験ではなく、既存の PB 棄却対象にない「SL 分母そのもの」の下限である。PB の ADX/slope 緩和は既に棄却済みです。[rejected 768-775行](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:768)

- **ATR 分母フロアのみ（取引は捨てない）**  
  改修: 小。`LotRisk(i, max(atr, atrFloor)*2)` として低 ATR 時のロットだけを上限化する。  
  固定ロット見込み: **0**。固定ロットでは発注集合・ロットとも不変。  
  複利見込み: 利益を削る代わりに低 ATR 事故の寄与を直接抑える。符号は未測定。これは「risk% を厳密に一定化する」案ではなく、低ボラ時だけ意図的にリスクを下げる案である。  
  棄却との差: 入口の広さではなく、risk% サイジングの非線形性に対するガード。

### PB GBPJPY

- **H4 ATR 下限ゲート**  
  改修: 小。上記と同じ。  
  固定ロット見込み: 極小・不安定。115か月で取引が少ない。  
  複利見込み: 低 ATR 日の過大ロットという機構はあるが、少数取引ゆえ採用可否を結論しにくい。**複利でも小さい可能性を強く見る。**  
  棄却との差: slope/ADX を緩める再試験ではない。

- **ATR 分母フロア**  
  改修: 小。  
  固定ロット見込み: 0。  
  複利見込み: DD 抑制候補だが、統計的な採否は難しい。取引の選別ではないため、少数性への過適合は比較的少ない。  
  棄却との差: `PbArmMaxBars` は全点両窓マイナスで棄却済みだが、この案は arm 状態でなくポジション量を変える。[round9](docs/oanda_fx_sleeve_quality_round9_20260919.md)

### RSI USDJPY

SL 分母を変える軸は**無い**。固定 50 pips なので、複利化しても「同枠内で狭い SL の取引へ重みが寄る」現象はありません。

- **R/B/D 機構別の出口設計**  
  改修: 中。機構タグに応じて TP/失効条件を変える。  
  固定ロット見込み: 小。  
  複利見込み: 初期ロットは固定分母なので、SCA/PB 型の増幅は期待しない。**複利でも小さい**。  
  棄却との差: 一律 BE・トレーリング・時間ストップは既に棄却済みだが、これは発火機構ごとの出口である。なお入口の V001 は既に採用候補であり、重ねて試さない。[rejected 754-766行](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:754)

### RSI EURUSD

SL 分母を変える軸は**無い**。固定 25 pipsです。

- **推奨する未測定収益案は無い**。  
  機構ゲートは窓間で符号が反転し、閉鎖済みです。[rejected 722-735行](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:722)  
  一律の BE／トレーリング／時間停止も既存検証で棄却済みです。[inventory](docs/codex_oafx_inventory_20260919.md)。  
  よって、案数を満たすための提案はしません。

### RSI GBPUSD

SL 分母を変える軸は**無い**。固定 50 pipsです。

- **BB 発火だけの機構別・段階利確**  
  改修: 中。BB 回帰発火に限り BB 中心線などで一部を確定し、残りは現行 TP を維持する。  
  固定ロット見込み: 小さいか悪化寄り。  
  複利見込み: 初期分母は一定のため、**複利でも小さい**。  
  棄却との差: 一律早利確ではなく BB 発火部分だけの条件付き出口。ただし RB 除外は既に棄却済みであり、事前確率は低い。[rejected 758-762行](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:758)

### Pair

SL 分母は**無い**。SL を置かず、資産連動ロットです。[1989-1997行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1989)

- **回帰後トレール**  
  改修: 中。`exitZ` 到達後、Z が再拡大したら閉じる。  
  固定ロット見込み: ±0.03pt 以下。  
  複利見込み: 分母選別がないため小さい。  
  棄却との差: entryZ/exitZ/lookback/保有上限の既測定とは別の、`exitZ` 到達後の状態遷移。

- **片脚約定の原子性ガード**  
  改修: 中。片脚失敗時に即時取消・反対売買する。  
  固定・複利見込み: 正常なテスターでは 0。実運用品質策。  
  棄却との差: `PairSkipAtStop` は収益ほぼゼロで棄却されたが、これは執行整合性の問題。[rejected 711-720行](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:711)

### Carry

SL 分母は**無い**。通常 SL がなく、資産連動ロットです。

- **収益改善の未測定案は出しません。**  
  Carry の退出 SMA は棄却済み、各窓7取引、IS の68%が窓末建玉1件で決まるため、パラメータ掃引を当面行わない結論です。[rejected 683-706行](C:/Users/f/source/repos/mt5_backtester/docs/rejected_strategies.md:683)  
  残る作業は窓末建玉・swap ドリフトの計測品質であり、収益案ではありません。

### SCA USDJPY

- **現行の `ScaFilRangeMin` を全複利で再確認する必要はない**  
  これは既測定・採用候補です。固定ロットでは +3,991/+3,393円、複利では +150,369/+525,131円という今回の基準例です。[round10](docs/oanda_fx_sleeve_quality_round10_20260919.md)

- **分母フロア（`dist = max(actualDist, floor)` をロット計算にだけ使用）**  
  改修: 小。SL/TP 価格は現状どおり、ロット計算だけをクリップする。  
  固定ロット見込み: 0。  
  複利見込み: 狭レンジ／早いブレイク時の過大ロットを直接止められるため、DD 低下の候補。ただし既存のレンジ下限と同じ方向の効果を二重に持つため、利益低下もあり得る。  
  棄却との差: 上位レンジだけを残す B1 は棄却済みだが、これは取引を落とさず、ロットだけを連続的に抑える。

- **レンジ幅の上限を個別に掃引**  
  既存 input: 親枠には無い。EA 改修は小。  
  固定ロット見込み: 小さい。  
  複利見込み: 大レンジは小ロットになるので、下限ほどの直接性はない。**複利でも小さい可能性が高い。**  
  棄却との差: B1 の「上位レンジのみ」とは逆側の、過大 SL・低重み取引を除く試験。

### SCA GBPJPY

- **`ScaFilRangeMin` の GBPJPY 単独・複利テスト**  
  既存 input: 可。`ScaFilMask=2` として単独適用できる。  
  固定ロット見込み: 既存の GBPJPY 下限試験は悪いので悪化寄り。`round8` は OOS −54,524円を記録しています。[round8](docs/oanda_fx_sleeve_quality_round8_20260919.md)  
  複利見込み: USDJPY の成功を根拠にはできない。GBPJPY は固定 FULL +115,992円から複利 FULL −1,826,948円へ反転しており、**狭い分母側が損失を増幅している仮説は強い**。したがって「レンジ下限が効く可能性」はあるが、固定結果が悪いため、成功確率は高く見積もれない。  
  棄却との差: B1 の上位25/50%だけを残す試験ではなく、`dist/entry` 下限で低分母を止める現在実装そのもの。ただし既存固定ロットの負けを覆す主張ではない。

- **GBPJPY 専用の分母フロア**  
  改修: 小。上記 SCA USDJPY と同様。  
  固定ロット見込み: 0。  
  複利見込み: こちらの方が入口下限より筋がよい。固定ロットで悪かった取引集合をそのまま保ちつつ、複利で損失を肥大化させる低分母だけを抑えられる。正負は未測定。  
  棄却との差: 既存 B1 は取引選別、これは重みのクリップ。

## (a) SCA GBPJPY のレンジ幅下限について

私は「同じ処方が効く」とは言いません。ただし、**複利で測る価値は USDJPY よりむしろ GBPJPY にあります**。

理由は二つです。

1. GBPJPY の複利反転は、`dist` が小さい取引ほど大ロットになる機構と整合します。  
2. しかし、固定ロットの GBPJPY 下限試験自体が悪いので、「狭いレンジが悪い」だけでなく、「下限で落とすと日内再エントリーの経路が変わり、遅い不利な entry を生む」可能性があります。`ScaFilRangeMin` は初回で止めても価格が離れると同日中に解除され得るゲートです。[1925-1928行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1925)

共有閾値は問題です。

- `ScaFilMask=2` なら GBPJPY だけを測れるので、**単独検証の障害ではありません**。
- ただし USDJPY と GBPJPY を同時適用する場合、両者に別の最適閾値を与えられません。`ScaFilRangeMin` は一つだけです。[167-168行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:167)
- 採用候補になった段階で、`ScaFilRangeMin_UJ/GJ` と各枠 mask を分離する小改修が必要です。共有値のまま「2枠に効く一点」を探すのは、USDJPY の既採用値へ GBPJPY を無理に合わせる設計になります。

## (b) PB の ATR 倍 SL は SCA と同型か

**数学的には同型です。** PB は `SL距離 = 2 × ATR`、かつ PB 2枠は risk% です。[1056行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1056)、[1064行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1064)、[1093行](C:/Users/f/source/repos/mt5_backtester/experts/MIX_EA_SIMVERIFY.mq5:1093)。ゆえに ATR が低いほど大ロットです。

ただし SCA と完全に同一ではありません。

- SCA の分母は「確定レンジ端から実際の entry まで」の距離で、日内の再ブレイクにより変わる。
- PB の分母は H4 ATR の指標値であり、entry 価格との距離には依存しない。

PB に入れるなら、SCA の「レンジ幅下限」に相当する正しい形は二段です。

1. **選別版**: `ATR / price` または `ATR / 過去N本ATR` の下限を入口条件にする。低ボラ環境の取引そのものを除外する。  
2. **サイジング版**: `SL計算用ATR = max(actualATR, ATR_floor)` としてロットだけをクリップする。取引は残しつつ、低 ATR 時の過大ロットを止める。

私は先に **2 を測る**べきと考えます。固定ロットでは完全に no-op で、複利の歪みだけを切り分けられるからです。その後、DD が改善し収益を削り過ぎるなら 1 を少数点で比較する順が、取引品質とサイジング効果を混同しません。
