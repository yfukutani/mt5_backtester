# 破綻前の2倍到達確率

既存の固定基準x1約定に全枠比例サイジングを仮定する、有限期間のブロック・ブートストラップ。
目標はP(2倍) >= 85%。DDを制約にしない。MT5測定・EA変更は不要。
Python標準ライブラリのみ（Python 3.6以上）。作成・更新するファイルはこのディレクトリ内だけ。

```powershell
py ml/double1/extract.py
py ml/double1/simulate.py --sensitivity --engine dotnet
py ml/double1/report.py
py -m unittest discover -s ml/double1 -p "test_*.py"
```

Windows標準の.NET Framework C#コンパイラを使える場合、`--engine dotnet`で高速化する。
同じ乱数・ブロック算法を使う補助コードを`_engine.exe`にコンパイルする。
他の環境では`--engine python`（既定）で同じ計算ができるが、全感度計算には時間がかかる。
この環境の`py`はPython 3.6。生成コード・データ・文書の改行はLF。

既定条件だけなら`py ml/double1/simulate.py --engine dotnet`。
個別指定例:

```powershell
py ml/double1/simulate.py --book fx --window IS OOS FULL --k 1 2 3 4 --block-lengths 10 20 --ruin-fracs 0.1 0.2 0.3 --n-paths 10000 --max-horizon 3 --engine dotnet
```

指定したbook/windowの結果CSVは実行ごとに置き換える。全感度結果を復元するには上記の`--sensitivity`を実行する。
`extract.py --seed 20260911`でseedを設定し、`sources.json`に記録する。
再抽出は出典・実行記録を再生成するため、その後はsimulate/reportも再実行する。

入力はfxmult1/results.csvのmult=1、およびgoldcomp1/results.csvのG001・mult=1。
複数候補は黙って選ばずエラー。MAGICS・窓・入金はmeasure.pyをASTで読み、実行しない。
GOLDブックはGOLD系だけでなくMAGICSに含まれる暗号3枠も含む。GOLD ISはデータなし。
profit非ゼロの対象magicの1約定を1取引とする。分割決済は集約せず、同時刻はCSV元行順。
損益はprofitのみで、手数料・swap・通貨換算列は加えない。FXの既存netとは一致しない。
元run、元行、SHA-256、magic、抽出件数、合計損益、月数、seed、実行設定をsources.jsonに保存する。

連続ブロックの開始点を0〜N-Lから等確率で復元抽出する非循環方式。末尾と先頭は連結しない。
L=1は独立仮定。L>Nはエラー。端点付近の取引が中央より抽出されにくい移動ブロック方式の性質がある。
経路別xorshift32（13/17/5）を使用し、初期状態は`(seed+(path+1)*2654435769) mod 2^32`（0は1）。
棄却法で整数抽出の剰余バイアスを除去する。同一Lではk・破綻閾値間で共通の抽出列を使う。
最大取引数はfloor(N*max_horizon)。どちらかの閾値に初めて触れた取引で停止し、
最終資産には閾値を超えた実際の資産を保存する。負資産は破綻として停止し、ゼロへ丸めない。
中央値の対象経路がない場合、CSVは空欄。

月数はmeasure.pyの公称期間（IS 60、OOS 55、FULL 115）を使用する。
平均日数は`月数*(365.25/12)/N`、到達月数は`到達取引数*月数/N`。
最初と最後の決済日だけで期間を短縮しない。暦の季節性や無取引期間の分布は再現しない。

この確率は過去の優位が将来も続く仮定の上でのみ意味を持つ。
85%は将来が過去に似ている条件付きの値であり、将来を保証しない。
ブロックは連敗の塊をある程度保存するが、レジーム変化は再現できない。
最小ロット0.01による比例縮小制約を無視するため、実際の破綻確率はここで出る値より高い。
破綻閾値は運用上の打ち切り水準で、証拠金の強制ロスカットの正確な再現ではない。
決済損益だけで含み損や建玉の重なりを再現しない。全枠の理想的比例サイジングであり、
現在のEAの固定ロット枠がそのままequity連動するという意味ではない。
最大3履歴ぶんでのP(2倍)であり、未決着を無視した無期限の確率ではない。
