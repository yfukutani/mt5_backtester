"""V080：**残り時間と残り距離に依存する最適サイジング**（簡易検証・2026-09-13）。

【この検証の位置づけ】
`CLAUDE.md`「戦略検証の進め方」の**段階2（簡易検証）**。
ここで測るのは「効果が出そうか」だけであり、**採用の根拠にはしない。**
段階2を通ったら段階3（MT5バックテスト）へ進める。

【何を疑っているか】
V078は「**一定の** 期限ボラ u」での最大値しか解いていない。

    P_const(H) = max_{u 一定}  P(到達)

しかし実際に選べるのは**その時点の資金 x と残り時間 τ に応じた u(x, τ)** である。
**本当の天井は最適制御の値関数であり、V078の値以上になる。**

    P_opt(H) = sup_{u(x,τ)}  P(到達)   ≥   P_const(H)

**V058（減速）・V062（加速）は「x だけに依存する u」を試して失敗した。**
**「τ にも依存する u」は一度も試していない。** これが未探索の軸である。

【解き方】
HJB方程式を後退オイラー法で解く。x は対数資金、τ は残り時間。

    ∂v/∂τ = max_u [ (u²/2)·v_xx + (u·H − u²/2)·v_x ]

u について最大化すると、`g(u) = (u²/2)(v_xx − v_x) + u·H·v_x` なので——
- `v_xx − v_x < 0` のとき内点最大：`u* = H·v_x / (v_x − v_xx)`
- そうでないとき単調増加：`u* = U_MAX`（現実の上限で頭打ち）

境界は `v(log0.1)=0`（破綻・吸収）、`v(log2)=1`（到達・吸収）。答えは `v(0, τ=1)`。

**U_MAX は結果を大きく左右するので、複数水準で報告する。**

【限界】
- 拡散近似（1取引の損益が独立同分布の正規）。実際は裾が厚く系列相関がある
- 最小ロット制約を含まない（含めれば**さらに低くなる**）
- u を連続に選べる前提。実際の k は離散
- 非線形HJBを陽的に扱うため、時間刻みを細かくしないと解が崩れる
- **これは段階2の簡易検証である。採用するならMT5バックテストが必要**
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import true_ceiling as tc

LOG_TARGET = tc.LOG_TARGET
LOG_RUIN = tc.LOG_RUIN
NX = 301
NT = 1500


def solve_hjb(Hs, u_max, nx=NX, nt=NT, want_policy=False):
    """HJBを**半陰的**に解く（制御は陽・拡散と移流は陰・移流は風上差分）。

    毎ステップ、そのときの v から最適な u*(x) を求め、その u* を係数として
    線形の後退方程式を陰的に1歩進める。風上差分にしているので係数行列は
    対角優位かつ単調で、時間刻みに対して無条件に安定。

    Hs は配列でよい（一括で解く）。v(0, τ=1) の配列を返す。
    """
    H = np.atleast_1d(np.asarray(Hs, dtype=float))
    P = len(H)
    xs = np.linspace(LOG_RUIN, LOG_TARGET, nx)
    dx = xs[1] - xs[0]
    dt = 1.0 / nt
    n = nx - 2
    v = np.zeros((nx, P))
    v[-1] = 1.0
    snap = {}
    dp = np.empty((n, P))
    cp = np.empty((n, P))
    for step in range(nt):
        vx = (v[2:] - v[:-2]) / (2.0 * dx)
        vxx = (v[2:] - 2.0 * v[1:-1] + v[:-2]) / (dx * dx)
        d = vx - vxx
        u = np.where(d > 1e-12, H * vx / np.where(d > 1e-12, d, 1.0), u_max)
        u = np.clip(np.nan_to_num(u, nan=0.0), 0.0, u_max)
        A = 0.5 * u * u                     # 拡散係数
        M = u * H - A                       # 移流係数（対数の期待成長）
        Mp = np.maximum(M, 0.0)
        Mm = np.minimum(M, 0.0)
        c_lo = A / (dx * dx) - Mm / dx      # ≥ 0
        c_up = A / (dx * dx) + Mp / dx      # ≥ 0
        lo = -dt * c_lo
        up = -dt * c_up
        di = 1.0 + dt * (c_lo + c_up)
        rhs = v[1:-1].copy()
        rhs[-1] -= up[-1] * 1.0             # 到達側の境界値 1（破綻側は 0）
        # --- Thomas（係数が空間で変わるので毎ステップ作る） ---
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
        if want_policy:
            tau = (step + 1) * dt
            for key in (0.25, 0.50, 0.75, 1.00):
                if abs(tau - key) < dt / 2:
                    snap[key] = (xs[1:-1].copy(), u[:, 0].copy())
    out = np.array([float(np.interp(0.0, xs, v[:, j])) for j in range(P)])
    return (out, snap) if want_policy else out


def main():
    print("=" * 104)
    print("V080：残り時間と残り距離に依存する最適サイジング（簡易検証）")
    print("=" * 104)
    print("★ `CLAUDE.md` の段階2（簡易検証）。**採用の根拠にはしない。**")
    print("  効果が出そうなら段階3（MT5バックテスト）へ進める。\n")
    print("  V078は『一定の u』での最大値しか解いていない。")
    print("  **本当の天井は u(x, τ) の最適制御であり、V078以上になるはず。**")
    print("  V058（減速）・V062（加速）は『x だけに依存する u』で失敗した。")
    print("  **『τ にも依存する u』は一度も試していない。**\n")

    # ---------- V078（一定u）の値を再計算して並べる ----------
    Hs = [0.34, 0.48, 0.68, 0.80, 1.00, 1.32, 1.50, 2.00, 2.16]
    U_GRID = np.arange(0.10, 8.01, 0.10)
    HH, UU = np.meshgrid(np.array(Hs), U_GRID, indexing="ij")
    const = tc.solve_batch(HH.ravel(), UU.ravel(), "reach").reshape(HH.shape)
    p_const = const.max(axis=1)
    u_const = U_GRID[const.argmax(axis=1)]

    print("=" * 104)
    print("【1. 一定u（V078）と 最適制御 u(x,τ) の比較】")
    print("=" * 104)
    print(f"{'H':>6}{'一定uの天井':>14}{'最適な一定u':>13}"
          f"{'最適制御 u上限4':>17}{'u上限8':>11}{'u上限16':>11}{'**改善**':>12}")
    opt = {um: solve_hjb(Hs, um) for um in (4.0, 8.0, 16.0)}
    for i, H in enumerate(Hs):
        row = [opt[um][i] for um in (4.0, 8.0, 16.0)]
        print(f"{H:>6.2f}{100*p_const[i]:>13.1f}%{u_const[i]:>13.2f}"
              f"{100*row[0]:>16.1f}%{100*row[1]:>10.1f}%{100*row[2]:>10.1f}%"
              f"{100*(max(row)-p_const[i]):>11.1f}pt")

    # ---------- 方針A/Bに必要なHがどう変わるか ----------
    print("\n" + "=" * 104)
    print("【2. 最適制御にすると、必要な期限シャープ H はどう変わるか】")
    print("=" * 104)
    grid = np.round(np.arange(0.10, 3.01, 0.05), 2)
    for um in (4.0, 8.0, 16.0):
        vals = solve_hjb(grid, um)
        need = {}
        for tgt in (0.65, 0.90):
            idx = np.where(vals >= tgt)[0]
            need[tgt] = float(grid[idx[0]]) if len(idx) else float("nan")
        fa = (need[0.65] / 0.480) ** 2
        fb = (need[0.90] / 0.679) ** 2
        print(f"  u上限{um:>5.1f}：方針A に必要なH = {need[0.65]:.2f}"
              f"（V078は0.80／取引数 {fa:.1f}倍） ／ "
              f"方針B に必要なH = {need[0.90]:.2f}"
              f"（V078は2.00／取引数 {fb:.1f}倍）")

    # ---------- 最適方策の形 ----------
    print("\n" + "=" * 104)
    print("【3. 最適方策の形】弱局面の H=0.48（6ヶ月）・u上限8")
    print("=" * 104)
    _, snap = solve_hjb([0.48], 8.0, want_policy=True)
    print("  x は対数資金（0 が初期資金・+0.693 が目標・−2.303 が破綻）")
    print(f"{'残り時間':>9}" + "".join(f"{f'x={x:+.2f}':>10}"
          for x in (-1.50, -1.00, -0.50, 0.00, 0.25, 0.50)))
    for tau in (0.25, 0.50, 0.75, 1.00):
        if tau not in snap:
            continue
        xs_, us_ = snap[tau]
        cells = "".join(f"{np.interp(x, xs_, us_):>10.2f}"
                        for x in (-1.50, -1.00, -0.50, 0.00, 0.25, 0.50))
        print(f"{tau:>9.2f}" + cells)
    print("\n  （表の値は期限ボラ u。大きいほど大きく張る）")

    print("\n" + "=" * 104)
    print("【限界】")
    print("=" * 104)
    print("  ・拡散近似。実際は裾が厚く系列相関がある")
    print("  ・最小ロット制約を含まない（含めれば**さらに低くなる**）")
    print("  ・u を連続に選べる前提。実際の k は離散")
    print("  ・非線形HJBを陽的に解いている。時間刻みへの依存を要確認")
    print("  ・**段階2の簡易検証である。採用するならMT5バックテストが必要**")
    print("\n完了。")


if __name__ == "__main__":
    main()
