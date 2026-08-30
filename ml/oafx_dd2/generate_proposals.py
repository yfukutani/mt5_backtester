"""OANDA FX DD低減ラウンド2の1000案台帳を再現可能に生成する。"""
from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
ROUND1 = ROOT.parent / "oafx_dd" / "proposals.csv"
FIELDS = [
    "id", "family", "overview", "rationale", "test_method", "variation",
    "implementation_class", "status", "parameter_json", "unverified_reason",
]


def product(**values: Iterable[Any]) -> list[dict[str, Any]]:
    keys = list(values)
    return [
        dict(zip(keys, combination))
        for combination in itertools.product(*(values[key] for key in keys))
    ]


FAMILIES = [
    {
        "family": "gj_initial_stop_atr_cap",
        "mode": 101,
        "overview": "SCA GBPJPYの初期SL距離を日足ATR上限で浅くし、TP距離を新旧リスク間で補間",
        "rationale": "主因枠の含み損深度を発注直後から制限しつつ、シグナルと発注回数は維持する",
        "test": "全シグナルを発注し、元SLより近い場合だけATR上限SLと補間TPを設定してEA実測",
        "implementation": "2軽微なコード変更",
        "grid": product(
            Oafx2StopCapATR=[.45, .55, .65, .75, .85, .95, 1.05, 1.20, 1.40, 1.60],
            Oafx2TargetBlend=[0, .10, .20, .30, .40, .50, .60, .70, .80, .90],
        ),
    },
    {
        "family": "gj_early_mae_exit",
        "mode": 102,
        "overview": "SCA GBPJPYの建玉直後に急速な逆行が出た場合だけ成行決済",
        "rationale": "全期間で6時間未満の取引が大幅赤字であり、早期の最大逆行を浅い実損に固定する",
        "test": "発注は全件維持し、指定バー以内に逆行幅がATR閾値へ達した建玉だけEA内で決済",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2EarlyBars=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            Oafx2EarlyMAEATR=[.15, .20, .25, .30, .35, .40, .50, .60, .75, .90],
        ),
    },
    {
        "family": "gj_loss_persistence_exit",
        "mode": 103,
        "overview": "SCA GBPJPYで指定時間後も初期リスク比の含み損が残る建玉だけを決済",
        "rationale": "一時的な揺らぎは許容し、回復しない損失だけを時間とR倍率の二軸で浅く終える",
        "test": "全エントリー後、経過M15バー数と現在損失Rを毎tick評価して条件一致時のみ決済",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2LossAgeBars=[2, 4, 6, 8, 12, 16, 20, 24, 32, 40],
            Oafx2LossAtR=[.05, .10, .15, .20, .25, .30, .40, .50, .65, .80],
        ),
    },
    {
        "family": "gj_break_even_lock",
        "mode": 104,
        "overview": "SCA GBPJPYが一定R順行した後にSLを建値または小幅利益位置へ移動",
        "rationale": "勝ち方向へ進んだ建玉が全損へ反転する経路を遮断し、取引開始数を変えずにDDを抑える",
        "test": "発注後の最大順行RをEAで監視し、発動R到達後に一度だけSLを利益側へ変更",
        "implementation": "2軽微なコード変更",
        "grid": product(
            Oafx2BETriggerR=[.30, .40, .50, .60, .70, .80, 1.00, 1.20, 1.50, 1.80],
            Oafx2BELockR=[0, .02, .04, .06, .08, .10, .12, .15, .18, .20],
        ),
    },
    {
        "family": "gj_atr_trailing",
        "mode": 105,
        "overview": "SCA GBPJPYが一定R順行した後に日足ATR幅の追随SLを開始",
        "rationale": "24時間超の大勝ちは残しながら、順行後の反転で生じる含み益消失とDD拡大を抑える",
        "test": "全発注を維持し、発動R到達後だけ有利方向へ単調に動くATRトレールをEAで適用",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2TrailTriggerR=[.30, .40, .50, .60, .70, .80, 1.00, 1.20, 1.50, 2.00],
            Oafx2TrailATR=[.10, .15, .20, .25, .30, .40, .50, .60, .75, 1.00],
        ),
    },
    {
        "family": "gj_profit_giveback_exit",
        "mode": 106,
        "overview": "SCA GBPJPYの含み益ピーク到達後、指定割合を失った時点で成行決済",
        "rationale": "利益化した建玉の全損反転を防ぎつつ、発動前の通常変動と全エントリーを維持する",
        "test": "建玉別の最大含み益RをEA内で保持し、最小ピークR到達後のギブバック率で決済",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2PeakMinR=[.40, .50, .60, .70, .80, 1.00, 1.20, 1.50, 1.80, 2.00],
            Oafx2GivebackFraction=[.10, .20, .30, .40, .50, .60, .70, .80, .90, 1.00],
        ),
    },
    {
        "family": "gj_boost_partial_exit",
        "mode": 107,
        "overview": "SCA GBPJPYの逆張りブースト建玉だけを一定Rで0.01 lot単位に部分決済",
        "rationale": "0.06 lot群の利益機会を残しながら一部を早期回収し、その後の損失振幅を小さくする",
        "test": "0.01 lot建玉は変更せず、より大きい建玉だけ指定Rで指定lotを一度部分決済してEA実測",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2PartialTriggerR=[.20, .30, .40, .50, .60, .70, .80, .90, 1.00, 1.10,
                                  1.20, 1.30, 1.40, 1.50, 1.60, 1.80, 2.00, 2.20, 2.50, 3.00],
            Oafx2PartialLots=[.01, .02, .03, .04, .05],
        ),
    },
    {
        "family": "gj_boost_cash_risk_cap",
        "mode": 108,
        "overview": "SCA GBPJPY逆張りブーストをSLまでの想定円損失と最大倍率で動的に丸める",
        "rationale": "総損失-457,350円の0.06 lot群を直接縮める一方、全シグナルを最低0.01 lotで執行する",
        "test": "発注時のSL距離から0.01 lot当たり円リスクを計算し、1～最大倍率のlotでEA発注",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2BoostRiskJPY=[500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 2750,
                               3000, 3250, 3500, 3750, 4000, 4500, 5000, 5500, 6000, 7000],
            Oafx2BoostMaxMult=[2, 3, 4, 5, 6],
        ),
    },
    {
        "family": "gj_boost_drift_softscale",
        "mode": 109,
        "overview": "SCA GBPJPY逆張りブーストをレンジ内ドリフト強度に応じて1～6倍で連続調整",
        "rationale": "入口品質が弱くても取引は0.01 lotで続け、確信度が高い時だけ現行0.06 lotへ近づける",
        "test": "従来の逆張り方向判定は維持し、絶対drift÷rangeでブースト倍率だけを補間してEA発注",
        "implementation": "2軽微なコード変更",
        "grid": product(
            Oafx2FullBoostDriftRatio=[.05, .10, .15, .20, .25, .30, .35, .40, .45, .50,
                                      .55, .60, .65, .70, .75, .80, .85, .90, .95, 1.00],
            Oafx2BoostFloorMult=[1, 2, 3, 4, 5],
        ),
    },
    {
        "family": "gj_overlap_stop_cap",
        "mode": 110,
        "overview": "指定他枠との同時保有中だけSCA GBPJPYの残存SLリスクを初期R比で浅くする",
        "rationale": "DD区間損失の83.4%を占める同時保有状態を、発注拒否ではなく損失深度の制限に使う",
        "test": "同時保有でも全シグナルを発注し、対象magic保有中だけGJのSLを不利方向へ戻さず短縮",
        "implementation": "2中規模のコード変更",
        "grid": product(
            Oafx2OverlapMask=[1, 2, 4, 8, 3, 5, 9, 6, 10, 15],
            Oafx2OverlapRiskR=[.15, .20, .25, .30, .35, .40, .50, .60, .75, .90],
        ),
    },
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
    for family in FAMILIES:
        assert len(family["grid"]) == 100, (family["family"], len(family["grid"]))
        for params in family["grid"]:
            parameters = {"Oafx2LabMode": family["mode"], **params}
            rows.append({
                "family": family["family"],
                "overview": family["overview"],
                "rationale": family["rationale"],
                "test_method": family["test"],
                "variation": detail(params),
                "implementation_class": family["implementation"],
                "status": "UNTESTED",
                "parameter_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                "unverified_reason": "",
            })

    assert len(rows) == 1000
    for number, row in enumerate(rows, 1001):
        row["id"] = f"OAFX{number:04d}"

    assert rows[0]["id"] == "OAFX1001" and rows[-1]["id"] == "OAFX2000"
    assert len({row["id"] for row in rows}) == 1000
    assert len({(row["family"], row["parameter_json"]) for row in rows}) == 1000
    assert all(row["status"] == "UNTESTED" for row in rows)
    assert all(row["implementation_class"].startswith("2") for row in rows)

    forbidden = (
        "overlap_gate", "realized_loss_cooldown", "weekday_exclusion",
        "postprocess_sampling", "lot_multiplier_below_one",
    )
    searchable = "\n".join(" ".join(map(str, row.values())).lower() for row in rows)
    assert not any(token in searchable for token in forbidden)

    if ROUND1.exists():
        with ROUND1.open(encoding="utf-8-sig", newline="") as handle:
            old_rows = list(csv.DictReader(handle))
        assert not ({row["id"] for row in rows} & {row["id"] for row in old_rows})
        old_keys = {(row["family"], row["parameter_json"]) for row in old_rows}
        assert not ({(row["family"], row["parameter_json"]) for row in rows} & old_keys)

    write_csv(ROOT / "proposals.csv", rows, FIELDS)
    write_csv(
        ROOT / "unverified.csv", [],
        ["proposal_id", "family", "status", "reason", "parameter_json"],
    )
    print(json.dumps({
        "rows": len(rows),
        "first_id": rows[0]["id"],
        "last_id": rows[-1]["id"],
        "families": {family["family"]: len(family["grid"]) for family in FAMILIES},
        "executable": sum(row["implementation_class"].startswith("2") for row in rows),
        "unverified": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
