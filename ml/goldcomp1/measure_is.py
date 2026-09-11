"""GOLDブックの IS窓を測る（課題C3）。

goldcomp1 は FULL/OOS のみで走らせたため IS窓が欠けており、
X2_HIGH_RISK の要件定義で「GOLD側のIS窓は未測定」と明記せざるを得なかった。
ユーザー指示（2026-09-11）により IS窓を必ず併記する方針になったので埋める。

測るのは G001（現行構成・Gszラボ OFF・倍率1）のみ。
枠別の統計と合算ブックのt値を3窓そろえるのが目的。
"""
import csv
import json
from pathlib import Path

import measure as m

OUT = Path(__file__).resolve().parent / "results_is.csv"
IS_WINDOW = ("2021.06.21", "2026.06.20", 60.0)


def main():
    for d in (m.RUN_DIR, m.CONFIG_DIR, m.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    m._ea_sha = m.ea_sha()
    m.log(f"IS_START EA_SHA {m._ea_sha[:16]}")

    # WINDOWS に IS を足してから G001 を回す
    m.WINDOWS["IS"] = IS_WINDOW

    props = {r["proposal_id"]: r for r in
             csv.DictReader(open(m.ROOT / "proposals.csv", encoding="utf-8"))}
    prop = props["G001"]

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        row = m.run(prop, "IS")
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=m.FIELDS)
        w.writeheader()
        w.writerow({k: row.get(k, "") for k in m.FIELDS})
    m.log(f"IS_END status={row.get('status')} net={row.get('net')} -> {OUT}")


if __name__ == "__main__":
    main()
