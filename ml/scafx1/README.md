# SCA FX 第2セッション掃引

スクリプト作成のみ。MT5測定は実行していない。

`generate_proposals.py` は `proposals.csv`（71案）と `baseline_proposals.csv`（基準1案）を生成する。
具体的な掃引水準を優先したため、目安の56案を超える。USDJPYは36案、GBPJPYは35案。
U/Gの0は中心点、1はレンジ窓、2は締切、3はRR、4はレンジ幅、5はバッファ/Boost。
内訳は U=1/15/5/5/5/5、G=1/15/5/5/5/4。中心点はX001とX037。
重複除去は3件（各通貨の13-15時、GBPJPYのBuffer=0）。出力内重複は0件。

## 将来、測定が別途指示された場合

以下は今回実行していない。リポジトリルートで、BASE 2runと掃引142runを同じドライバで測る。
BASEは新枠両方OFFであり、新枠ONの中心点とは異なる。

```powershell
py -c "from ml.scafx1 import measure as m; m.PROPOSALS = m.ROOT / 'baseline_proposals.csv'; m.main()"
py ml/scafx1/measure.py
py ml/scafx1/adjudicate.py
py ml/scafx1/robustness.py
```

基準と掃引は同じ `results.csv` に蓄積する。EA・構成を揃えた同一測定ラウンドを使う。
`measure.py` は指定箇所以外を流用元から変更していないため、元の保護機構と出力処理を維持する。
配布ファイルの改行はLF。ドライバ実行時のログ・CSV等の改行処理も流用元のままである。

## 集計の解釈

`adjudication.csv` は全案、`adjudication_passed.csv` は両窓の新枠純益が正の案を最弱窓純益降順で出す。
`family_summary.csv` は両窓評価済み案の新枠純益中央値、評価数、両窓正の件数を出す。
`adjudication.txt` に同じ内容と欠測理由を出す。取引数は決済position数であり、ドライバのIN約定数とは定義が異なる。
IS 60取引以上を参考表示するが、黒字判定を採用確定とは扱わない。

損益はdealの `profit` のみ。円建てDDは時刻順（同時刻はログ順）の累積損益のピークからの最大落ち込み。
含み損を含むequity DDではない。純益倍率とDD倍率は両方OFFの実測BASEを分母とする参考値で、合否・順位には使わない。
親枠の純益・取引数とBASEとの差分も表示する。BASE欠測時は倍率・差分を空欄にし、新枠純益の判定は続行する。
ファミリー中央値には片窓欠測案を含めず、評価数を明記する。

`robustness.csv` / `robustness.txt` は有効な新枠別に、各窓の最良年をそれぞれ除外して両窓黒字かを示す。
流用元と同様に年は建玉開始年に帰属し、部分決済損益をposition単位に合算する。

## measure.py: BASE / MAGICS

```json
{
  "BASE": {
    "En_PB_USDJPY": true,
    "En_PB_GBPJPY": true,
    "En_PB_AUDJPY": false,
    "En_PB_GOLD": true,
    "En_RSI_USDJPY": true,
    "En_RSI_EURUSD": true,
    "En_RSI_GBPUSD": true,
    "En_PAIR": true,
    "En_CARRY": true,
    "En_VBO": false,
    "En_ETH": false,
    "En_BTC_FUND": false,
    "En_BFXREV": false,
    "En_SCA_GOLD": true,
    "En_SCA_USDJPY": true,
    "En_SCA_GBPJPY": true,
    "SimVerifyMode": 0,
    "R6GoldMode": 0,
    "R6CryptoMode": 0,
    "GoldDDMode": 0,
    "GoldLabMode": 0,
    "GoldLabMode2": 0,
    "GoldPBHoldBars": 64,
    "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2,
    "GoldHourPBStart1": 0,
    "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32,
    "GoldHourPBStart2": 12,
    "GoldHourPBEnd2": 16,
    "GszMode": 0,
    "GszSleeveMask": 0,
    "Sca2Enable": true,
    "Sca2RangeStart": 13,
    "Sca2RangeEnd": 15,
    "Sca2TradeEnd": 20,
    "Sca2ForceClose": 23,
    "Sca2MinRange": 0.4,
    "Sca2MaxRange": 1.0,
    "Sca2Buffer": 0.0,
    "Sca2RR": 1.7,
    "Sca2SkipFriday": true,
    "Sca2RevBoost": true,
    "Sca2BoostMult": 2.0,
    "Sca2Lot": 0.01,
    "Sca3Enable": false,
    "FundUseWebRequest": false,
    "BfxUseWebRequest": false,
    "Sca4Enable": false,
    "Sca5Enable": false,
    "Sca6Enable": false,
    "Pb2Enable": false
  }
}
```

```json
{
  "MAGICS": {
    "20261000": "sca_uj",
    "20261001": "sca_gj",
    "20261006": "uj2",
    "20261007": "gj2",
    "20261002": "sca1",
    "20261003": "sca2",
    "20260640": "pb"
  }
}
```

