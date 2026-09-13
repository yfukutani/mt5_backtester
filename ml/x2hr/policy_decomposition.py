"""V086：**期限意識サイジングの分解**（簡易検証・2026-09-13）。

【Codexの指摘（2026-09-13）— 実装上の重大な誤り】

> 提示のHJBでは、全期限 T、実時間での資金リターンのボラ a、そのシャープ率 θ に対し
>
>     u = a·√T,  H = θ·√T,  τ = (T − t)/T
>
> という**固定の時間単位への変換**で、提示の方程式になる。
> したがって HJB の `u*(x,τ)` を実時間のボラへ戻す変換は **`u*/√T`** である。
> **ここに追加の `1/√τ` は出ない。**
>
> 実際、提示表の x=0 では残り時間が 1→0.25 で方策自体が 1.71/0.78 ≒ 2.19倍になる。
> V083はさらに2倍し、クリップ前で約4.38倍にしている。
>
> **V083が検証したのは、HJB方策そのものではなく
> 「HJB由来の形＋追加の時間増幅＋クリップ」という別の方策である。**
> 別方策として有効な可能性はあるが、**V080の最適性を根拠にできない。**

**この指摘は正しい。V083の式は誤りだった。**

【本スクリプトで分解する（Codexの推奨どおり）】

同じ起点・同じ取引列で、次の5つを並べる。

| 記号 | 倍率 | 意味 |
|---|---|---|
| **P** | 1（なし） | 比例一定k（基準） |
| **T** | `min(cap, 1/√τ)` | 時間増幅のみ（x非依存） |
| **H** | `min(cap, u*(x,τ)/u*(0,1))` | **HJB方策そのもの（追加増幅なし）** |
| **V083** | `min(cap, [u*(x,τ)/u*(0,1)]/√τ)` | V083の式（誤り。参考として残す） |
| **X** | `min(cap, u*(0,τ)/u*(0,1))` | HJBの時間方向のみ（x固定） |

**H が P を大きく上回るなら、HJBの形そのものに価値がある。**
**H が P と変わらず V083 だけが効くなら、効いているのは「攻めを強めたこと」であり、
V080の最適性は根拠にならない。**

**到達率だけでなく破綻率も併記する**（Codexの指摘：6月k=4は到達+38.4ptだが破綻も+14.5pt）。

【非重複起点の修正（Codexの指摘）】
V084の `D*30` 日刻みは暦月と一致せず重なりが残っていた。
**前の窓の終了日時を次の起点にする**よう修正した。

【限界（Codexの指摘を反映）】
- 履歴再生は決済時にしか資金を動かさない。**含み損益・期限時の残存建玉・
  証拠金不足による強制決済を扱っていない。** 期限直前に増額する方策では特に重大
- 「比例はkをどう選んでも最大◯%」とは言えない。**試したkの範囲・刻みでの最大値**
- H=0.48 を弱局面OOSから推定した以上、**この方策について未使用OOSではない**
- 138起点は138回の独立試行ではない。弱局面は約3年で、非重複6ヶ月窓は約6本
- 最小ロット制約は**増やす側だけに効く非対称な制約**で、「目標付近で守る」を消す
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_aware_sizing as das
import deadline_committed as dc
import target_policy_gap as tpg

QUIET_END = tpg.QUIET_END
K_SHOW = [2.0, 4.0, 8.0, 16.0]
DEADLINES = [6, 12]
CAP = 3.0
H_POL = 0.48


class TimeOnly:
    """T：時間増幅のみ min(cap, 1/√τ)。x に依存しない。"""

    def mult(self, x, tau, cap):
        return min(1.0 / math.sqrt(min(max(tau, 1e-4), 1.0)), cap)


class HJB:
    """H：HJB方策そのもの min(cap, u*(x,τ)/u*(0,1))。**追加の 1/√τ なし。**"""

    def __init__(self, pol, x_fixed=False):
        self.p = pol
        self.x_fixed = x_fixed

    def mult(self, x, tau, cap):
        tau = min(max(tau, 1e-4), 1.0)
        j = int(np.clip(np.searchsorted(self.p.taus, tau),
                        0, len(self.p.taus) - 1))
        xx = 0.0 if self.x_fixed else x
        u = float(np.interp(xx, self.p.xs, self.p.tab[j]))
        return min(u / self.p.u_ref, cap)


def nonoverlap_origins(start, end_cap, months):
    """**前の窓の終了日時を次の起点にする**（暦月で正しく非重複にする）。"""
    out, d = [], start
    while cod.add_months(d, months) <= end_cap:
        out.append(d)
        d = cod.add_months(d, months)
    return out


def run_origins(rec, origins, k, pol, cap, months):
    ti = [x[0] for x in rec]
    hit = ruin = 0
    for d in origins:
        t_end = cod.add_months(d, months)
        h, r = dc.simulate(rec, ti, int(d.timestamp()), int(t_end.timestamp()),
                           k, pol, cap)
        hit += h
        ruin += r
    n = len(origins)
    return (hit / n if n else 0.0), (ruin / n if n else 0.0), n


def all_origins(start, end_cap, months, step_days=7):
    from datetime import timedelta
    out, d = [], start
    while cod.add_months(d, months) <= end_cap:
        out.append(d)
        d += timedelta(days=step_days)
    return out


def main():
    print("=" * 118)
    print("V086：期限意識サイジングの分解（簡易検証）")
    print("=" * 118)
    print("★ Codexの指摘により、V083の `1/√τ` は**二重増幅の誤り**と判明。")
    print("  HJBの u*(x,τ) は既に率なので、実ロットへの変換は u*/√T（定数）。")
    print("  **V083が測ったのはHJB方策ではなく、より攻撃的な別方策だった。**\n")
    print("  ここで5つの方策を同じ起点・同じ取引列で分解する。")
    print("  **到達率だけでなく破綻率も併記する。**\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    base = das.Policy(H=H_POL)

    pols = [
        ("P 比例（基準）", None),
        ("T 時間のみ 1/√τ", TimeOnly()),
        ("**H HJB方策そのもの**", HJB(base)),
        ("X HJBの時間方向のみ", HJB(base, x_fixed=True)),
        ("V083の式（誤り・参考）", base),
    ]

    for wname, rec, st, cap_end in (
            ("OOS 弱局面（〜2020-01）", data["OOS"], a_oos, QUIET_END),
            ("IS窓（2021-06〜2026-06）", data["IS"], a_is, b_is)):
        for D in DEADLINES:
            og = all_origins(st, cap_end, D)
            print("=" * 118)
            print(f"【{wname}・期限{D}ヶ月】起点{len(og)}（7日刻み・重なりあり）"
                  f"・上限{CAP:.0f}倍・H={H_POL}")
            print("=" * 118)
            print(f"{'方策':<26}" + "".join(
                f"{f'k={k:.0f} 到達':>11}{f'破綻':>8}" for k in K_SHOW))
            for label, p in pols:
                cells = ""
                for k in K_SHOW:
                    h, r, _ = run_origins(rec, og, k, p, CAP, D)
                    cells += f"{100*h:>10.1f}%{100*r:>7.1f}%"
                print(f"{label:<26}{cells}")
            print()

    # ---------- 非重複起点（正しく非重複） ----------
    print("=" * 118)
    print("【非重複起点】**前の窓の終了日時を次の起点にする**（Codexの指摘で修正）")
    print("=" * 118)
    for wname, rec, st, cap_end in (
            ("OOS 弱局面", data["OOS"], a_oos, QUIET_END),
            ("IS窓", data["IS"], a_is, b_is)):
        for D in DEADLINES:
            og = nonoverlap_origins(st, cap_end, D)
            print(f"\n--- {wname}・期限{D}ヶ月・**起点{len(og)}本** ---")
            print(f"{'方策':<26}" + "".join(
                f"{f'k={k:.0f} 到達':>11}{f'破綻':>8}" for k in K_SHOW))
            for label, p in pols:
                cells = ""
                for k in K_SHOW:
                    h, r, _ = run_origins(rec, og, k, p, CAP, D)
                    cells += f"{100*h:>10.1f}%{100*r:>7.1f}%"
                print(f"{label:<26}{cells}")

    print("\n" + "=" * 118)
    print("【読み方】")
    print("=" * 118)
    print("  ・**H が P を大きく上回るなら、HJBの形そのものに価値がある**")
    print("  ・H が P と変わらず V083 だけ効くなら、効いているのは『攻めを強めたこと』で、")
    print("    **V080の最適性は根拠にならない**")
    print("  ・T と X の比較で、x依存が必要かが分かる")
    print("  ・**到達と破綻は組で見る。** 到達が上がっても破綻が同じだけ上がるなら価値は薄い")

    print("\n" + "=" * 118)
    print("【限界】Codexの指摘を反映")
    print("=" * 118)
    print("  ・履歴再生は決済時にしか資金を動かさない。**含み損益・期限時の残存建玉・")
    print("    証拠金不足による強制決済を扱っていない。** 期限直前に増額する方策では特に重大")
    print("  ・『比例はkをどう選んでも最大◯%』とは言えない。**試したkの範囲での最大値**")
    print("  ・H=0.48 を弱局面OOSから推定した以上、**この方策について未使用OOSではない**")
    print("  ・138起点は138回の独立試行ではない。弱局面は約3年で非重複6ヶ月窓は約6本")
    print("  ・最小ロット制約は**増やす側だけに効く非対称な制約**")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
