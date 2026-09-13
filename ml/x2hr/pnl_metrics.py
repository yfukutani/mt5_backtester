"""V088：**損益・想定月利・最大ドロップダウン**（簡易検証・2026-09-13）。

【ユーザー指示（2026-09-13）】
> 報告の際は**損益、想定月利、最大ドロップダウン**も記載するようにしてください。
> これもプロジェクトのルールとして記載してください。

`CLAUDE.md`「報告に必ず含める数値」に記載済み。本スクリプトはその数値を出す。

【測るもの】
弱局面の実履歴（起点＋期限 ≤ 2020-01-01）とIS窓で、期限ごとに——

| 項目 | 定義 |
|---|---|
| **損益** | 期末（または到達／破綻時点）の資金 − 初期資金10万円 |
| **想定月利** | `(期末資金/初期資金)^(1/月数) − 1`（**複利**）。到達で打ち切った経路は到達月数で割る |
| **最大DD** | 経路上の「それまでの最高資金からの落ち込み」の最大値（%） |

**中央値・平均・最悪値をすべて出す。1つの数字にまとめない。**

【重要な限界】
- **最大DDは確定損益ベースであり、含み損を含まない。実際の最大DDはこれより深い。**
- 到達（2倍）または破綻（10%）で経路を打ち切るので、**打ち切り後の値動きは反映されない**
- 到達した経路と未達の経路では月数が違う。**月利の分布は両者を混ぜている**
- 証拠金不足による強制決済を扱っていない
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import bisect
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_aware_sizing as das
import policy_decomposition as pd
import target_policy_gap as tpg

CAPITAL = co.CAPITAL
MIN_LOT = co.MIN_LOT
STEP = co.STEP
RUIN = co.RUIN
MULT = 2.0
QUIET_END = tpg.QUIET_END
CAP = 3.0
H_POL = 0.48


def run_path(rec, ti, t0, t_end, k, pol, cap):
    """1経路を走らせ、(到達, 破綻, 期末資金, 最大DD%, 経過月数) を返す。"""
    i0 = bisect.bisect_left(ti, t0)
    i1 = bisect.bisect_left(ti, t_end)
    span = float(t_end - t0)
    eq = CAPITAL
    peak = CAPITAL
    mdd = 0.0
    pend, pi, ei = [], 0, i0
    t_last = t0
    while ei < i1 or pi < len(pend):
        t_ev = rec[ei][0] if ei < i1 else None
        if pi < len(pend):
            pend[pi:] = sorted(pend[pi:])
            t_pd = pend[pi][0]
        else:
            t_pd = None
        if t_pd is not None and (t_ev is None or t_pd <= t_ev):
            t, m, profit = pend[pi]
            pi += 1
            if t > t_end:
                continue
            eq += profit * m
            t_last = t
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak)
            if eq >= CAPITAL * MULT:
                return True, False, eq, mdd, (t - t0) / (30.44 * 86400)
            if eq <= CAPITAL * RUIN:
                return False, True, eq, mdd, (t - t0) / (30.44 * 86400)
        else:
            t_in, t_out, profit, vol = rec[ei]
            ei += 1
            ratio = eq / CAPITAL
            mk = k * ratio
            if pol is not None:
                tau = max(t_end - t_in, 0) / span
                mk *= pol.mult(math.log(max(ratio, 1e-6)), tau, cap)
            actual = max(MIN_LOT, math.floor(vol * mk / STEP + 1e-9) * STEP)
            pend.append((t_out, actual / vol, profit))
    return False, False, eq, mdd, (t_end - t0) / (30.44 * 86400)


def collect(rec, origins, k, pol, cap, months):
    ti = [x[0] for x in rec]
    rows = []
    for d in origins:
        t_end = cod.add_months(d, months)
        rows.append(run_path(rec, ti, int(d.timestamp()),
                             int(t_end.timestamp()), k, pol, cap))
    return rows


def summarize(rows, months):
    """想定月利は**期限 months に対する複利**で揃える。

    到達までの実日数で割ると、数日で2倍になった経路が月利数百%になり平均が壊れる
    （実際にV088の最初の実行で 1787%/月 が出た）。到達したら資金はそのまま置く
    前提で、**期限全体に対する月利**に揃える。到達の速さは別途「到達までの月数」で出す。
    """
    n = len(rows)
    pnl = np.array([r[2] - CAPITAL for r in rows])
    mdd = np.array([100.0 * r[3] for r in rows])
    mret = np.array([
        -100.0 if eq <= 0 else
        100.0 * ((eq / CAPITAL) ** (1.0 / months) - 1.0)
        for _, _, eq, _, _ in rows])
    reach_mo = [mo for hit, _, _, _, mo in rows if hit]
    return {
        "n": n,
        "reach": 100.0 * sum(r[0] for r in rows) / n,
        "ruin": 100.0 * sum(r[1] for r in rows) / n,
        "neg": sum(1 for r in rows if r[2] < 0),
        "pnl_med": float(np.median(pnl)),
        "pnl_mean": float(pnl.mean()),
        "pnl_min": float(pnl.min()),
        "mr_med": float(np.median(mret)),
        "mr_mean": float(mret.mean()),
        "mr_min": float(mret.min()),
        "dd_med": float(np.median(mdd)),
        "dd_mean": float(mdd.mean()),
        "dd_max": float(mdd.max()),
        "reach_mo": float(np.median(reach_mo)) if reach_mo else float("nan"),
    }


def main():
    print("=" * 126)
    print("V088：損益・想定月利・最大ドロップダウン（簡易検証）")
    print("=" * 126)
    print("★ ユーザー指示により、報告には損益・想定月利・最大DDを必ず含める")
    print("  （`CLAUDE.md`「報告に必ず含める数値」）。\n")
    print(f"  資金 {CAPITAL:,.0f}円・目標2倍・破綻ライン{100*RUIN:.0f}%・最小ロット制約あり")
    print("  想定月利は**複利**。到達で打ち切った経路は到達までの月数で割っている。\n")
    print("> [!warning] **最大DDは確定損益ベースであり、含み損を含まない。**")
    print("> **実際の最大DDはこれより深い。** 証拠金不足による強制決済も扱っていない。\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    base = das.Policy(H=H_POL)
    hjb = pd.HJB(base)

    def origins(st, cap_end, D, step=7):
        out, d = [], st
        while cod.add_months(d, D) <= cap_end:
            out.append(d)
            d += timedelta(days=step)
        return out

    for wname, rec, st, cap_end in (
            ("OOS 弱局面（〜2020-01）", data["OOS"], a_oos, QUIET_END),
            ("IS窓（2021-06〜2026-06）", data["IS"], a_is, b_is)):
        for D, kk in ((6, 4.0), (12, 2.0)):
            og = origins(st, cap_end, D)
            print("=" * 126)
            print(f"【{wname}・期限{D}ヶ月・k={kk:.0f}】起点{len(og)}本")
            print("=" * 126)
            print(f"{'方策':<20}{'到達':>7}{'破綻':>7}{'到達月数':>9}"
                  f"│{'損益 中央':>11}{'損益 平均':>11}{'損益 最悪':>11}"
                  f"│{'月利 中央':>10}{'月利 平均':>10}{'月利 最悪':>10}"
                  f"│{'最大DD 中央':>12}{'最大DD 平均':>12}{'最大DD 最悪':>12}"
                  f"{'資金<0':>8}")
            for label, p in (("比例方策（基準）", None), ("**HJB期限意識**", hjb)):
                s = summarize(collect(rec, og, kk, p, CAP, D), D)
                print(f"{label:<20}{s['reach']:>6.1f}%{s['ruin']:>6.1f}%"
                      f"{s['reach_mo']:>9.1f}"
                      f"│{s['pnl_med']:>11,.0f}{s['pnl_mean']:>11,.0f}"
                      f"{s['pnl_min']:>11,.0f}"
                      f"│{s['mr_med']:>9.2f}%{s['mr_mean']:>9.2f}%"
                      f"{s['mr_min']:>9.2f}%"
                      f"│{s['dd_med']:>11.1f}%{s['dd_mean']:>11.1f}%"
                      f"{s['dd_max']:>11.1f}%{s['neg']:>8}")
            print()

    print("=" * 126)
    print("【限界】")
    print("=" * 126)
    print("  ・**最大DDは確定損益ベース。含み損を含まないので実際はこれより深い**")
    print("  ・**『資金<0』の列は、1回の決済で資金がマイナスまで突き抜けた経路の本数。**")
    print("    実際には証拠金不足で強制決済されるので、この経路の損益は現実的でない。")
    print("    最大DDが100%を超えるのもこのため。**方策の攻めが強いほど増える**")
    print("  ・想定月利は**期限全体に対する複利**に揃えている。到達までの実日数で")
    print("    割ると、数日で2倍になった経路が月利数百%になり平均が壊れるため")
    print("  ・到達（2倍）または破綻（10%）で経路を打ち切るため、打ち切り後は反映されない")
    print("  ・到達経路と未達経路で月数が違う。**月利の分布は両者を混ぜている**")
    print("  ・証拠金不足による強制決済を扱っていない")
    print("  ・起点が重なるため独立ではない")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
