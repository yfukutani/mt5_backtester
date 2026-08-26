"""Verify that OANDA SIMVERIFY is behavior-identical to the production EA.

The production EA writes only ``time,profit``.  The SIMVERIFY EA writes the
expanded FILE_COMMON schema, so the cross-EA SHA gate uses a canonical
``time,profit`` projection.  The raw expanded-file SHA is also recorded as the
future default-OFF baseline for the proposal driver.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "oafx_dd"
DEALS = ROOT / "deals"
OUTPUT = ROOT / "regression_gate.json"
EA = REPO / "experts" / "MIX_EA_OANDA_SIMVERIFY.mq5"

SCHEMA = [
    "time", "profit", "magic", "entry", "position_id", "type", "volume",
    "price", "sl", "usdjpy", "profit_jpy",
]
MAGICS = {
    "En_PB_USDJPY": 20260622,
    "En_PB_GBPJPY": 20260627,
    "En_RSI_USDJPY": 20260610,
    "En_RSI_EURUSD": 20260605,
    "En_RSI_GBPUSD": 20260774,
    "En_PAIR": 20260629,
    "En_CARRY": 20260650,
    "En_SCA_USDJPY": 20261000,
    "En_SCA_GBPJPY": 20261001,
}
WINDOWS = {
    "IS": {
        "production_summary": REPO / "results" / "oafx_regression_prod_is" / "summary.csv",
        "simverify_summary": REPO / "results" / "oafx_regression_simverify_is_v2" / "summary.csv",
        "production_deals": DEALS / "oafx_regression_prod_is_deals.csv",
        "simverify_deals": DEALS / "oafx_regression_simverify_is_deals.csv",
        "saved_reference": {"net": "277106.0", "pf": "1.3945", "dd_pct": "35.6479", "trades": "1573"},
    },
    "FULL": {
        "production_summary": REPO / "results" / "oafx_regression_prod_full" / "summary.csv",
        "simverify_summary": REPO / "results" / "oafx_regression_simverify_full" / "summary.csv",
        "production_deals": DEALS / "oafx_regression_prod_full_deals.csv",
        "simverify_deals": DEALS / "oafx_regression_simverify_full_deals.csv",
        "saved_reference": {"net": "390740.0", "pf": "1.3163", "dd_pct": "30.7523", "trades": "2926"},
    },
}
SUMMARY_KEYS = {
    "net": "純利益",
    "pf": "プロフィットファクター",
    "dd_pct": "最大相対DD%",
    "trades": "総取引数",
}


def read_summary(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        values = {row[0]: row[1] for row in csv.reader(handle) if len(row) >= 2}
    return {name: values[label] for name, label in SUMMARY_KEYS.items()}


def read_deals(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def projected_sha(rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["time", "profit"])
    writer.writerows((row["time"], row["profit"]) for row in rows)
    return hashlib.sha256(output.getvalue().encode("utf-8")).hexdigest().upper()


def main() -> int:
    report: dict[str, object] = {
        "status": "PASS",
        "ea_sha256": sha256(EA),
        "schema": SCHEMA,
        "windows": {},
    }
    failures: list[str] = []

    for window, cfg in WINDOWS.items():
        prod_summary = read_summary(cfg["production_summary"])
        sim_summary = read_summary(cfg["simverify_summary"])
        prod_schema, prod_rows = read_deals(cfg["production_deals"])
        sim_schema, sim_rows = read_deals(cfg["simverify_deals"])

        counts = {
            name: sum(int(row["magic"] or 0) == magic for row in sim_rows)
            for name, magic in MAGICS.items()
        }
        projection_prod = projected_sha(prod_rows)
        projection_sim = projected_sha(sim_rows)
        summary_match = prod_summary == sim_summary
        sequence_match = (
            len(prod_rows) == len(sim_rows)
            and all(
                left["time"] == right["time"] and left["profit"] == right["profit"]
                for left, right in zip(prod_rows, sim_rows)
            )
        )
        profit_jpy_match = all(
            Decimal(row["profit"]) == Decimal(row["profit_jpy"])
            for row in sim_rows
        )
        magic_gate = all(value > 0 for value in counts.values())
        saved = cfg["saved_reference"]
        saved_delta = {
            "net": str(Decimal(sim_summary["net"]) - Decimal(saved["net"])),
            "pf": str(Decimal(sim_summary["pf"]) - Decimal(saved["pf"])),
            "dd_pct": str(Decimal(sim_summary["dd_pct"]) - Decimal(saved["dd_pct"])),
            "trades": str(Decimal(sim_summary["trades"]) - Decimal(saved["trades"])),
        }

        checks = {
            "production_schema": prod_schema == ["time", "profit"],
            "simverify_schema": sim_schema == SCHEMA,
            "summary_match": summary_match,
            "row_count_match": len(prod_rows) == len(sim_rows),
            "time_profit_sequence_match": sequence_match,
            "projected_sha256_match": projection_prod == projection_sim,
            "magic_gate": magic_gate,
            "profit_jpy_is_account_jpy": profit_jpy_match,
        }
        for check, passed in checks.items():
            if not passed:
                failures.append(f"{window}:{check}")

        report["windows"][window] = {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "summary": sim_summary,
            "saved_reference": saved,
            "saved_reference_delta": saved_delta,
            "deal_rows": len(sim_rows),
            "production_deal_sha256": sha256(cfg["production_deals"]),
            "simverify_deal_sha256": sha256(cfg["simverify_deals"]),
            "projected_time_profit_sha256": projection_sim,
            "magic_rows": counts,
            "tester_forced_close_magic_zero_rows": sum(
                int(row["magic"] or 0) == 0 for row in sim_rows
            ),
        }

    if failures:
        report["status"] = "FAIL"
        report["failures"] = failures
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
