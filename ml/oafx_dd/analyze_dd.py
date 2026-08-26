"""Closed-deal drawdown source analysis for the OANDA nine-sleeve portfolio.

This is a diagnostic attribution only.  It does not remove trades or estimate
the performance of a hypothetical EA.  The curve is the initial JPY deposit
plus deal profits in the exact CSV order.  MT5's report DD can be larger because
it also observes floating equity between deal settlements.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
INITIAL_BALANCE = Decimal("77954")
INPUTS = {
    "IS": ROOT / "deals" / "oafx_regression_simverify_is_deals.csv",
    "FULL": ROOT / "deals" / "oafx_regression_simverify_full_deals.csv",
}
MAGICS = {
    20260622: "En_PB_USDJPY",
    20260627: "En_PB_GBPJPY",
    20260610: "En_RSI_USDJPY",
    20260605: "En_RSI_EURUSD",
    20260774: "En_RSI_GBPUSD",
    20260629: "En_PAIR",
    20260650: "En_CARRY",
    20261000: "En_SCA_USDJPY",
    20261001: "En_SCA_GBPJPY",
}


def stamp(value: int | None) -> str:
    if value is None:
        return "WINDOW_START"
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def num(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def load_deals(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.DictReader(handle))
    position_magic = {
        row["position_id"]: int(row["magic"])
        for row in raw
        if int(row["magic"] or 0) != 0
    }
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
        position_id = row["position_id"]
        magic = position_magic.get(position_id, int(row["magic"] or 0))
        if magic not in MAGICS:
            raise ValueError(f"unmapped magic={magic}, position_id={position_id}")
        rows.append({
            **row,
            "index": index,
            "time_i": int(row["time"]),
            "profit_d": Decimal(row["profit"]),
            "magic_i": magic,
            "sleeve": MAGICS[magic],
        })
    return rows


def maximum_drawdown(rows: list[dict[str, Any]], initial: Decimal) -> dict[str, Any]:
    balance = initial
    peak = initial
    peak_index = -1
    best = {
        "amount": Decimal(0), "peak": initial, "trough": initial,
        "peak_index": -1, "trough_index": -1,
    }
    for row in rows:
        balance += row["profit_d"]
        if balance > peak:
            peak = balance
            peak_index = row["index"]
        amount = peak - balance
        if amount > best["amount"]:
            best = {
                "amount": amount, "peak": peak, "trough": balance,
                "peak_index": peak_index, "trough_index": row["index"],
            }
    peak_time = None if best["peak_index"] < 0 else rows[best["peak_index"]]["time_i"]
    trough_time = None if best["trough_index"] < 0 else rows[best["trough_index"]]["time_i"]
    recovery_time = None
    if best["trough_index"] >= 0:
        running = initial + sum((r["profit_d"] for r in rows[: best["trough_index"] + 1]), Decimal(0))
        for row in rows[best["trough_index"] + 1:]:
            running += row["profit_d"]
            if running >= best["peak"]:
                recovery_time = row["time_i"]
                break
    return {
        **best,
        "pct_of_peak": best["amount"] / best["peak"] * 100 if best["peak"] else Decimal(0),
        "peak_time_i": peak_time,
        "trough_time_i": trough_time,
        "recovery_time_i": recovery_time,
        "ending_balance": balance,
    }


def make_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positions: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = positions.setdefault(row["position_id"], {
            "position_id": row["position_id"], "magic": row["magic_i"],
            "sleeve": row["sleeve"], "open": None, "close": None,
            "profit": Decimal(0), "type": None, "volume": None,
        })
        item["profit"] += row["profit_d"]
        if row["entry"] == "0":
            item["open"] = row["time_i"] if item["open"] is None else min(item["open"], row["time_i"])
            item["type"] = "BUY" if row["type"] == "0" else "SELL"
            item["volume"] = Decimal(row["volume"])
        elif row["entry"] == "1":
            item["close"] = row["time_i"] if item["close"] is None else max(item["close"], row["time_i"])
    incomplete = [p["position_id"] for p in positions.values() if p["open"] is None or p["close"] is None]
    if incomplete:
        raise ValueError(f"incomplete position intervals: {incomplete[:10]}")
    return list(positions.values())


def intervals_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["open"] < right["close"] and right["open"] < left["close"]


def standalone_sleeves(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for magic, sleeve in MAGICS.items():
        subset = [row for row in rows if row["magic_i"] == magic]
        curve = Decimal(0)
        peak = Decimal(0)
        peak_time = None
        best_amount = Decimal(0)
        best_peak_time = None
        best_trough_time = None
        for row in subset:
            curve += row["profit_d"]
            if curve > peak:
                peak = curve
                peak_time = row["time_i"]
            if peak - curve > best_amount:
                best_amount = peak - curve
                best_peak_time = peak_time
                best_trough_time = row["time_i"]
        gross_profit = sum((r["profit_d"] for r in subset if r["profit_d"] > 0), Decimal(0))
        gross_loss = sum((r["profit_d"] for r in subset if r["profit_d"] < 0), Decimal(0))
        output.append({
            "magic": magic, "sleeve": sleeve, "deal_rows": len(subset),
            "positions": len(subset) // 2, "net": sum((r["profit_d"] for r in subset), Decimal(0)),
            "gross_profit": gross_profit, "gross_loss": gross_loss,
            "standalone_max_dd": best_amount,
            "standalone_dd_pct_of_initial": best_amount / INITIAL_BALANCE * 100,
            "standalone_peak_time": stamp(best_peak_time),
            "standalone_trough_time": stamp(best_trough_time),
        })
    return output


def period_breakdown(rows: list[dict[str, Any]], dd: dict[str, Any]) -> list[dict[str, Any]]:
    interval = rows[dd["peak_index"] + 1: dd["trough_index"] + 1]
    output = []
    for magic, sleeve in MAGICS.items():
        subset = [row for row in interval if row["magic_i"] == magic]
        net = sum((r["profit_d"] for r in subset), Decimal(0))
        output.append({
            "magic": magic, "sleeve": sleeve, "deal_rows": len(subset),
            "net": net,
            "gross_profit": sum((r["profit_d"] for r in subset if r["profit_d"] > 0), Decimal(0)),
            "gross_loss": sum((r["profit_d"] for r in subset if r["profit_d"] < 0), Decimal(0)),
            "net_dd_share_pct": -net / dd["amount"] * 100 if dd["amount"] else Decimal(0),
        })
    return output


def overlap_attribution(positions: list[dict[str, Any]], dd: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start = dd["peak_time_i"]
    end = dd["trough_time_i"]
    if start is None or end is None:
        return {}, []
    closed = [p for p in positions if start < p["close"] <= end]
    losses = [p for p in closed if p["profit"] < 0]
    all_cross: dict[str, list[dict[str, Any]]] = {}
    co_loss: dict[str, list[dict[str, Any]]] = {}
    for item in losses:
        all_cross[item["position_id"]] = [
            other for other in positions
            if other["sleeve"] != item["sleeve"] and intervals_overlap(item, other)
        ]
        co_loss[item["position_id"]] = [
            other for other in losses
            if other is not item and other["sleeve"] != item["sleeve"] and intervals_overlap(item, other)
        ]

    pair_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"interval_pairs": 0, "overlap_seconds": 0, "allocated_loss": Decimal(0)}
    )
    for left_index, left in enumerate(losses):
        for right in losses[left_index + 1:]:
            if left["sleeve"] == right["sleeve"] or not intervals_overlap(left, right):
                continue
            pair = tuple(sorted((left["sleeve"], right["sleeve"])))
            pair_stats[pair]["interval_pairs"] += 1
            pair_stats[pair]["overlap_seconds"] += min(left["close"], right["close"]) - max(left["open"], right["open"])
    # Split each co-overlapped losing position once across its counterpart sleeve
    # types.  Therefore allocated_loss sums without duplication across pair rows.
    for item in losses:
        counterparts = sorted({other["sleeve"] for other in co_loss[item["position_id"]]})
        if not counterparts:
            continue
        share = -item["profit"] / len(counterparts)
        for counterpart in counterparts:
            pair = tuple(sorted((item["sleeve"], counterpart)))
            pair_stats[pair]["allocated_loss"] += share

    max_active = 0
    max_active_time = None
    events = []
    for item in positions:
        if item["open"] <= end and item["close"] >= start:
            events.append((max(item["open"], start), 1, item["position_id"]))
            events.append((min(item["close"], end), -1, item["position_id"]))
    active: set[str] = set()
    for event_time, event_type, position_id in sorted(events, key=lambda x: (x[0], x[1])):
        if event_type < 0:
            active.discard(position_id)
        else:
            active.add(position_id)
        if len(active) > max_active:
            max_active = len(active)
            max_active_time = event_time

    cross_yes = [p for p in losses if all_cross[p["position_id"]]]
    coloss_yes = [p for p in losses if co_loss[p["position_id"]]]
    summary = {
        "closed_positions": len(closed),
        "loss_positions": len(losses),
        "gross_loss": num(sum((p["profit"] for p in losses), Decimal(0))),
        "cross_sleeve_overlap_loss_positions": len(cross_yes),
        "cross_sleeve_overlap_gross_loss": num(sum((p["profit"] for p in cross_yes), Decimal(0))),
        "isolated_loss_positions": len(losses) - len(cross_yes),
        "isolated_gross_loss": num(sum((p["profit"] for p in losses if not all_cross[p["position_id"]]), Decimal(0))),
        "co_loss_overlap_positions": len(coloss_yes),
        "co_loss_overlap_gross_loss": num(sum((p["profit"] for p in coloss_yes), Decimal(0))),
        "not_co_loss_overlap_positions": len(losses) - len(coloss_yes),
        "not_co_loss_overlap_gross_loss": num(sum((p["profit"] for p in losses if not co_loss[p["position_id"]]), Decimal(0))),
        "max_concurrent_positions": max_active,
        "max_concurrent_time": stamp(max_active_time),
    }
    pairs = [{
        "sleeve_a": pair[0], "sleeve_b": pair[1],
        "interval_pairs": value["interval_pairs"],
        "overlap_hours": round(value["overlap_seconds"] / 3600, 4),
        "allocated_co_loss": num(value["allocated_loss"]),
    } for pair, value in pair_stats.items()]
    pairs.sort(key=lambda item: item["allocated_co_loss"], reverse=True)
    return summary, pairs


def worst_months(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    months: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        if row["profit_d"]:
            months[datetime.fromtimestamp(row["time_i"], timezone.utc).strftime("%Y-%m")] += row["profit_d"]
    return [{"month": month, "net": num(net)} for month, net in sorted(months.items(), key=lambda x: x[1])[:limit]]


def sca_shape(positions: list[dict[str, Any]], sleeve: str) -> dict[str, Any]:
    subset = [p for p in positions if p["sleeve"] == sleeve]
    groups: dict[str, dict[str, list[Decimal]]] = {
        "direction": defaultdict(list), "volume": defaultdict(list),
        "hold": defaultdict(list), "entry_hour": defaultdict(list),
    }
    for item in subset:
        hold_seconds = item["close"] - item["open"]
        hold_bin = "lt_6h" if hold_seconds < 6 * 3600 else "6h_to_24h" if hold_seconds < 24 * 3600 else "ge_24h"
        groups["direction"][item["type"]].append(item["profit"])
        groups["volume"][str(item["volume"])].append(item["profit"])
        groups["hold"][hold_bin].append(item["profit"])
        groups["entry_hour"][str(datetime.fromtimestamp(item["open"], timezone.utc).hour)].append(item["profit"])
    result: dict[str, Any] = {}
    for dimension, buckets in groups.items():
        result[dimension] = [{
            "value": value, "positions": len(profits), "net": num(sum(profits, Decimal(0))),
            "gross_loss": num(sum((p for p in profits if p < 0), Decimal(0))),
        } for value, profits in sorted(buckets.items())]
    return result


def serialise_sleeve(item: dict[str, Any]) -> dict[str, Any]:
    return {key: num(value) if isinstance(value, Decimal) else value for key, value in item.items()}


def analyse(window: str, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = load_deals(path)
    positions = make_positions(rows)
    dd = maximum_drawdown(rows, INITIAL_BALANCE)
    sleeves = standalone_sleeves(rows)
    breakdown = period_breakdown(rows, dd)
    overlap, pairs = overlap_attribution(positions, dd)
    report = {
        "source": str(path.relative_to(ROOT)),
        "deal_rows": len(rows), "positions": len(positions),
        "net": num(sum((r["profit_d"] for r in rows), Decimal(0))),
        "closed_deal_max_dd": {
            "amount": num(dd["amount"]), "pct_of_peak": num(dd["pct_of_peak"]),
            "peak_balance": num(dd["peak"]), "trough_balance": num(dd["trough"]),
            "peak_time": stamp(dd["peak_time_i"]), "trough_time": stamp(dd["trough_time_i"]),
            "recovery_time": stamp(dd["recovery_time_i"]) if dd["recovery_time_i"] else "NOT_RECOVERED",
        },
        "max_dd_interval_breakdown": [serialise_sleeve(item) for item in sorted(breakdown, key=lambda x: x["net"])],
        "overlap_attribution": overlap,
        "worst_months": worst_months(rows),
        "sca_shape": {
            "En_SCA_GBPJPY": sca_shape(positions, "En_SCA_GBPJPY"),
            "En_SCA_USDJPY": sca_shape(positions, "En_SCA_USDJPY"),
        },
    }
    return report, [serialise_sleeve(item) | {"window": window} for item in sleeves], [item | {"window": window} for item in pairs]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    report: dict[str, Any] = {
        "method": "initial balance + profit in exact deal CSV order; diagnostic only",
        "initial_balance_jpy": num(INITIAL_BALANCE),
        "magic_zero_rule": "map forced tester exits to the non-zero magic of the same position_id",
        "overlap_rule": "strict positive holding-time intersection between different sleeves",
        "windows": {},
    }
    sleeves: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for window, path in INPUTS.items():
        window_report, window_sleeves, window_pairs = analyse(window, path)
        report["windows"][window] = window_report
        sleeves.extend(window_sleeves)
        pairs.extend(window_pairs)
    (ROOT / "dd_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(ROOT / "dd_sleeves.csv", sleeves)
    write_csv(ROOT / "dd_overlap_pairs.csv", pairs)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
