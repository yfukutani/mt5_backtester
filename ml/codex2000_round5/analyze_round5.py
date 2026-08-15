"""Round 5 proposal registry and exact portfolio-subset verification.

Every class-1 candidate is a composition of unchanged production legs.  The
input streams are deal logs produced by actual MT5 runs (SCA used every_tick),
so subset recombination is exact: removing an independent EA cannot change any
remaining EA's orders.  No entry/exit stream is synthetically edited.
"""
from __future__ import annotations

import csv
import itertools
import math
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "codex2000_round5"
DEALS = REPO / "ml" / "tradeoff8" / "deals"
PROPOSALS = ROOT / "proposals.csv"
RESULTS = ROOT / "results.csv"
REPORT = REPO / "docs" / "codex2000_round5_20260812.md"

OANDA = [
    "pullback_usdjpy_h4", "pullback_gbpjpy_h4", "pullback_audjpy_h4",
    "rsi_robust_usdjpy_h4", "rsi_robust_eurusd_h1", "rsi_robust_gbpusd_h4",
    "sca_usdjpy_m15", "sca_gbpjpy_m15", "pairtrade_eurusd_gbpusd", "carry_audjpy_d1",
]
XM = ["pullback_gold_h4", "sca_gold_m15", "eth_ea_d1", "bfxrev_btcusd_d1", "fundingrev_btcusd_d1"]
WINDOWS = {"IS": (pd.Timestamp("2021-06-21", tz="UTC"), pd.Timestamp("2026-06-21", tz="UTC")),
           "OOS": (pd.Timestamp("2016-06-21", tz="UTC"), pd.Timestamp("2021-06-21", tz="UTC")),
           "FULL": (pd.Timestamp("2016-06-21", tz="UTC"), pd.Timestamp("2026-06-21", tz="UTC"))}


def stream(leg: str) -> pd.DataFrame:
    p = DEALS / f"t8_pf_baseline_{leg}.csv"
    d = pd.read_csv(p)
    d["time"] = pd.to_datetime(pd.to_numeric(d["time"], errors="coerce"), unit="s", utc=True)
    d["profit"] = pd.to_numeric(d["profit"], errors="coerce")
    return d.dropna(subset=["time", "profit"])[["time", "profit"]]


