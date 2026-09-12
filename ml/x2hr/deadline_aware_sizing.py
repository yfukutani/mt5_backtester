"""V082：**期限を意識したサイジングを実履歴で測る**（簡易検証・2026-09-13）。

【この検証の位置づけ】
`CLAUDE.md`「戦略検証の進め方」の**段階2（簡易検証）の後半**。
V080（拡散近似のHJB）で見込みが立ったので、**同じ方策を実際の取引履歴に当てる。**
**それでも段階2である。採用の根拠にはならない。** 通れば段階3（MT5バックテスト）へ。

【V080で分かったこと】
V078は「**一定の** 期限ボラ u」しか解いていなかった。
残り時間 τ と対数資金 x に依存する `u*(x, τ)` を解くと——

| H | 一定uの天井 | **最適制御** | 改善 |
|---:|---:|---:|---:|
| 0.48（弱局面6ヶ月） | 58.5% | **65.6%** | **+7.4pt** |
| 0.68（弱局面12ヶ月） | 63.8% | **72.5%** | +9.0pt |
| 1.32 | 80.2% | **89.0%** | +9.1pt |

**必要な期限シャープ：方針A 0.80→0.50、方針B 2.00→1.40。**

最適方策の形（H=0.48・u上限8）：

| 残り時間 | x=−1.50 | x=−0.50 | x=0.00 | x=+0.50 |
|---:|---:|---:|---:|---:|
| 0.25 | 2.42 | 2.31 | 1.71 | 0.69 |
| 1.00 | 1.10 | 1.06 | 0.78 | 0.32 |

**① 残り時間が減るほど大きく張る（これが新しい軸）**
**② 資金が目標に近づくほど小さく張る（守りに入る）**

**V058（減速）・V062（加速）は「x だけに依存する u」で失敗した。**
**「τ に依存する u」は一度も試していない。ここが未探索だった。**

【本スクリプトで測ること】
実際の取引履歴（弱局面の実履歴・86起点・最小ロット制約あり）で——

    ロット = 基準ロット × k × (資金/初期資金) × [u*(x,τ) / u*(0,1)] / √τ

**比較対象は同じ評価系での比例方策（V073の k=8 と、各方策でIS選択したk）。**
kはIS窓の6ヶ月基準で選ぶ（OOSを見ない）。

【限界】
- V080の u* は拡散近似の産物。実際の損益は裾が厚く系列相関がある
- τ が0に近づくと `1/√τ` が発散するので**上限で頭打ちにする**（上限も報告する）
- 弱局面の起点は86個。起点が重なるため独立ではない
- 含み損益・証拠金制約を考慮していない
- **段階2の簡易検証である。採用するならMT5バックテストが必要**
"""
from __future__ import annotations

import bisect
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import optimal_control as oc
import target_policy_gap as tpg

CAPITAL = co.CAPITAL
MIN_LOT = co.MIN_LOT
STEP = co.STEP
RUIN = co.RUIN
MULT = 2.0
QUIET_END = tpg.QUIET_END
ORIGIN_STEP_DAYS = 7
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
CHECK = [3, 6, 12]
MAX_MONTHS = 18
U_MAX = 8.0
H_POLICY = 0.48                      # 弱局面6ヶ月相当。方策の形を決めるだけ
CAP_GRID = [2.0, 3.0, 5.0, 1e9]      # 期限接近時の増し玉の上限


def build_policy(H=H_POLICY, u_max=U_MAX, ntau=40):
    """u*(x, τ) の表を作る。HJBを解きながら τ の各点でスナップを取る。"""
    nx, nt = oc.NX, oc.NT
    xs = np.linspace(oc.LOG_RUIN, oc.LOG_TARGET, nx)
    dx = xs[1] - xs[0]
    dt = 1.0 / nt
    n = nx - 2
    v = np.zeros((nx, 1))
    v[-1] = 1.0
    dp = np.empty((n, 1))
    cp = np.empty((n, 1))
    taus = np.linspace(1.0 / ntau, 1.0, ntau)
    table = np.zeros((ntau, n))
    ti = 0
    Harr = np.array([H])
    for step in range(nt):
        vx = (v[2:] - v[:-2]) / (2.0 * dx)
        vxx = (v[2:] - 2.0 * v[1:-1] + v[:-2]) / (dx * dx)
        d = vx - vxx
        u = np.where(d > 1e-12, Harr * vx / np.where(d > 1e-12, d, 1.0), u_max)
        u = np.clip(np.nan_to_num(u, nan=0.0), 0.0, u_max)
        A = 0.5 * u * u
        M = u * Harr - A
        c_lo = A / (dx * dx) - np.minimum(M, 0.0) / dx
        c_up = A / (dx * dx) + np.maximum(M, 0.0) / dx
        lo, up = -dt * c_lo, -dt * c_up
        di = 1.0 + dt * (c_lo + c_up)
        rhs = v[1:-1].copy()
        rhs[-1] -= up[-1] * 1.0
        cp[0] = up[0] / di[0]
        dp[0] = rhs[0] / di[0]
        for i in range(1, n):
            den = di[i] - lo[i] * cp[i - 1]
            cp[i] = up[i] / den
            dp[i] = (rhs[i] - lo[i] * dp[i - 1]) / den
        v[n] = dp[n - 1]
        for i in range(n - 2, -1, -1):
            v[i + 1] = dp[i] - cp[i] * v[i + 2]
        np.clip(v, 0.0, 1.0, out=v)
        v[0] = 0.0
        v[-1] = 1.0
        tau = (step + 1) * dt
        while ti < ntau and tau >= taus[ti] - dt / 2:
            table[ti] = u[:, 0]
            ti += 1
    return xs[1:-1], taus, table


