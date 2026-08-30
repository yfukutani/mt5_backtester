"""OANDA FX DD round-2 actual-MT5 driver.

The battle-tested round-1 execution engine is reused for terminal ownership,
five-way parallelism, launch staggering, restart-safe append-only results, the
two-stage screen, and optional regression/magic gates.  This module supplies
the round-2 registry, paths, classifications, and mandatory trade-count gate.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import sys
import threading
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
ROUND1_DRIVER = ROOT.parent / "oafx_dd" / "run_oafx.py"


def load_round1_driver():
    spec = importlib.util.spec_from_file_location("oafx_round1_engine", ROUND1_DRIVER)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load round-1 driver: {ROUND1_DRIVER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load_round1_driver()

# Round-2-local mutable artifacts.  No production config is changed.
engine.ROOT = ROOT
engine.PROPOSALS = ROOT / "proposals.csv"
engine.RESULTS = ROOT / "results.csv"
engine.UNVERIFIED = ROOT / "unverified.csv"
engine.CONFIG_DIR = ROOT / "configs"
engine.LOG_DIR = ROOT / "logs"
engine.DEAL_DIR = ROOT / "run_deals"
engine.PROGRESS = ROOT / "run_oafx2.log"
engine.LOCK = ROOT / "run_oafx2.lock"
engine.BASE_TEMPLATE = ROOT / "regression_is.yaml"
engine.DEFAULT_RUN_TIMEOUT = 1200
engine.DEFAULT_TERMINAL_COUNT = 5
engine.TERMINAL_START_STAGGER_SECONDS = 8.0

# 2026-08-29 再基準化。ブローカー側の銘柄仕様(スワップ)更新により旧基準277,106は
# 再現不能になった。dealログ全列比較で時刻・magic・ロット・約定価格・SL・position IDは
# 全行一致し、profit/profit_jpyのみ344行で差(合計+1,535円)。本番EA自身も同じ値を出す。
# 5端末すべてがこの値で一致することを確認済み。
BASELINE_IS_FALLBACK = {"net": 279712.0, "pf": 1.3994, "dd_pct": 34.8667, "trades": 1573}
BASELINE_OOS_FALLBACK = {"net": 117124.0, "pf": 1.2182, "dd_pct": 30.1366, "trades": 1354}
BASELINE_SCREEN_IS_FALLBACK = {"net": 84921.0, "pf": 1.2184, "dd_pct": 19.5314, "trades": 685}
MIN_TRADE_RATIO = 0.70
DD_NOISE_THRESHOLD_PT = 0.5
PROFIT_NOISE_THRESHOLD_RATIO = 0.01
TOKYO = ZoneInfo("Asia/Tokyo")
PRODUCTION_EA = "MIX_EA_OANDA"
PRODUCTION_EA_SOURCE = REPO / "experts" / "MIX_EA_OANDA.mq5"

BASELINE_IDS = {
    "IS": "REGRESSION_BASELINE",
    "OOS": "BASELINE_OOS",
    "SCREEN_IS": "BASELINE_SCREEN_IS",
}
FALLBACKS = {
    "IS": BASELINE_IS_FALLBACK,
    "OOS": BASELINE_OOS_FALLBACK,
    "SCREEN_IS": BASELINE_SCREEN_IS_FALLBACK,
}

# Each worker retains the baseline snapshot selected immediately before its MT5
# launch.  A different worker may refresh the process-wide baseline after
# midnight without changing an already-running candidate's comparison target.
RUN_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("oafx2_run_context", default=None)


def measurement_date() -> str:
    return datetime.now(TOKYO).date().isoformat()


def metric_dict(value: dict[str, Any]) -> dict[str, float]:
    return {key: float(value[key]) for key in ("net", "pf", "dd_pct", "trades")}


def fallback(window: str) -> dict[str, float]:
    return {key: float(value) for key, value in FALLBACKS[window].items()}


def context_baseline(window: str) -> dict[str, Any] | None:
    context = RUN_CONTEXT.get()
    if not context:
        return None
    return context.get("baselines", {}).get(window)


def current_is_baseline() -> dict[str, float]:
    selected = context_baseline("IS")
    if selected:
        return metric_dict(selected)
    if DAILY_BASELINES.current:
        return metric_dict(DAILY_BASELINES.current["IS"])
    return fallback("IS")


def selected_baseline(window: str) -> dict[str, Any]:
    selected = context_baseline(window)
    if selected:
        return selected
    if DAILY_BASELINES.current:
        return DAILY_BASELINES.current[window]
    return {
        **fallback(window),
        "measurement_date": measurement_date(),
        "source": "FALLBACK_NO_DAILY_MEASUREMENT",
    }


def noise_for_window(value: dict[str, Any], baseline: dict[str, Any]) -> bool:
    dd_improvement = float(baseline["dd_pct"]) - float(value["dd_pct"])
    profit_change = abs(float(value["net"]) / float(baseline["net"]) - 1.0)
    return (
        0.0 < dd_improvement < DD_NOISE_THRESHOLD_PT
        or profit_change < PROFIT_NOISE_THRESHOLD_RATIO
    )


def detail(window: str, value: dict[str, Any], baseline: dict[str, float]) -> str:
    ratio = float(value["trades"]) / baseline["trades"]
    return (
        f"{window} net={float(value['net']):.2f} ({float(value['net']) / baseline['net'] - 1:+.2%}), "
        f"PF={float(value['pf']):.4f} ({float(value['pf']) / baseline['pf'] - 1:+.2%}), "
        f"DD={float(value['dd_pct']):.4f}% "
        f"({float(value['dd_pct']) - baseline['dd_pct']:+.4f}pt), "
        f"DD<30={'YES' if float(value['dd_pct']) < 30 else 'NO'}, "
        f"trades={int(value['trades'])} ({ratio - 1:+.2%})"
    )


def classify_is(value: dict[str, Any]) -> tuple[str, str, str]:
    baseline = selected_baseline("IS")
    reason = detail("IS", value, baseline)
    trade_ratio = float(value["trades"]) / baseline["trades"]
    if trade_ratio < MIN_TRADE_RATIO:
        return "IS_SLOT_SHRINK", "TRADE_COUNT_BELOW_70", reason
    dd_lower = float(value["dd_pct"]) < baseline["dd_pct"]
    profit_ok = float(value["net"]) >= baseline["net"] * 0.90
    if dd_lower and noise_for_window(value, baseline):
        return "IS_NOISE_BAND", "EFFECT_WITHIN_NOISE_BAND", reason
    strict = (dd_lower and float(value["net"]) > baseline["net"] and
              float(value["pf"]) > baseline["pf"])
    if strict:
        return "IS_SURVIVOR_STRICT", "STRICT_IS", reason
    if dd_lower and profit_ok:
        return "IS_SURVIVOR_DD", "DD_AND_PROFIT_GATE", reason
    if dd_lower:
        return "IS_REJECT_TRADEOFF", "PROFIT_DAMAGE_GT10", reason
    return "IS_REJECT", "DD_NOT_IMPROVED", reason


def classify_screen_is(value: dict[str, Any]) -> tuple[str, str, str]:
    baseline = selected_baseline("SCREEN_IS")
    reason = "single-sleeve pre-screen only; " + detail("SCREEN_IS", value, baseline)
    if float(value["trades"]) / baseline["trades"] < MIN_TRADE_RATIO:
        return "SCREEN_OUT_SLOT_SHRINK", "TRADE_COUNT_BELOW_70", reason
    dd_lower = float(value["dd_pct"]) < baseline["dd_pct"]
    profit_ok = float(value["net"]) >= baseline["net"] * 0.90
    if dd_lower and noise_for_window(value, baseline):
        return "SCREEN_NOISE_BAND", "EFFECT_WITHIN_NOISE_BAND", reason
    if dd_lower and profit_ok:
        if float(value["net"]) > baseline["net"] and float(value["pf"]) > baseline["pf"]:
            return "SCREEN_PASS_STRICT", "SINGLE_STRICT_GATE", reason
        return "SCREEN_PASS_DD", "SINGLE_DD_AND_PROFIT_GATE", reason
    return "SCREEN_OUT_SINGLE_SLEEVE", (
        "SINGLE_PROFIT_DAMAGE_GT10" if dd_lower else "SINGLE_DD_NOT_IMPROVED"
    ), reason


def oos_baseline() -> dict[str, float]:
    return metric_dict(selected_baseline("OOS"))


def classify_oos(is_row: dict[str, str], value: dict[str, Any],
                 _base_oos: dict[str, Any]) -> tuple[str, str, str]:
    baseline_is = baseline_from_row(is_row, "is")
    baseline_oos = selected_baseline("OOS")
    is_value = {key: float(is_row[key]) for key in ("net", "pf", "dd_pct", "trades")}
    reason = detail("IS", is_value, baseline_is) + "; " + detail("OOS", value, baseline_oos)
    is_trade_ratio = is_value["trades"] / baseline_is["trades"]
    oos_trade_ratio = float(value["trades"]) / baseline_oos["trades"]
    if is_trade_ratio < MIN_TRADE_RATIO or oos_trade_ratio < MIN_TRADE_RATIO:
        return "SLOT_SHRINK", "TRADE_COUNT_BELOW_70", reason

    is_dd = is_value["dd_pct"] < baseline_is["dd_pct"]
    oos_dd = float(value["dd_pct"]) < baseline_oos["dd_pct"]
    both_dd = is_dd and oos_dd
    within_noise = both_dd and (
        noise_for_window(is_value, baseline_is) or noise_for_window(value, baseline_oos)
    )
    strict = (
        both_dd and is_value["net"] > baseline_is["net"] and
        is_value["pf"] > baseline_is["pf"] and
        float(value["net"]) > baseline_oos["net"] and
        float(value["pf"]) > baseline_oos["pf"]
    )
    profit_ok = (is_value["net"] >= baseline_is["net"] * 0.90 and
                 float(value["net"]) >= baseline_oos["net"] * 0.90)
    if within_noise:
        return "NOISE_BAND", "EFFECT_WITHIN_NOISE_BAND", reason
    if strict:
        return "STRICT_IMPROVEMENT", "STRICT_BOTH", reason
    if both_dd and profit_ok:
        return "DD_IMPROVEMENT", "DD_BOTH_PROFIT_WITHIN10", reason
    if both_dd:
        return "TRADEOFF", "DD_BOTH_PROFIT_DAMAGE_GT10", reason
    return "REJECT", "DD_NOT_LOWER_BOTH", reason


def screening_plan(proposal: dict[str, str]) -> tuple[str, str]:
    if proposal["family"] == "gj_overlap_stop_cap":
        return engine.SCREEN_ROUTE_DIRECT, (
            "他枠の同時保有を参照するため、単独枠スクリーニングでは測定不能"
        )
    return engine.SCREEN_ROUTE_STAGED, (
        "SCA GBPJPY内の損失深度・退出・ブースト量だけを変えるため単独枠で一次選別"
    )


engine.classify_is = classify_is
engine.classify_screen_is = classify_screen_is
engine.classify_oos = classify_oos
engine.screening_plan = screening_plan

EXTRA_RESULT_FIELDS = [
    "measurement_date", "baseline_measurement_date", "baseline_source",
    "baseline_net", "baseline_pf", "baseline_dd_pct", "baseline_trades",
    "is_baseline_measurement_date", "is_baseline_source", "is_baseline_net",
    "is_baseline_pf", "is_baseline_dd_pct", "is_baseline_trades",
    "oos_baseline_measurement_date", "oos_baseline_source", "oos_baseline_net",
    "oos_baseline_pf", "oos_baseline_dd_pct", "oos_baseline_trades",
    "within_noise_band", "classification_bucket", "trade_count_gate_pass",
    "is_trades", "is_trade_change_rate", "oos_trades", "oos_trade_change_rate",
]
insert_at = engine.RESULT_FIELDS.index("ea_sha256")
engine.RESULT_FIELDS[insert_at:insert_at] = EXTRA_RESULT_FIELDS


def apply_baseline_fields(row: dict[str, Any], baseline: dict[str, Any]) -> None:
    row.update(
        baseline_measurement_date=baseline["measurement_date"],
        baseline_source=baseline["source"],
        baseline_net=baseline["net"],
        baseline_pf=baseline["pf"],
        baseline_dd_pct=baseline["dd_pct"],
        baseline_trades=int(float(baseline["trades"])),
    )


def apply_period_baseline_fields(row: dict[str, Any], prefix: str,
                                 baseline: dict[str, Any]) -> None:
    row.update({
        f"{prefix}_baseline_measurement_date": baseline["measurement_date"],
        f"{prefix}_baseline_source": baseline["source"],
        f"{prefix}_baseline_net": baseline["net"],
        f"{prefix}_baseline_pf": baseline["pf"],
        f"{prefix}_baseline_dd_pct": baseline["dd_pct"],
        f"{prefix}_baseline_trades": int(float(baseline["trades"])),
    })


def baseline_from_row(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    date_key = f"{prefix}_baseline_measurement_date"
    if not row.get(date_key):
        raise RuntimeError(f"candidate row has no auditable {prefix.upper()} daily baseline")
    return {
        "measurement_date": row[date_key],
        "source": row[f"{prefix}_baseline_source"],
        "net": float(row[f"{prefix}_baseline_net"]),
        "pf": float(row[f"{prefix}_baseline_pf"]),
        "dd_pct": float(row[f"{prefix}_baseline_dd_pct"]),
        "trades": float(row[f"{prefix}_baseline_trades"]),
    }


def validate_simverify_row(row: dict[str, Any], baseline: dict[str, Any]) -> None:
    checks: dict[str, bool] = {"actual_daily_baseline": baseline["source"] == "ACTUAL_MT5"}
    if row.get("status") == "OK" and row.get("net") not in (None, ""):
        checks.update({
            "net": abs(float(row["net"]) - baseline["net"]) < .005,
            "pf": abs(float(row["pf"]) - baseline["pf"]) < .00005,
            "dd": abs(float(row["dd_pct"]) - baseline["dd_pct"]) < .00005,
            "trades": int(float(row["trades"])) == int(float(baseline["trades"])),
            "deal_log": int(float(row["deal_rows"])) > 0 and bool(row["projected_sha256"]),
        })
        magic_names = ("sca_gbpjpy",) if row.get("window") == "SCREEN_IS" else tuple(engine.MAGICS)
        checks["magic_rows"] = all(int(float(row[f"{name}_rows"])) > 0 for name in magic_names)
    else:
        checks["simverify_run"] = False
    failed = [name for name, passed in checks.items() if not passed]
    row["regression_pass"] = not failed
    row.update(
        status="OK" if not failed else "INVALID",
        decision="REGRESSION_PASS" if not failed else "REGRESSION_FAIL",
        gate_code="DAILY_BASELINE_MATCH" if not failed else "DAILY_BASELINE_MISMATCH",
        reason=(
            "same-day production baseline matches default-OFF SIMVERIFY"
            if not failed else "failed: " + ",".join(failed)
        ),
    )


def append_result(row: dict[str, Any]) -> None:
    window = row.get("window")
    context = RUN_CONTEXT.get() or {}
    row["measurement_date"] = context.get("measurement_date", measurement_date())
    baseline = context_baseline(str(window)) if window in FALLBACKS else None
    if baseline:
        apply_baseline_fields(row, baseline)

    if context.get("kind") == "daily_production":
        row["ea_sha256"] = hashlib.sha256(PRODUCTION_EA_SOURCE.read_bytes()).hexdigest().upper()
        if row.get("status") == "OK":
            actual_baseline = {
                **metric_dict(row),
                "measurement_date": row["measurement_date"],
                "source": "ACTUAL_MT5",
            }
            apply_baseline_fields(row, actual_baseline)
            row.update(
                decision="BASELINE_MEASURED", gate_code="DAILY_ACTUAL_MT5",
                reason=f"{window} daily production baseline measured by actual MT5",
            )
    elif context.get("kind") == "daily_simverify":
        validate_simverify_row(row, context["baselines"][str(window)])

    if window in {"IS", "SCREEN_IS"} and row.get("trades") not in (None, ""):
        baseline = selected_baseline(str(window))
        row["is_trades"] = int(row["trades"])
        row["is_trade_change_rate"] = float(row["trades"]) / baseline["trades"] - 1.0
        row["trade_count_gate_pass"] = float(row["trades"]) >= baseline["trades"] * MIN_TRADE_RATIO
    elif window == "OOS" and row.get("trades") not in (None, ""):
        is_row = engine.latest_rows().get((str(row.get("proposal_id")), "IS"))
        baseline_is = baseline_from_row(is_row, "is") if is_row else selected_baseline("IS")
        baseline_oos = selected_baseline("OOS")
        if is_row:
            row["is_trades"] = int(float(is_row["trades"]))
            row["is_trade_change_rate"] = float(is_row["trades"]) / baseline_is["trades"] - 1.0
            row["is_dd_below_30"] = float(is_row["dd_pct"]) < 30.0
        row["oos_trades"] = int(row["trades"])
        row["oos_trade_change_rate"] = float(row["trades"]) / baseline_oos["trades"] - 1.0
        row["oos_dd_below_30"] = float(row["dd_pct"]) < 30.0
        row["trade_count_gate_pass"] = (
            bool(is_row) and float(is_row["trades"]) >= baseline_is["trades"] * MIN_TRADE_RATIO and
            float(row["trades"]) >= baseline_oos["trades"] * MIN_TRADE_RATIO
        )

    if row.get("status") == "OK" and window in FALLBACKS and row.get("trades") not in (None, ""):
        if window == "OOS":
            is_row = engine.latest_rows().get((str(row.get("proposal_id")), "IS"))
            is_base = baseline_from_row(is_row, "is") if is_row else selected_baseline("IS")
            oos_base = selected_baseline("OOS")
            apply_period_baseline_fields(row, "is", is_base)
            apply_period_baseline_fields(row, "oos", oos_base)
            row["within_noise_band"] = bool(
                is_row and float(is_row["dd_pct"]) < is_base["dd_pct"]
                and float(row["dd_pct"]) < oos_base["dd_pct"]
                and (noise_for_window(is_row, is_base) or noise_for_window(row, oos_base))
            )
            row["profit_ratio"] = float(row["net"]) / oos_base["net"]
            row["pf_ratio"] = float(row["pf"]) / oos_base["pf"]
            row["dd_delta"] = float(row["dd_pct"]) - oos_base["dd_pct"]
        else:
            prefix = "is" if window == "IS" else None
            if prefix:
                apply_period_baseline_fields(row, prefix, selected_baseline(str(window)))
            row["within_noise_band"] = (
                float(row["dd_pct"]) < selected_baseline(str(window))["dd_pct"]
                and noise_for_window(row, selected_baseline(str(window)))
            )
            row["profit_ratio"] = float(row["net"]) / selected_baseline(str(window))["net"]
            row["pf_ratio"] = float(row["pf"]) / selected_baseline(str(window))["pf"]
            row["dd_delta"] = float(row["dd_pct"]) - selected_baseline(str(window))["dd_pct"]

    parameters = json.loads(str(row.get("parameter_json") or "{}"))
    lot_sensitive = int(parameters.get("Oafx2LabMode", 0)) in {108, 109}
    if lot_sensitive:
        changed = row.get("effective_gj_lots") != row.get("baseline_gj_lots")
        row["lot_step_verified"] = changed
        if not changed and row.get("status") == "OK":
            row.update(
                status="UNVERIFIED", decision="UNVERIFIED_LOTSTEP",
                gate_code="EFFECTIVE_LOTS_UNCHANGED",
                reason=f"SCA GBPJPY lots unchanged: {row.get('effective_gj_lots', '')}",
            )

    if row.get("decision") in {"SLOT_SHRINK", "IS_SLOT_SHRINK", "SCREEN_OUT_SLOT_SHRINK"}:
        row["classification_bucket"] = "枠縮小"
    elif row.get("decision") in {"NOISE_BAND", "IS_NOISE_BAND", "SCREEN_NOISE_BAND"}:
        row["classification_bucket"] = "ノイズ範囲"
    elif row.get("decision") in {"STRICT_IMPROVEMENT", "DD_IMPROVEMENT", "TRADEOFF", "REJECT"}:
        row["classification_bucket"] = row["decision"]

    expected_production_log_absence = (
        context.get("kind") == "daily_production"
        and not context.get("write_production_failure")
        and row.get("status") == "FAILED"
        and row.get("gate_code") == "FileNotFoundError"
        and "FILE_COMMON deal log missing" in str(row.get("reason"))
    )
    if expected_production_log_absence:
        return

    with engine.RESULT_LOCK:
        with engine.RESULTS.open("a", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=engine.RESULT_FIELDS, extrasaction="ignore").writerow(
                {field: row.get(field, "") for field in engine.RESULT_FIELDS}
            )
            handle.flush()
            os.fsync(handle.fileno())


engine.append_result = append_result


round1_base_config = engine.base_config


def base_config(window: str, run_id: str, deal_name: str) -> dict[str, Any]:
    """Start every generated config with both lab generations OFF."""
    config = round1_base_config(window, run_id, deal_name)
    context = RUN_CONTEXT.get() or {}
    if context.get("kind") == "daily_production":
        config["expert"] = PRODUCTION_EA
        config["parameters"].pop("OafxLabMode", None)
        config["parameters"].pop("Oafx2LabMode", None)
    else:
        config["parameters"]["Oafx2LabMode"] = 0
    return config


engine.base_config = base_config


round1_execute = engine.execute
round1_completed = engine.completed


class DailyBaselineManager:
    """Measure and retain one immutable production baseline snapshot per Tokyo date."""

    def __init__(self) -> None:
        self.current: dict[str, dict[str, Any]] | None = None
        self._verified_date: str | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _provisional(date: str) -> dict[str, dict[str, Any]]:
        return {
            window: {
                **fallback(window), "measurement_date": date,
                "source": "FALLBACK_PENDING_DAILY_MEASUREMENT",
            }
            for window in FALLBACKS
        }

    def _measure_one(self, window: str, date: str, args: Any, terminal: Any,
                     launch_gate: Any, provisional: dict[str, dict[str, Any]]) -> dict[str, Any]:
        context = {
            "kind": "daily_production", "measurement_date": date,
            "baselines": provisional,
        }
        token = RUN_CONTEXT.set(context)
        try:
            if window == "OOS":
                result = round1_execute(None, window, args, terminal, launch_gate,
                                        purpose="oos_baseline")
            else:
                proposal = {
                    "id": BASELINE_IDS[window], "family": "daily_baseline",
                    "implementation_class": "gate", "parameter_json": "{}",
                }
                result = round1_execute(proposal, window, args, terminal, launch_gate)
            # The production EA intentionally has no SIMVERIFY deal logger.  Its
            # MT5 report is nevertheless complete, so recover the actual summary
            # instead of treating the missing verification-only CSV as a failed
            # baseline.  The second append supersedes the failed audit attempt.
            if (result.get("status") == "FAILED"
                    and result.get("gate_code") == "FileNotFoundError"
                    and "FILE_COMMON deal log missing" in str(result.get("reason"))):
                try:
                    summary = engine.read_summary(str(result["run_id"]))
                except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
                    engine.progress(
                        f"DAILY_BASELINE_REPORT_UNAVAILABLE date={date} window={window} "
                        f"error={type(exc).__name__}:{exc}"
                    )
                    context["write_production_failure"] = True
                    append_result(result)
                else:
                    result.update(
                        summary, status="OK", decision="BASELINE_MEASURED",
                        gate_code="DAILY_ACTUAL_MT5_REPORT",
                        reason=f"{window} daily production baseline recovered from MT5 report",
                        dd_below_30=summary["dd_pct"] < 30, error="",
                    )
                    append_result(result)
                    engine.progress(
                        f"DAILY_BASELINE_REPORT_RECOVERED date={date} window={window} "
                        f"net={summary['net']:.2f} pf={summary['pf']:.4f} "
                        f"dd={summary['dd_pct']:.4f} trades={summary['trades']}"
                    )
        finally:
            RUN_CONTEXT.reset(token)
        if result.get("status") == "OK" and result.get("net") not in (None, ""):
            return {
                **metric_dict(result),
                "measurement_date": date,
                "source": "ACTUAL_MT5",
            }
        engine.progress(
            f"DAILY_BASELINE_FALLBACK date={date} window={window} "
            f"status={result.get('status')} reason={result.get('reason')}"
        )
        return {
            **fallback(window), "measurement_date": date,
            "source": "FALLBACK_ACTUAL_MT5_FAILED",
        }

    def ensure(self, args: Any, terminal: Any, launch_gate: Any) -> dict[str, dict[str, Any]]:
        with self._lock:
            target = measurement_date()
            if self.current and self.current["IS"]["measurement_date"] == target:
                return self.current
            while True:
                engine.progress(f"DAILY_BASELINE_REFRESH_START date={target}")
                provisional = self._provisional(target)
                measured: dict[str, dict[str, Any]] = {}
                for window in ("IS", "OOS", "SCREEN_IS"):
                    measured[window] = self._measure_one(
                        window, target, args, terminal, launch_gate, provisional
                    )
                    provisional[window] = measured[window]
                if measurement_date() != target:
                    target = measurement_date()
                    engine.progress(
                        f"DAILY_BASELINE_DATE_CHANGED action=remeasure new_date={target}"
                    )
                    continue
                self.current = measured
                self._verified_date = None
                engine.BASELINE_IS = metric_dict(measured["IS"])
                engine.BASELINE_SCREEN_IS = metric_dict(measured["SCREEN_IS"])
                engine.progress(
                    "DAILY_BASELINE_REFRESH_END " + " ".join(
                        f"{window}=net:{value['net']:.2f},pf:{value['pf']:.4f},"
                        f"dd:{value['dd_pct']:.4f},trades:{int(value['trades'])},"
                        f"source:{value['source']}"
                        for window, value in measured.items()
                    )
                )
                return measured

    def ensure_regression(self, args: Any, terminal: Any, launch_gate: Any) -> None:
        with self._lock:
            baselines = self.ensure(args, terminal, launch_gate)
            date = baselines["IS"]["measurement_date"]
            if self._verified_date == date:
                engine.progress(f"SKIP_REGRESSION date={date} reason=existing same-day pass")
                return
            if any(item["source"] != "ACTUAL_MT5" for item in baselines.values()):
                raise RuntimeError("daily regression gate requires three actual-MT5 baselines")
            proposal = {
                "id": f"DAILY_SIMVERIFY_{date.replace('-', '')}",
                "family": "daily_regression", "implementation_class": "gate",
                "parameter_json": "{}",
            }
            for window in ("IS", "SCREEN_IS", "OOS"):
                token = RUN_CONTEXT.set({
                    "kind": "daily_simverify", "measurement_date": date,
                    "baselines": baselines,
                })
                try:
                    result = round1_execute(proposal, window, args, terminal, launch_gate)
                finally:
                    RUN_CONTEXT.reset(token)
                if result.get("decision") != "REGRESSION_PASS":
                    raise RuntimeError(
                        f"daily regression gate failed for {window}: {result.get('reason')}"
                    )
            if measurement_date() != date:
                engine.progress(
                    f"REGRESSION_DATE_CHANGED action=remeasure old_date={date} "
                    f"new_date={measurement_date()}"
                )
                self.current = None
                self._verified_date = None
                self.ensure_regression(args, terminal, launch_gate)
                return
            self._verified_date = date


DAILY_BASELINES = DailyBaselineManager()


def execute(proposal: dict[str, str] | None, window: str, args: Any, terminal: Any,
            launch_gate: Any, purpose: str = "proposal") -> dict[str, Any]:
    context = RUN_CONTEXT.get()
    if context:
        return round1_execute(proposal, window, args, terminal, launch_gate, purpose)
    baselines = DAILY_BASELINES.ensure(args, terminal, launch_gate)
    if args.sha_regression_gate:
        DAILY_BASELINES.ensure_regression(args, terminal, launch_gate)
        baselines = DAILY_BASELINES.ensure(args, terminal, launch_gate)
    date = baselines["IS"]["measurement_date"]
    token = RUN_CONTEXT.set({
        "kind": "candidate", "measurement_date": date, "baselines": baselines,
    })
    try:
        return round1_execute(proposal, window, args, terminal, launch_gate, purpose)
    finally:
        RUN_CONTEXT.reset(token)


def completed(row: dict[str, str] | None, args: Any) -> bool:
    if row and row.get("proposal_id") not in set(BASELINE_IDS.values()):
        if row.get("window") in FALLBACKS and not row.get("baseline_measurement_date"):
            return False
    return round1_completed(row, args)


def ensure_regression(args: Any, latest: dict[tuple[str, str], dict[str, str]],
                      terminal: Any, launch_gate: Any) -> None:
    if args.dry_run:
        engine.progress("DAILY_BASELINE skipped for dry-run")
        return
    DAILY_BASELINES.ensure(args, terminal, launch_gate)
    if args.sha_regression_gate:
        DAILY_BASELINES.ensure_regression(args, terminal, launch_gate)
    else:
        engine.progress("REGRESSION_GATE disabled; daily production baselines measured")
    latest.update(engine.latest_rows())


def ensure_oos_baseline(args: Any, latest: dict[tuple[str, str], dict[str, str]],
                        state_lock: Any, terminal: Any, launch_gate: Any) -> None:
    baselines = DAILY_BASELINES.ensure(args, terminal, launch_gate)
    if baselines["OOS"]["measurement_date"] != measurement_date():
        raise RuntimeError("OOS baseline date changed before candidate launch")
    with state_lock:
        latest.update(engine.latest_rows())


engine.execute = execute
engine.completed = completed
engine.ensure_regression = ensure_regression
engine.ensure_oos_baseline = ensure_oos_baseline


def self_check() -> None:
    proposals = engine.read_csv(engine.PROPOSALS)
    if len(proposals) != 1000 or len({row["id"] for row in proposals}) != 1000:
        raise AssertionError("round-2 registry must contain 1,000 unique proposals")
    if any(not row["implementation_class"].startswith("2") for row in proposals):
        raise AssertionError("all round-2 proposals must be executable class 2")
    known_inputs = engine.ea_inputs()
    missing = {
        row["id"]: sorted(set(json.loads(row["parameter_json"])) - known_inputs)
        for row in proposals
        if set(json.loads(row["parameter_json"])) - known_inputs
    }
    if missing:
        raise AssertionError(f"proposal inputs missing from SIMVERIFY: {missing}")
    if len(engine.read_csv(engine.UNVERIFIED)) != 0:
        raise AssertionError("round-2 unverified registry should be empty")
    routes = {engine.SCREEN_ROUTE_STAGED: 0, engine.SCREEN_ROUTE_DIRECT: 0}
    for proposal in proposals:
        routes[screening_plan(proposal)[0]] += 1
    if routes != {engine.SCREEN_ROUTE_STAGED: 900, engine.SCREEN_ROUTE_DIRECT: 100}:
        raise AssertionError(f"unexpected screening routes: {routes}")
    defaults = engine.parse_args([])
    if defaults.run_timeout != 1200 or defaults.terminal_count != 5:
        raise AssertionError("runtime defaults changed")
    if defaults.start_stagger_seconds < 8.0:
        raise AssertionError("MT5 launches must be staggered by at least eight seconds")
    if MIN_TRADE_RATIO != 0.70:
        raise AssertionError("trade-count gate must be 70%")
    if DD_NOISE_THRESHOLD_PT != 0.5 or PROFIT_NOISE_THRESHOLD_RATIO != 0.01:
        raise AssertionError("noise thresholds changed")

    date = measurement_date()
    synthetic_baselines = {
        window: {**fallback(window), "measurement_date": date, "source": "ACTUAL_MT5"}
        for window in FALLBACKS
    }
    token = RUN_CONTEXT.set({
        "kind": "self_check", "measurement_date": date, "baselines": synthetic_baselines,
    })
    try:
        is_base = synthetic_baselines["IS"]
        dd_noise = {
            "net": is_base["net"] * 1.02, "pf": is_base["pf"] * 1.01,
            "dd_pct": is_base["dd_pct"] - 0.4999, "trades": is_base["trades"],
        }
        profit_noise = {
            "net": is_base["net"] * 1.0099, "pf": is_base["pf"] * 1.01,
            "dd_pct": is_base["dd_pct"] - 0.6, "trades": is_base["trades"],
        }
        significant = {
            "net": is_base["net"] * 1.01, "pf": is_base["pf"] * 1.01,
            "dd_pct": is_base["dd_pct"] - 0.5, "trades": is_base["trades"],
        }
        if classify_is(dd_noise)[0] != "IS_NOISE_BAND":
            raise AssertionError("DD noise band boundary is ineffective")
        if classify_is(profit_noise)[0] != "IS_NOISE_BAND":
            raise AssertionError("profit noise band boundary is ineffective")
        if classify_is(significant)[0] != "IS_SURVIVOR_STRICT":
            raise AssertionError("significant improvement was incorrectly treated as noise")

        regression_row = {
            "window": "IS", "status": "OK", **metric_dict(is_base),
            "deal_rows": 2, "projected_sha256": "SYNTHETIC",
            **{f"{name}_rows": 1 for name in engine.MAGICS},
        }
        validate_simverify_row(regression_row, is_base)
        if regression_row["decision"] != "REGRESSION_PASS":
            raise AssertionError("same-day regression match was rejected")
        mismatch_row = {**regression_row, "status": "OK", "net": is_base["net"] + 1.0}
        validate_simverify_row(mismatch_row, is_base)
        if mismatch_row["decision"] != "REGRESSION_FAIL":
            raise AssertionError("same-day regression mismatch was not detected")
    finally:
        RUN_CONTEXT.reset(token)

    legacy = {"proposal_id": "OAFX_TEST", "window": "IS", "ea_sha256": engine.ea_sha(),
              "status": "OK"}
    audited = {**legacy, "baseline_measurement_date": date}
    if completed(legacy, defaults) or not completed(audited, defaults):
        raise AssertionError("restart skip must require an auditable daily baseline")
    required_fields = {
        "baseline_measurement_date", "baseline_net", "baseline_pf", "baseline_dd_pct",
        "baseline_trades", "within_noise_band", "is_trade_change_rate",
        "oos_trade_change_rate", "is_dd_below_30", "oos_dd_below_30",
    }
    if not required_fields.issubset(engine.RESULT_FIELDS):
        raise AssertionError("daily baseline/noise audit fields are missing")
    print(json.dumps({
        "self_check": "OK", "proposals": len(proposals), "executable": len(proposals),
        "families": len({row["family"] for row in proposals}),
        "screening_routes": routes, "terminal_count": defaults.terminal_count,
        "start_stagger_seconds": defaults.start_stagger_seconds,
        "run_timeout": defaults.run_timeout, "minimum_trade_ratio": MIN_TRADE_RATIO,
        "dd_noise_threshold_pt": DD_NOISE_THRESHOLD_PT,
        "profit_noise_threshold_ratio": PROFIT_NOISE_THRESHOLD_RATIO,
        "restart_skip_requires_daily_baseline": True,
    }, ensure_ascii=False), flush=True)


engine.self_check = self_check


if __name__ == "__main__":
    raise SystemExit(engine.main())
