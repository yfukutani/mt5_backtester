"""Generate the immutable 1,000-proposal OANDA DD registry."""
from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
FIELDS = [
    "id", "family", "overview", "rationale", "test_method", "variation",
    "implementation_class", "status", "parameter_json", "unverified_reason",
]


def product(**values: Iterable[Any]) -> list[dict[str, Any]]:
    keys = list(values)
    return [dict(zip(keys, combination)) for combination in itertools.product(*(values[key] for key in keys))]


EXECUTABLE = [
    {
        "family": "sca_gj_range_quality", "mode": 1,
        "overview": "SCA GBPJPYのレンジ幅とブレイクbufferを同時調整",
        "rationale": "FULL最大DDの81.48%を占める主因枠の偽ブレイクを入口で抑える",
        "test": "Min/Max Range÷ATRdとbufferをEAの発注前に適用して実バックテスト",
        "grid": product(OafxGJMinRange=[.35, .40, .45, .50, .55],
                        OafxGJMaxRange=[.70, .80, .90, 1.00],
                        OafxGJBuffer=[.02, .04, .06, .08, .10]),
    },
    {
        "family": "sca_gj_boost_rr_direction", "mode": 2,
        "overview": "SCA GBPJPYの実効boost lot・RR・BUY限定を同時調整",
        "rationale": "0.06 lot群の総損失-457,350円とIS SELL純損失-4,264円を直接狙う",
        "test": "boostを1～5の有効lot段階へ変更し、RRとBUY限定をEA内で実測",
        "grid": product(OafxGJBoostMult=[1, 2, 3, 4, 5],
                        OafxGJRR=[1.2, 1.4, 1.6, 1.8, 2.1, 2.2, 2.4, 2.6, 2.8, 3.0],
                        OafxGJDirection=[0, 1]),
    },
    {
        "family": "sca_gj_break_confirmation", "mode": 3,
        "overview": "SCA GBPJPYに複数終値確認・実体・伸び過ぎ上限を追加",
        "rationale": "6時間未満の失敗群がFULL -207,830円、IS -97,932円",
        "test": "連続終値、本体ATR比、レンジ端からの乖離を発注時点だけで判定",
        "grid": product(OafxGJConfirmBars=[2, 3, 4, 5, 6],
                        OafxGJBodyMinATR=[0, .05, .10, .15, .20],
                        OafxGJExtensionMaxATR=[.10, .20, .30, .40]),
    },
    {
        "family": "sca_gj_retest", "mode": 4,
        "overview": "SCA GBPJPYをブレイク後のレンジ端再接触確認型へ変更",
        "rationale": "短時間でSLに戻る偽ブレイクを価格の再接触で選別する",
        "test": "直近確定足の高安だけを用いるpoint-in-timeリテスト条件で実測",
        "grid": product(OafxGJRetestLookback=[1, 2, 3, 4, 5],
                        OafxGJRetestToleranceATR=[0, .05, .10, .15, .20],
                        OafxGJExtensionMaxATR=[.10, .20, .30, .40]),
    },
    {
        "family": "sca_gj_drift_regime", "mode": 5,
        "overview": "SCA GBPJPYのアジアレンジ内drift強度と方向整合を選別",
        "rationale": "現行0.06 lotはdrift逆方向だけを増幅し損失振幅も増やしている",
        "test": "当日レンジ確定時のdrift÷rangeだけで方向許可を決め実測",
        "grid": product(OafxGJDriftMinRatio=[0, .10, .20, .30, .40],
                        OafxGJDriftMaxRatio=[.50, .70, .90, 1.10, 1.30],
                        OafxGJDriftPolicy=[0, 1, 2, 3]),
    },
    {
        "family": "sca_gj_session_shape", "mode": 6,
        "overview": "SCA GBPJPYのレンジ開始・終了・発注窓長を再定義",
        "rationale": "時刻丸ごとの除外ではなくレンジ形成とブレイク観測窓を変える",
        "test": "曜日を使わずサーバ時刻の連続セッション定義をEAで実測",
        "grid": [dict(OafxGJRangeStart=start, OafxGJRangeEnd=end, OafxGJTradeEnd=end + span)
                 for start, end, span in itertools.product(range(0, 5), range(7, 12), range(1, 5))],
    },
    {
        "family": "sca_gj_exit_risk", "mode": 7,
        "overview": "SCA GBPJPYのRR・強制決済時刻・初期SL幅を同時調整",
        "rationale": "主因枠の損失額を実際のSLと保有期限で抑え、利益毀損を比較する",
        "test": "レンジ幅に対するSL比率とTP、強制決済を注文時に実装して実測",
        "grid": product(OafxGJRR=[1.2, 1.4, 1.6, 1.8, 2.1, 2.2, 2.4, 2.6, 2.8, 3.0],
                        OafxGJForceClose=[14, 16, 18, 20, 22],
                        OafxGJSLRangeFraction=[.60, .80]),
    },
    {
        "family": "sca_gj_overlap_gate", "mode": 8,
        "overview": "SCA GBPJPY新規時に実保有中のDD重複相手を制限",
        "rationale": "FULL損失の83.36%が他枠保有と重なり、上位ペアも同枠中心",
        "test": "対象magicの現在建玉数を発注直前に数え、閾値以上ならEAで見送る",
        "grid": product(OafxOverlapMask=[1, 2, 4, 8, 3, 5, 9, 6, 10, 15],
                        OafxOverlapLimit=[1, 2, 3, 4, 5],
                        OafxOverlapSide=[0, 1]),
    },
    {
        "family": "sca_gj_realized_loss_cooldown", "mode": 9,
        "overview": "直近実現損失が上限を超えた間だけSCA GBPJPY新規を停止",
        "rationale": "主因枠と重複相手の損失クラスターを実時間で遮断する",
        "test": "発注時点までのHistoryDeal総損失をlookback内で集計して実測",
        "grid": product(OafxLossLookbackHours=[6, 12, 24, 48, 72],
                        OafxLossCapJPY=[500, 1000, 2000, 4000, 8000],
                        OafxLossScope=[1, 2, 3, 4]),
    },
]