class Policy:
    def __init__(self):
        self.xs, self.taus, self.tab = build_policy()
        self.u_ref = float(np.interp(0.0, self.xs,
                                     self.tab[len(self.taus) - 1]))

    def mult(self, x, tau, cap):
        """比例方策に対する倍率。"""
        tau = min(max(tau, 1e-4), 1.0)
        j = int(np.clip(np.searchsorted(self.taus, tau), 0, len(self.taus) - 1))
        u = float(np.interp(x, self.xs, self.tab[j]))
        m = (u / self.u_ref) / math.sqrt(tau)
        return min(m, cap)


def simulate(rec, ti, t0, t_end, k, pol, cap):
    """1本の経路。(初回到達時刻, 破綻時刻) を返す。pol=None なら比例方策。"""
    i0 = bisect.bisect_left(ti, t0)
    i1 = bisect.bisect_left(ti, t_end)
    span = float(t_end - t0)
    eq = CAPITAL
    pend, pi, ei = [], 0, i0
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
            if eq >= CAPITAL * MULT:
                return t, None
            if eq <= CAPITAL * RUIN:
                return None, t
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
    return None, None


def evaluate(rec, k, pol, cap, start, end_cap):
    ti = [x[0] for x in rec]
    res, d = [], start
    while cod.add_months(d, MAX_MONTHS) <= end_cap:
        t_end = cod.add_months(d, MAX_MONTHS)
        hit, ruin = simulate(rec, ti, int(d.timestamp()),
                             int(t_end.timestamp()), k, pol, cap)
        res.append((d, hit, ruin))
        d += timedelta(days=ORIGIN_STEP_DAYS)
    out = {}
    for m in CHECK:
        h, r, _ = cod.cumulative(res, m)
        out[m] = (h, r)
    out["n"] = len(res)
    return out


def main():
    print("=" * 112)
    print("V082：期限を意識したサイジングを実履歴で測る（簡易検証）")
    print("=" * 112)
    print("★ `CLAUDE.md` の段階2。**採用の根拠にはしない。** 通れば段階3（MT5）へ。\n")
    print("  ロット = 基準 × k × (資金/初期資金) × [u*(x,τ)/u*(0,1)] / √τ")
    print("  ① 残り時間が減るほど大きく張る（**未探索の軸**）")
    print("  ② 資金が目標に近づくほど小さく張る")
    print("  V058（減速）・V062（加速）は x だけの方策で失敗した。\n")
    print("  評価：弱局面の実履歴（起点＋18暦月 ≤ 2020-01-01・86起点）")
    print("  資金10万円・破綻ライン10%・最小ロット制約あり・倍率2倍固定")
    print("  **kはIS窓の6ヶ月基準で選ぶ（OOSを見ない）**\n")

    print("  方策表を作成中（HJB）...", flush=True)
    pol = Policy()
    print(f"  基準 u*(0, τ=1) = {pol.u_ref:.3f}\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    print("=" * 112)
    print("【結果】方針A＝6ヶ月65% / 方針B＝12ヶ月90%（破綻は限りなく低く）")
    print("=" * 112)
    print(f"{'方策':<30}{'IS選択k':>9}{'IS 6月':>9}{'IS 12月':>9}"
          f"│{'OOS 3月':>9}{'OOS 6月':>9}{'OOS 12月':>10}{'12月破綻':>10}"
          f"│{'方針A':>7}{'方針B':>7}")

    def run(label, pol_, cap):
        best, bp = None, -1.0
        for k in K_GRID:
            o = evaluate(data["IS"], k, pol_, cap, a_is, b_is)
            if o[6][0] > bp:
                best, bp = k, o[6][0]
        oi = evaluate(data["IS"], best, pol_, cap, a_is, b_is)
        oo = evaluate(data["OOS"], best, pol_, cap, a_oos, QUIET_END)
        okA = oo[6][0] >= 0.65
        okB = oo[12][0] >= 0.90
        print(f"{label:<30}{best:>9.0f}{100*oi[6][0]:>8.1f}%{100*oi[12][0]:>8.1f}%"
              f"│{100*oo[3][0]:>8.1f}%{100*oo[6][0]:>8.1f}%{100*oo[12][0]:>9.1f}%"
              f"{100*oo[12][1]:>9.1f}%│{'OK' if okA else 'NG':>7}"
              f"{'OK' if okB else 'NG':>7}")
        return oo

    base = run("比例方策（基準・V073）", None, 0.0)
    for cap in CAP_GRID:
        lab = f"期限意識（増し玉上限 {cap:.0f}倍）" if cap < 1e8 else "期限意識（上限なし）"
        run(lab, pol, cap)

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・V080の u* は拡散近似の産物。実際の損益は裾が厚く系列相関がある")
    print("  ・弱局面の起点は86個。起点が重なるため独立ではない")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・**段階2の簡易検証である。採用するならMT5バックテストが必要**")
    print("\n完了。")


if __name__ == "__main__":
    main()
