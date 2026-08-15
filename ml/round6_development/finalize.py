from pathlib import Path
import pandas as pd

REPO=Path(__file__).resolve().parents[2];ROOT=REPO/'ml'/'round6_development'
g=pd.read_csv(ROOT/'gold_results.csv');o=pd.read_csv(ROOT/'gold_oos_results.csv')
b=g.iloc[0]; cand=g[(g['family']=='gold_exit') & (g.net>b.net) & (g.pf>b.pf) & (g.dd<=b.dd)].copy()
cand['dd_reduction_pt']=b.dd-cand.dd
# XM portfolio reference from deploy_split: DD32.63, monthly4.54. A single GOLD-leg IS test cannot
# establish the portfolio delta, so capacity columns intentionally remain unverified.
cand['xm_dd_after']='未検証';cand['max_integer_multiple']='未算出';cand['monthly_at_dd30_pct']='未算出'
cand.to_csv(ROOT/'gold_candidates.csv',index=False)
families=pd.DataFrame([
 ['A/B_gold_cause','価格ショック後の新規抑制',20,18,0],
 ['A/B_gold_exit','ATR逆行幅での危機退出',20,20,5],
],columns=['family','mechanism','is_tests','survive_is','oos_attempts'])
tab=cand[['id','net','pf','dd','trades','dd_reduction_pt','xm_dd_after','max_integer_multiple','monthly_at_dd30_pct']].to_markdown(index=False,floatfmt='.2f')
rep=f'''# Round 6 大規模開発（2026-08-12）

## 結論

資金配分78案を除外し、最優先のGOLD 2ファミリー40案を検証専用EAへ実装して実MT5バックテストした。ISではGOLD exit 4案が純利益・PF上昇かつDD低下。最良は逆行0.25 ATR退出で、純利益158,012→185,960、PF 2.0294→3.2099、DD 19.1097→15.0600%（-4.0497pt）。ただし既知のGOLD OOSデータ制約により5候補すべてOOSは結果生成不能で、両期間ゲートを通った厳格改善は0件。したがってXM口座DD32.63%への寄与、可能倍率、月利は未確定であり採用候補とはしない。

## 1. 着手ファミリーと実装

{families.to_markdown(index=False)}

`MIX_EA_SIMVERIFY.mq5`（検証専用）へ既定OFFのinputを追加した。

- `R6GoldMode=1`: GOLD PB/SCAの直近確定足レンジをATR正規化し、閾値超過後の新規注文をEA内部で見送る。
- `R6GoldMode=2`: GOLDポジションの建値から確定足終値までの逆行幅をATR正規化し、閾値超過時にEA内部で成行退出する。
- `R6GoldMode=0`: 追加分岐は即returnし、既存発注処理を変更しない。
- 実効volumeは既存の`Clamp()`を維持。本機構はlot縮小を行わないため0.01丸め戻り問題はない。

指定MetaEditor（XM Trading MT5）でコンパイルし、`0 errors, 0 warnings`を確認した。

## 2. OFF同一性

既存SIMVERIFY全15枠・2016-2026・every_tickを再実行し、既存保存値と一致した。

| 指標 | OFF再実測 |
|---|---:|
| 純利益 | 5,822,343 |
| PF | 2.8526 |
| DD | 22.8384% |
| 取引数 | 3,846 |

なお統合検証EAは個別口座構成とサイジングが異なるため、この値を本番XM/OANDA成績には使用していない。

## 3. ファミリー別結果

| ファミリー | IS検証 | IS純利益>0 | IS内厳格改善 | OOS試行 | 両期間厳格改善 |
|---|---:|---:|---:|---:|---:|
| gold_cause | 20 | 15 | 0 | 0 | 0 |
| gold_exit | 20 | 20 | 4 | 5 | 0 |
| 合計 | 40 | 35 | 4 | 5 | 0 |

GOLD OOSは指示された既知制約どおり全5件を「検証不能」と記録し、それ以上の反復を打ち切った。

## 4. 厳格改善候補

両期間ゲートを通過した候補は0件。

IS限定の有望点（未採用）:

{tab}

## 5. DD低下候補と倍率・月利

上表のDD低下はGOLD PB単独ISの値であり、XM5枠口座DDへ線形転記できない。OOS不能かつXM5枠を同一EA実測する確認前なので、DD30%内倍率と月利は意図的に「未算出」とした。`floor(30/DD)`の機械計算を単独枠から行うと誤ったレバレッジ判断になるためである。

## 6. トレードオフ

CAUSE_L1_T0.75はPF 2.8433、DD 16.7667%へ改善した一方、純利益が95,502へ低下。CAUSE_L3_T1.25/1.5もDDを8.9781/10.4492%へ下げたが純利益が124,112/139,484へ低下した。いずれもOOS不能のため参考記録のみ。

## 7. 未着手

- crypto_cause / crypto_exit: GOLDの両期間ゲートがデータ制約で閉じ、まず最優先ファミリーの判定可能性を確定するため未着手。
- vol_target: 全枠で実効整数lotログと個別EA改造が必要。今回の40点実測後は未着手。
- risk_budget / equity_brake / recovery_state: 口座共有状態を持つ統合検証EAと口座別サイジング同一性の構築が必要。
- decorrelated_time / loss_cluster_gate / tail_hedge: 新規シグナルまたはpoint-in-time共有状態とデータ監査が必要。

残る対象は830案。時間切れであり、未検証案を検証済みとして扱っていない。

## 8. 月利5%への距離

現状はOANDA月2.30%、XM月4.54%、合算約2.4%。今回のGOLD exitはIS単独で強い改善を示したが、OOSおよびXM5枠DDが未確定なので上積みは0%として評価する。従って実証済み到達値は約2.4%のまま、目標5%まで約2.6pt。次の判断材料は、OOS可能な暗号3枠の危機退出を先に実装し、XM5枠の実バックテスト合算でDD30%未満を確認できるかである。

## 成果物・保護確認

- EA: `experts/MIX_EA_SIMVERIFY.mq5`（検証専用）
- configs/logs: `ml/round6_development/configs/`, `logs/`
- 数値: `gold_results.csv`, `gold_oos_results.csv`, `gold_candidates.csv`
- 本番EA2ファイル、本番configs、認証設定は無変更。commit/push/PRなし。
'''
(REPO/'docs'/'round6_development_20260812.md').write_text(rep,encoding='utf-8')
print(len(g),len(cand),o.status.value_counts().to_dict())
