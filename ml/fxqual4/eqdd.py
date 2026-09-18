"""results.csv の各 run に、cap ログ側の equity DD（含み損込み）を横に並べて出す。

残高DD（`STAT_BALANCE_DDREL_PERCENT`）は建玉中の含み損を含まない。第16報で
両方を併記する運びになったので、ラウンドの判定表を作る前にここで突き合わせる。
引数でラウンドのディレクトリを渡す（既定は自分のディレクトリ）。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path


def eq_dd(cap_path: Path) -> str:
    try:
        for line in cap_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("equity_dd_pct"):
                return line.split(",")[5]
    except OSError:
        pass
    return ""


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    rows = list(csv.DictReader((root / "results.csv").open(encoding="utf-8")))
    base = {}
    for r in rows:
        if r["proposal_id"].endswith("000"):
            base[r["window"]] = r

    hdr = ("案", "窓", "純益", "Δ純益", "残高DD", "eqDD", "取引", "単利月利%")
    print("{:6}{:5}{:>10}{:>10}{:>8}{:>8}{:>7}{:>10}".format(*hdr))
    for r in sorted(rows, key=lambda x: (x["proposal_id"], x["window"])):
        cap = Path(r["deals"].replace("_deals.csv", "_cap.csv"))
        b = base.get(r["window"])
        d = float(r["net"]) - float(b["net"]) if b else 0.0
        print("{:6}{:5}{:>10.0f}{:>10.0f}{:>8.2f}{:>8}{:>7}{:>10.3f}".format(
            r["proposal_id"], r["window"], float(r["net"]), d,
            float(r["dd_pct"]), eq_dd(cap) or "-", r["trades"],
            float(r["monthly_pct"])))


if __name__ == "__main__":
    main()
