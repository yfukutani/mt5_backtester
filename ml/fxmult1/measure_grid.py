"""倍率を刻んで実測し、「月利+1ポイント」に必要な倍率とそのDDを確定する。

【なぜ刻むのか】x1 の deal ログを n 倍しても x4 にはならない。PB/Carry が risk sizing で
ロットステップの丸めが入り、x1 では丸めで落ちる割合が大きいため超線形になる
（実測: IS x4 で +15.3% / x8 で +17.2% / OOS x4 で +7.5%）。内挿もできないので
必要な倍率を直接測る。

【現状】x1 は入金50万に対し円建てDDが FULL窓 9.7% しか使っていない。
XM側は x4 で 25.8% を使っており、FX側は明らかに過小。OOS窓の x4 で月利 +1.43ポイント。
"""
import csv
from pathlib import Path

import measure as m

OUT = Path(__file__).resolve().parent / "results_grid.csv"


def main():
    for d in (m.RUN_DIR, m.CONFIG_DIR, m.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    m._ea_sha = m.ea_sha()
    m.log(f"EA_SHA {m._ea_sha[:16]}")

    # 既測定は x1(3窓) / IS x4,x8 / OOS x4。足りない刻みだけ回す。
    jobs = [(2, "FULL"), (3, "FULL"), (4, "FULL"),
            (2, "OOS"), (3, "OOS"),
            (2, "IS"), (3, "IS"),
            (5, "FULL"), (6, "FULL")]

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        m.log(f"GRID_START jobs={len(jobs)}")
        for mult, window in jobs:
            results.append(m.run(mult, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = (["mult", "window", "status", "net", "pf", "dd_pct", "monthly_pct",
               "trades", "deals", "elapsed", "run_id"]
              + [f"{k}_{s}" for k in m.MAGICS.values() for s in ("net", "n")])
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})
    ok = sum(1 for r in results if r.get("status") == "OK")
    m.log(f"GRID_END rows={len(results)} ok={ok} -> {OUT}")


if __name__ == "__main__":
    main()
