"""ファミリー×パラメータ水準ごとの応答を表にする。

採用/不採用の二値ではなく「どちらへどれだけ動いたか」を見るためのもの。
単調な応答が出ていれば結果はノイズではなく構造的な効果である。
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_IS = {"net": 417882.0, "dd": 3.7942, "trades": 301}

KEYS = ["PprotArmPeakATR", "PprotArmPeakR", "PprotBELockATR", "PprotBELockR",
        "PprotTrailATR", "PprotTrailPeakATR", "PprotGivebackFrac", "PprotGivebackATR",
        "PprotArmAfterBars", "PprotArmBeforeBars", "PprotTightenBars", "PprotTightenSLATR",
        "PprotArmMinATRRatio", "PprotArmMaxATRRatio", "PprotArmHourStart",
        "PprotPartialLots", "PprotTPExtendATR", "PprotFridayHour", "PprotFridayMinATR"]
OFF = {"PprotArmPeakATR": 0.0, "PprotArmPeakR": 0.0, "PprotBELockATR": -9.0,
       "PprotBELockR": -9.0, "PprotTrailATR": 0.0, "PprotTrailPeakATR": 0.0,
       "PprotGivebackFrac": 0.0, "PprotGivebackATR": 0.0, "PprotArmAfterBars": 0,
       "PprotArmBeforeBars": 0, "PprotTightenBars": 0, "PprotTightenSLATR": 0.0,
       "PprotArmMinATRRatio": 0.0, "PprotArmMaxATRRatio": 0.0, "PprotArmHourStart": -1,
       "PprotPartialLots": 0.0, "PprotTPExtendATR": 0.0, "PprotFridayHour": -1,
       "PprotFridayMinATR": 0.0}


def main():
    props = {p["proposal_id"]: p for p in csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8"))}
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["window"] == "IS" and r["status"] == "OK"]
    latest = {r["proposal_id"]: r for r in rows}

    by_fam_target = defaultdict(list)
    for pid, r in latest.items():
        p = props[pid]
        by_fam_target[(p["family"], p["target_name"])].append((pid, r, json.loads(p["parameter_json"])))

    for (fam, target) in sorted(by_fam_target):
        items = by_fam_target[(fam, target)]
        active = [k for k in KEYS if any(v.get(k, OFF[k]) != OFF[k] for _, _, v in items)]
        print(f"\n{'='*92}")
        print(f"{fam}  /  {target}   測定 {len(items)} 件   可変: {', '.join(active) or '(なし)'}")
        print(f"{'案':<9}{'  '.join(f'{k[5:]:>13}' for k in active)}"
              f"{'純益':>12}{'対基準%':>10}{'DD%':>9}{'DD差pt':>9}{'取引':>7}  判定")
        items.sort(key=lambda x: tuple(x[2].get(k, 0) or 0 for k in active))
        for pid, r, v in items:
            cells = "  ".join(f"{v.get(k, OFF[k]):>13}" for k in active)
            print(f"{pid:<9}{cells}"
                  f"{float(r['net']):>12,.0f}{100*(float(r['net_ratio'])-1):>9.2f}%"
                  f"{float(r['dd_pct']):>9.3f}{float(r['dd_delta']):>9.3f}"
                  f"{r['trades']:>7}  {r['decision']}")


if __name__ == "__main__":
    main()