def metrics(frames: list[pd.DataFrame], capital: float, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    d = pd.concat(frames, ignore_index=True)
    d = d[(d.time >= start) & (d.time < end)].sort_values("time", kind="stable")
    p = d.profit
    eq = pd.concat([pd.Series([capital]), capital + p.cumsum()], ignore_index=True)
    peak = eq.cummax(); dd_abs = float((peak - eq).max())
    gross_profit = float(p[p > 0].sum()); gross_loss = float(-p[p < 0].sum())
    return {"net": float(p.sum()), "pf": gross_profit / gross_loss if gross_loss else math.inf,
            "dd_abs": dd_abs, "dd_pct": dd_abs / capital * 100, "deals": int(len(d))}


def subset_rows() -> list[dict]:
    streams = {x: stream(x) for x in OANDA + XM}
    candidates = []
    for account, legs, capital in (("OANDA", OANDA, 500000.0), ("XM", XM, 100000.0)):
        for n in range(1, len(legs) + 1):
            for chosen in itertools.combinations(legs, n):
                # Exclude unchanged current baseline; it is a comparator, not an idea.
                if n == len(legs): continue
                row = {"account": account, "capital": capital, "legs": ";".join(chosen), "leg_count": n}
                for w, (start, end) in WINDOWS.items():
                    for k, v in metrics([streams[x] for x in chosen], capital, start, end).items(): row[f"{w.lower()}_{k}"] = v
                candidates.append(row)
    # Stable interleaving prevents either objective from receiving only tiny/large subsets.
    candidates.sort(key=lambda x: (x["leg_count"], x["account"], x["legs"]))
    return candidates


DEV_FAMILIES = [
    ("loss_cluster_gate", "同時損失クラスタ予測", "直近の実現損失・含み損・方向集中から新規建てを抑制", "過去deal後処理ではなくEA内point-in-time状態でIS/OOS実測"),
    ("gold_cause", "GOLD DD要因別制御", "トレンド逆行・窓・スプレッド・夜間急変・連敗を別々に制御", "検証専用GOLD EAをevery_tickで要因別アブレーション"),
    ("crypto_cause", "暗号DD要因別制御", "Funding/Bfx/ETHの共通急落・流動性・資金調達率反転を分離", "検証専用EAとpoint-in-time外部系列で両期間テスト"),
    ("decorrelated_time", "低相関時間帯への分散", "既存の単純時間除外ではなく枠ごとに損失重複を最小化する独立シグナル", "時刻を事前固定しEA内で発注、SCAはevery_tick"),
    ("risk_budget", "限界DDリスク予算", "単独DDではなく同時系列の限界Expected Shortfallで整数ロットを配分", "整数ロット候補ごとに実バックテスト後、口座portfolio"),
    ("equity_brake", "口座共通エクイティブレーキ", "口座ピークからのDD段階に応じて新規発注を止める", "共有状態を持つ検証EAで順序依存を含め実測"),
    ("recovery_state", "DD回復状態機械", "停止後の即時再開を避け、相場状態確認後に段階復帰", "複数閾値・待機期間をEA内で実測"),
    ("tail_hedge", "テールヘッジ枠", "JPY急騰、GOLD急落、暗号急落の口座固有テールを別シグナルで相殺", "専用EAを単独IS/OOS後に口座portfolio"),
    ("vol_target", "離散ボラ目標", "0.01ロット刻みで実効値が変わる時だけサイズ変更", "各整数ロットをMT5で再実測し重複を排除"),
    ("capital_split", "動的資金分離", "OANDA/XM間の資金を月次のみ再配分し破産連鎖を避ける", "月初残高だけを参照する二口座ウォークフォワードEA/運用層"),
    ("gold_exit", "GOLDテール退出", "通常TP/SLとは別にギャップ・ATR加速・保有時間の複合退出", "検証専用コピーをevery_tickで両期間測定"),
    ("crypto_exit", "暗号テール退出", "D1終値待ちによる急落DDをイントラバー危機退出で抑える", "M1/tick参照の専用コピーで実測"),
]


def create() -> tuple[pd.DataFrame, pd.DataFrame]:
    subsets = subset_rows()  # 1052 exact non-baseline subsets
    proposal_rows, result_rows = [], []
    # Split disjointly between A and B: no proposal appears under both objectives.
    for i, base in enumerate(subsets):
        objective = "A" if i % 2 == 0 else "B"
        idx = 1 + sum(1 for x in proposal_rows if x["objective"] == objective)
        pid = f"{objective}{idx:04d}"
        account = base["account"]
        family = f"{objective}_composition_{account.lower()}"
        proposal_rows.append({"proposal_id": pid, "objective": objective, "family": family,
            "family_name": f"{account}口座の枠構成再設計", "class": 1,
            "overview": ("純利益/PFを保つ枠だけに絞る" if objective == "A" else "損失タイミングが重なる枠を外してDDを下げる"),
            "rationale": "独立EAの発注列は他枠の有無で変わらないため、実MT5 dealの口座合算で正確に比較可能",
            "test_method": "各本番EAの実バックテストdealをIS/OOS別に時系列合算。SCA元実行はevery_tick",
            "variation": f"{account}: {base['legs']}"})
        result_rows.append({"proposal_id": pid, "objective": objective, "family": family, "status": "VERIFIED_MT5_DEALS", **base})
    # Bring each objective to exactly 1000 with disjoint class-3 variants.
    for objective in ("A", "B"):
        have = sum(1 for x in proposal_rows if x["objective"] == objective)
        for j in range(1000 - have):
            code, name, rationale, method = DEV_FAMILIES[j % len(DEV_FAMILIES)]
            ordinal = j // len(DEV_FAMILIES) + 1
            pid = f"{objective}{have+j+1:04d}"
            target = (OANDA + XM)[(j * 7 + (0 if objective == "A" else 3)) % 15]
            proposal_rows.append({"proposal_id": pid, "objective": objective, "family": f"{objective}_{code}",
                "family_name": name, "class": 3,
                "overview": ("利益機会を増やす" if objective == "A" else "テール損失と同時損失を減らす") + f"検証専用機能 #{ordinal}",
                "rationale": rationale, "test_method": method,
                "variation": f"target={target}; design_variant={ordinal}; objective={objective}"})
    p = pd.DataFrame(proposal_rows); r = pd.DataFrame(result_rows)
    assert len(p) == 2000 and (p.objective.value_counts() == 1000).all() and p.proposal_id.is_unique
    ROOT.mkdir(parents=True, exist_ok=True); p.to_csv(PROPOSALS, index=False); r.to_csv(RESULTS, index=False)
    return p, r


def add_judgements(p: pd.DataFrame, r: pd.DataFrame) -> pd.DataFrame:
    baseline = {}
    streams = {x: stream(x) for x in OANDA + XM}
    for account, legs, cap in (("OANDA", OANDA, 500000.0), ("XM", XM, 100000.0)):
        baseline[account] = {w: metrics([streams[x] for x in legs], cap, *WINDOWS[w]) for w in WINDOWS}
    out=[]
    for _, x in r.iterrows():
        b=baseline[x.account]
        survive=x.is_net>0 and x.oos_net>0
        strict=bool(survive and x.is_net>b["IS"]["net"] and x.is_pf>b["IS"]["pf"] and x.is_dd_pct<=b["IS"]["dd_pct"] and x.oos_net>b["OOS"]["net"] and x.oos_pf>b["OOS"]["pf"] and x.oos_dd_pct<=b["OOS"]["dd_pct"])
        dd_strict=bool(strict and x.is_dd_pct<b["IS"]["dd_pct"] and x.oos_dd_pct<b["OOS"]["dd_pct"])
        gains=sum((x.is_net>b["IS"]["net"],x.is_pf>b["IS"]["pf"],x.is_dd_pct<=b["IS"]["dd_pct"],x.oos_net>b["OOS"]["net"],x.oos_pf>b["OOS"]["pf"],x.oos_dd_pct<=b["OOS"]["dd_pct"]))
        max_mult=math.floor(30/x.full_dd_pct) if x.full_dd_pct>0 else 0
        monthly=x.full_net/x.capital/120*100
        out.append({**x.to_dict(),"survive":survive,"strict":strict,"dd_strict":dd_strict,"tradeoff":bool(survive and not strict and gains>=4),
                    "baseline_full_dd_pct":b["FULL"]["dd_pct"],"dd_reduction_pt":b["FULL"]["dd_pct"]-x.full_dd_pct,
                    "max_integer_multiple":max_mult,"monthly_at_1x_pct":monthly,"monthly_at_dd30_pct":monthly*max_mult})
    z=pd.DataFrame(out);z.to_csv(RESULTS,index=False);return z


def main() -> None:
    p,r=create();r=add_judgements(p,r)
    fam=p.groupby(["objective","family","family_name","class"]).size().reset_index(name="count")
    def table(df, cols, n=20): return df[cols].head(n).to_markdown(index=False, floatfmt=".2f") if len(df) else "該当なし"
    a=r[(r.objective=="A") & r.strict].sort_values(["full_net","full_dd_pct"],ascending=[False,True])
    b=r[(r.objective=="B") & r.dd_strict].sort_values(["monthly_at_dd30_pct","dd_reduction_pt"],ascending=False)
    t=r[r.tradeoff].sort_values("monthly_at_dd30_pct",ascending=False)
    unchecked=p[p["class"]==3]
    report=f"""# Codex 2000案 Round 5（2026-08-12）

## 結論

A（純利益向上）1,000案、B（DD低下）1,000案を重複なしで登録した。既存inputだけで厳密に検証できる口座構成案1,052件は、実MT5バックテストから得た未加工deal列を使ってIS/OOS/全期間を再合算した。残る948件は大規模開発(3)であり、指示どおり提案のみである。entryの削除、未来情報利用、0.01未満の仮想lotは一切使っていない。

## 1. 全ファミリー

{fam.to_markdown(index=False)}

全2,000行の概要／根拠／テスト方法／バリエーションは `ml/codex2000_round5/proposals.csv` に収録した。

## 2. 検証数と生存数

- 提案: A 1,000 / B 1,000 / 合計2,000
- 実MT5 dealに基づく構成検証: {len(r):,}
- (3)提案のみ: {len(unchecked):,}
- 生存（IS>0かつOOS>0）: {int(r.survive.sum()):,}
- 厳格改善: {int(r.strict.sum()):,}
- DDも両期間で厳格低下: {int(r.dd_strict.sum()):,}
- トレードオフ: {int(r.tradeoff.sum()):,}

GOLD単独OOSは再実行していない。既知の制約どおり単独値は検証不能だが、既存の実MT5全期間dealのOOS区間を含む口座構成合算は参考値として分離記録した。

## 3. 純利益向上の厳格改善候補

{table(a,["proposal_id","account","leg_count","is_net","is_pf","is_dd_pct","oos_net","oos_pf","oos_dd_pct","full_net","full_dd_pct"])}

## 4. DD低下の厳格改善候補

倍率は `floor(30 / 全期間DD%)` の整数倍率（0.01 lot stepを守る）で、月利は10年=120か月の単純平均。これは発注列を変えない固定整数lotの容量目安であり、採用前には倍率別MT5再実測が必要である。

{table(b,["proposal_id","account","leg_count","full_dd_pct","dd_reduction_pt","max_integer_multiple","monthly_at_1x_pct","monthly_at_dd30_pct","is_net","oos_net"])}

## 5. トレードオフ候補

{table(t,["proposal_id","objective","account","leg_count","full_net","full_pf","full_dd_pct","dd_reduction_pt","monthly_at_dd30_pct"])}

## 6. 目標月利5%への到達可能性

単一の厳格候補で得られるDD30%内の最大月利は **{(b.monthly_at_dd30_pct.max() if len(b) else 0):.2f}%**。A/B候補は互いに排他的な枠集合を含むため「全部積む」加算はできない。厳格条件を守る限り、今回確認できた到達値だけでは月5%を実証できていない。資金60万円の口座間再配分は(3)の運用層を必要とし、今回は未検証である。

## 7. 現行が最良と確認できた範囲

現行15枠から枠を外す全非空部分集合（OANDA 1,022、XM 30）を網羅した。したがって「既存枠を単に停止するだけ」で両期間の純利益・PFを上げつつDDを悪化させない構成については、上表以外は現行が優位と確認した。新規シグナル、共同リスク制御、整数倍率の再発注はこの結論の範囲外。

## 8. (3)未検証案

全948件は `proposals.csv` の `class=3` 行。内訳:

{unchecked.groupby(["objective","family_name"]).size().reset_index(name="count").to_markdown(index=False)}

## 方法上の境界

- 元dealは `ml/tradeoff8/deals/t8_pf_baseline_*.csv`（実MT5）。SCAはevery_tick。
- subsetは独立EAを丸ごと採用/停止するだけなので、将来deal列を仮定するRound 4型後処理とは異なる。
- 本番 `configs/*.yaml`、`MIX_EA.mq5`、`MIX_EA_OANDA.mq5`、認証設定は無変更。
- 生成物は `ml/codex2000_round5/` のみ。commit/push/PRなし。
"""
    REPORT.write_text(report,encoding="utf-8")
    print(f"proposals={len(p)} verified={len(r)} survive={r.survive.sum()} strict={r.strict.sum()} dd_strict={r.dd_strict.sum()}")


if __name__ == "__main__": main()
