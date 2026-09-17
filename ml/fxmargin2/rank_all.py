"""測定済みの全案に A10（証拠金上限）を掛け、実行可能なものだけを順位づける（段階2）。

ユーザー指示は「すべての案を検証」である。`margin_cap_sim.py` は個別の応答曲線を見るためのもので、
本スクリプトは **dealログのある全案 × 全cap** を一度に回して、

  1. `stopout_bound.py` の**保証側**（最悪維持率 ≥ 100%＝追証を割らない）を満たすものだけを残し、
  2. OOS月利で順位づけ、
  3. FULL窓でも同じ順位になるかを併記する

ことで、「OOS窓を見て一番良いものを選んだ」たぐいの選択を可視化する。

**段階2の簡易検証。採用の最終判断は MT5 バックテストで行う。**
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import margin_cap_sim as M
import stopout_bound as B


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", default="1.0,0.9,0.85,0.8,0.75,0.7,0.6,0.5")
    ap.add_argument("--min-level", type=float, default=1.0,
                    help="採用する最悪維持率の下限（1.0＝追証ラインを割らない）")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[2]
    caps = [None] + [float(c) for c in args.caps.split(",")]

    ids = []
    for r in csv.DictReader(open(repo / "ml/fxrisk3/results.csv", encoding="utf-8")):
        if r["proposal_id"] not in ids:
            ids.append(r["proposal_id"])

    rows = []
    for pid in ids:
        params, desc = M.params_of(repo, pid)
        comp = M.compounding_magics(params)
        oos = M.load(repo, pid, "oos")
        full = M.load(repo, pid, "full")
        if not oos or not full:
            continue
        for cap in caps:
            so = B.run(oos, comp, cap)
            if so["worst_level"] < args.min_level:
                continue                      # 保証側を満たさない＝採らない
            s = M.simulate(oos, comp, cap)
            g, med, d3 = M.geo_monthly(s["monthly"])
            sf = M.simulate(full, comp, cap)
            gf, _, d3f = M.geo_monthly(sf["monthly"])
            sof = B.run(full, comp, cap)
            rows.append({
                "pid": pid, "cap": cap, "desc": desc,
                "oos_net": s["net"], "oos_m": g, "oos_med": med, "oos_d3": d3,
                "oos_dd": s["dd"] * 100, "oos_min": s["min_eq"],
                "oos_lv": so["worst_level"] * 100, "oos_lot": s["max_lot"],
                "full_m": gf, "full_d3": d3f, "full_dd": sf["dd"] * 100,
                "full_lv": sof["worst_level"] * 100,
            })

    rows.sort(key=lambda r: -r["oos_m"])
    print("A10つき全案ランキング（OOS月利順・最悪維持率 %.0f%% 以上のものだけ）"
          % (args.min_level * 100))
    print("最悪維持率はSLまで逆行した上界。OANDA証券MT5は100%で追証・50%でロスカット。")
    print("段階2の簡易検証であり、MT5未確認。\n")
    print("%-6s %5s %11s %7s %7s %8s %7s %9s %6s %7s | %7s %8s %7s %6s"
          % ("案", "cap", "OOS純益", "OOS月利", "中央値", "上位3除外", "OOS DD",
             "最低資産", "維持率", "最大lot", "FULL月利", "上位3除外", "FULL DD", "維持率"))
    for r in rows[:30]:
        cap = "無制限" if r["cap"] is None else "%.0f%%" % (r["cap"] * 100)
        print("%-6s %5s %11s %6.2f%% %6.2f%% %7.2f%% %6.1f%% %9s %5.0f%% %7.2f | %6.2f%% %7.2f%% %6.1f%% %5.0f%%"
              % (r["pid"], cap, format(round(r["oos_net"]), ","), r["oos_m"],
                 r["oos_med"], r["oos_d3"], r["oos_dd"], format(round(r["oos_min"]), ","),
                 r["oos_lv"], r["oos_lot"], r["full_m"], r["full_d3"],
                 r["full_dd"], r["full_lv"]))
    print("\n採用候補は %d 件（%d 案 × cap を評価し、保証側を満たしたもの）"
          % (len(rows), len(ids)))
    print("注: 順位は OOS 窓で付けている。OOS を見て最良を選ぶこと自体が選択バイアスである")
    print("    （Codex #44/#46）。FULL 側の列と見比べ、両窓で上位のものを選ぶこと。")

    out = repo / "ml/fxmargin2/rank_all.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("→ %s" % out)


if __name__ == "__main__":
    main()