LARGE = [
    ("dynamic_correlation_allocator", "rolling相関に応じた9枠リスク予算", "多変量のpoint-in-time配分器と学習窓検証が必要"),
    ("latent_volatility_regime", "潜在ボラティリティ状態でSCAを切替", "状態推定器、凍結モデル、walk-forward検証が必要"),
    ("event_calendar_engine", "日米英の重要指標イベント連動ゲート", "将来情報混入を防ぐ時点整合カレンダー基盤が必要"),
    ("orderbook_liquidity_model", "板・流動性による偽ブレイク判定", "過去板データとOANDA再現可能な執行モデルが存在しない"),
    ("cross_asset_regime", "金利・株・商品を含むクロスアセット状態判定", "追加銘柄履歴、欠損処理、モデル凍結手順が必要"),
    ("online_bayesian_selector", "枠別成績の逐次Bayes配分", "事前分布と更新規則を固定した独立検証基盤が必要"),
    ("meta_label_model", "SCAシグナルのmeta-label分類", "学習データ分割、特徴量時点監査、モデルEA移植が必要"),
    ("tail_hedge_engine", "重複局面だけ動くテールヘッジ", "新規商品の選定、ヘッジ比率、証拠金一体検証が必要"),
    ("execution_cost_optimizer", "スリッページ分布を使う注文方式選択", "ブローカー別tick/約定履歴と注文シミュレータが必要"),
    ("walkforward_parameter_controller", "定期再学習するSCAパラメータ制御", "ネストしたwalk-forwardとライブ更新障害設計が必要"),
]


def detail(params: dict[str, Any]) -> str:
    return "; ".join(f"{key}={value}" for key, value in params.items())


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows: list[dict[str, Any]] = []
    for family in EXECUTABLE:
        assert len(family["grid"]) == 100, family["family"]
        for params in family["grid"]:
            parameters = {"OafxLabMode": family["mode"], **params}
            rows.append({
                "family": family["family"], "overview": family["overview"],
                "rationale": family["rationale"], "test_method": family["test"],
                "variation": detail(params), "implementation_class": "2軽微なコード変更",
                "status": "UNTESTED", "parameter_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                "unverified_reason": "",
            })
    for family, overview, reason in LARGE:
        for variant in range(1, 11):
            variant_reason = f"{reason}（variant {variant:02d}: 複雑度段階{variant}/10）"
            rows.append({
                "family": family, "overview": overview,
                "rationale": "SCA GBPJPY主因と枠間重複を動的状態推定で抑える長期案",
                "test_method": "基盤完成後に時点整合した実EA backtestを行う",
                "variation": f"複雑度・データ要求段階 {variant:02d}/10",
                "implementation_class": "3大規模開発", "status": "UNVERIFIED_LARGE_DEV",
                "parameter_json": "{}", "unverified_reason": variant_reason,
            })
    assert len(rows) == 1000
    for number, row in enumerate(rows, 1):
        row["id"] = f"OAFX{number:04d}"
    assert len({row["id"] for row in rows}) == 1000
    assert len({(row["family"], row["parameter_json"], row["variation"]) for row in rows}) == 1000
    forbidden = ("曜日除外", "後処理", "lot倍率0.")
    assert not any(any(token in " ".join(map(str, row.values())) for token in forbidden) for row in rows)
    write_csv(ROOT / "proposals.csv", rows, FIELDS)
    unverified = [{
        "proposal_id": row["id"], "family": row["family"], "status": row["status"],
        "reason": row["unverified_reason"], "parameter_json": row["parameter_json"],
    } for row in rows if row["implementation_class"].startswith("3")]
    write_csv(ROOT / "unverified.csv", unverified,
              ["proposal_id", "family", "status", "reason", "parameter_json"])
    print(json.dumps({
        "rows": len(rows), "families": len({row["family"] for row in rows}),
        "class2": sum(row["implementation_class"].startswith("2") for row in rows),
        "class3": len(unverified),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
