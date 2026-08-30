"""Enumerate all 256 trade-off subsets from the saved full-period deal streams."""
from __future__ import annotations

import itertools
from pathlib import Path

import pandas as pd

from run_tradeoff8 import CHANGES, DEALS, PORTFOLIO, ROOT


def read(run: str) -> pd.DataFrame:
    x = pd.read_csv(DEALS / f"{run}.csv")
    x.columns = [c.strip().lower() for c in x.columns]
    x["time"] = pd.to_numeric(x["time"], errors="coerce")
    x["profit"] = pd.to_numeric(x["profit"], errors="coerce")
    return x.dropna(subset=["time", "profit"])[["time", "profit"]]


def main() -> None:
    streams = {}
    for name in PORTFOLIO:
        stem = Path(name).stem
        streams[(name, False)] = read(f"t8_pf_baseline_{stem}")
        if name in CHANGES:
            streams[(name, True)] = read(f"t8_pf_candidate_{stem}")
    changed = list(CHANGES)
    rows = []
    for bits in itertools.product([False, True], repeat=len(changed)):
        selected = {name for name, bit in zip(changed, bits) if bit}
        frames, single_dd = [], []
        for name in PORTFOLIO:
            df = streams[(name, name in selected)]
            frames.append(df)
            leg_eq = pd.concat([pd.Series([100000.0]),
                                100000.0 + df.sort_values("time")["profit"].cumsum()], ignore_index=True)
            single_dd.append(float((leg_eq.cummax() - leg_eq).max()))
        deals = pd.concat(frames, ignore_index=True).sort_values("time", kind="stable")
        eq = pd.concat([pd.Series([1500000.0]), 1500000.0 + deals.profit.cumsum()], ignore_index=True)
        peak = eq.cummax(); dd = peak - eq
        max_abs = float(dd.max()); max_pct = float((dd / peak).max() * 100); net = float(deals.profit.sum())
        dd_sum = sum(single_dd)
        rows.append({"selected_ids": "+".join(CHANGES[n][0] for n in changed if n in selected) or "none",
                     "count": len(selected), "net": net, "max_dd_abs": max_abs, "max_dd_pct": max_pct,
                     "return_dd_pct": net / max_pct, "return_dd_abs": net / max_abs,
                     "diversification_abs": dd_sum - max_abs,
                     "diversification_pct": (1 - max_abs / dd_sum) * 100})
    pd.DataFrame(rows).to_csv(ROOT / "subset_results.csv", index=False)


if __name__ == "__main__":
    main()
