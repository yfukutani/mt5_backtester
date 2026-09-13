"""V095：**HJB数値解の検証と、実際に使った方策の正しい基準値**（2026-09-13）。

【Codexの指摘（2026-09-13）】

> 14.9ptをそのまま回収可能な実装損失とは見なせない。比較に3つのずれがある。
> 1. **50.7%は実履歴の簡易再生値**。決済時にしか残高を更新せず、含み損益を
>    含むequityでの到達・破綻とは異なる。
> 2. **V086はHJBの「形」を移植した方策**であり、HJBの絶対的な総リスク水準と
>    一致する保証がない。対応には `k·σ₀·√T = u_ref` が必要。
> 3. **12ヶ月にも H=0.48 の表を使っている。** H=0.679の最適値と、別のH・
>    倍率上限・IS選択k=2の実績を比較している。
>    **−39.8ptを実装ギャップと呼ぶのは早い。**
>
> HJB数値解についても、格子を細かくした収束確認と、同じ拡散過程で抽出方策を
> 再生して値関数を再現する確認が先。**ここで一致しなければ、実履歴の問題まで
> 進めない。**

**この指摘は正しい。本スクリプトで3つを潰す。**

【やること】
- **A. 格子の収束確認** — 空間・時間の分割を変えて値が動かないか
- **B. 抽出方策の再生** — HJBの値関数と、その方策を前向きに走らせた到達率が一致するか
  （**一致しなければHJBの数値解を信用できない**）
- **C. 実際に使った方策の正しい基準値** — 「H=0.48で作った表」を
  「真のHが0.679の過程」に当てたときの到達率。**12ヶ月の基準はこれである。**
- **D. 倍率上限（cap）の効果** — 上限3倍が理論値をどれだけ下げているか

【限界】
- 拡散近似そのものの妥当性は本スクリプトでは検証できない（それはV096以降）
- モンテカルロには標準誤差がある。経路数を明記する
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimal_control as oc
import true_ceiling as tc

LOG_TARGET = tc.LOG_TARGET
LOG_RUIN = tc.LOG_RUIN
U_MAX = 8.0
PATHS = 200000
STEPS = 2000
SEED = 20260913


def policy_table(H, u_max=U_MAX, nx=301, nt=1500, ntau=60):
    """HJBを解きながら τ 断面の u*(x) を保存する。"""
    xs = np.linspace(LOG_RUIN, LOG_TARGET, nx)
    dx = xs[1] - xs[0]
    dt = 1.0 / nt
    n = nx - 2
    v = np.zeros((nx, 1))
    v[-1] = 1.0
    dp = np.empty((n, 1))
    cp = np.empty((n, 1))
    taus = np.linspace(1.0 / ntau, 1.0, ntau)
    tab = np.zeros((ntau, n))
    ti = 0
    Ha = np.array([H])
    for step in range(nt):
        vx = (v[2:] - v[:-2]) / (2.0 * dx)
        vxx = (v[2:] - 2.0 * v[1:-1] + v[:-2]) / (dx * dx)
        d = vx - vxx
        u = np.where(d > 1e-12, Ha * vx / np.where(d > 1e-12, d, 1.0), u_max)
        u = np.clip(np.nan_to_num(u, nan=0.0), 0.0, u_max)
        A = 0.5 * u * u
        M = u * Ha - A
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
            tab[ti] = u[:, 0]
            ti += 1
    val = float(np.interp(0.0, xs, v[:, 0]))
    return xs[1:-1], taus, tab, val


def forward(xs, taus, tab, H_true, cap=None, u_ref=None,
            paths=PATHS, steps=STEPS, seed=SEED):
    """抽出した方策を、真のシャープ H_true の拡散で前向きに走らせる。

    cap を与えると `u = u_ref * min(u_tab/u_ref, cap)` に制限する
    （実装で使っている倍率上限と同じ扱い）。
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / steps
    x = np.zeros(paths)
    hit = np.zeros(paths, dtype=bool)
    dead = np.zeros(paths, dtype=bool)
    for s in range(steps):
        tau = 1.0 - s * dt
        j = int(np.clip(np.searchsorted(taus, tau), 0, len(taus) - 1))
        live = ~(hit | dead)
        if not live.any():
            break
        u = np.interp(x[live], xs, tab[j])
        if cap is not None and u_ref:
            u = u_ref * np.minimum(u / u_ref, cap)
        u = np.clip(u, 0.0, U_MAX)
        drift = (u * H_true - 0.5 * u * u) * dt
        vol = u * math.sqrt(dt)
        x[live] += drift + vol * rng.standard_normal(int(live.sum()))
        hit |= live & (x >= LOG_TARGET)
        live = ~(hit | dead)
        dead |= live & (x <= LOG_RUIN)
    p = float(hit.mean())
    se = math.sqrt(max(p * (1 - p), 1e-12) / paths)
    return p, float(dead.mean()), se


def main():
    print("=" * 112)
    print("V095：HJB数値解の検証と、実際に使った方策の正しい基準値")
    print("=" * 112)
    print("★ Codexの指摘：**格子の収束と、抽出方策の再生で値関数を再現できるか**を")
    print("  先に確認しないと、実履歴との差を実装ギャップとは呼べない。\n")

    # ---------- A. 格子の収束 ----------
    print("=" * 112)
    print("【A. 格子の収束確認】H=0.48 / u上限8")
    print("=" * 112)
    print(f"{'空間分割':>10}{'時間分割':>10}{'HJBの値':>12}")
    for nx, nt in ((151, 750), (301, 1500), (601, 3000)):
        _, _, _, val = policy_table(0.48, nx=nx, nt=nt)
        print(f"{nx:>10}{nt:>10}{100*val:>11.2f}%")
    print("  → 分割を変えても動かなければ、離散化は十分")

    # ---------- B. 抽出方策の再生 ----------
    print("\n" + "=" * 112)
    print("【B. 抽出方策の再生】HJBの値関数 vs その方策を前向きに走らせた到達率")
    print("=" * 112)
    print(f"  経路数 {PATHS:,} × 分割 {STEPS}")
    print(f"{'H':>7}{'HJBの値':>11}{'方策を再生':>12}{'標準誤差':>10}{'差':>9}{'判定':>7}")
    tabs = {}
    for H in (0.34, 0.48, 0.68, 1.00, 1.50):
        xs, taus, tab, val = policy_table(H)
        tabs[H] = (xs, taus, tab, val)
        p, r, se = forward(xs, taus, tab, H)
        ok = abs(p - val) < 4 * se + 0.01
        print(f"{H:>7.2f}{100*val:>10.2f}%{100*p:>11.2f}%{100*se:>9.2f}%"
              f"{100*(p-val):>8.2f}{'OK' if ok else 'NG':>7}")
    print("  → **一致しなければHJBの数値解を信用できない**")

    # ---------- C. 実際に使った方策の正しい基準値 ----------
    print("\n" + "=" * 112)
    print("【C. 実際に使った方策の正しい基準値】**ここがCodexの3番目の指摘**")
    print("=" * 112)
    print("  V086/V087は 6ヶ月・12ヶ月とも **H=0.48 で作った表**を使っていた。")
    print("  12ヶ月の真のHは 0.679。**H=0.679の最適値と比べるのは誤り。**\n")
    xs48, taus48, tab48, val48 = tabs[0.48]
    xs68, taus68, tab68, val68 = tabs[0.68]
    print(f"{'条件':<42}{'到達':>9}{'破綻':>9}{'標準誤差':>10}")
    rows = [
        ("6ヶ月：H=0.48の最適方策・上限なし", xs48, taus48, tab48, 0.48, None),
        ("6ヶ月：H=0.48の最適方策・**上限3倍**", xs48, taus48, tab48, 0.48, 3.0),
        ("12ヶ月：H=0.679の最適方策・上限なし", xs68, taus68, tab68, 0.679, None),
        ("12ヶ月：**H=0.48の表**を使用・上限なし", xs48, taus48, tab48, 0.679, None),
        ("12ヶ月：**H=0.48の表＋上限3倍**（実際に使った条件）",
         xs48, taus48, tab48, 0.679, 3.0),
    ]
    u_ref48 = float(np.interp(0.0, xs48, tab48[len(taus48) - 1]))
    for label, xs, taus, tab, Ht, cap in rows:
        ur = (float(np.interp(0.0, xs, tab[len(taus) - 1]))
              if cap is not None else None)
        p, r, se = forward(xs, taus, tab, Ht, cap=cap, u_ref=ur)
        print(f"{label:<42}{100*p:>8.1f}%{100*r:>8.1f}%{100*se:>9.2f}%")

    print("\n  → **12ヶ月の正しい基準は最後の行**であり、72.8%ではない。")

    # ---------- D. 上限の効果 ----------
    print("\n" + "=" * 112)
    print("【D. 倍率上限（cap）の効果】H=0.48の方策を上限を変えて再生")
    print("=" * 112)
    print(f"{'上限':>8}{'到達':>9}{'破綻':>9}")
    for cap in (2.0, 3.0, 5.0, 8.0, None):
        p, r, se = forward(xs48, taus48, tab48, 0.48,
                           cap=cap, u_ref=u_ref48 if cap else None)
        lab = "なし" if cap is None else f"{cap:.0f}倍"
        print(f"{lab:>8}{100*p:>8.1f}%{100*r:>8.1f}%")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・拡散近似そのものの妥当性は本スクリプトでは検証できない")
    print(f"  ・モンテカルロの標準誤差は約0.1pt（経路数 {PATHS:,}）")
    print("  ・実履歴との差の分解は V096 以降で行う")
    print("\n完了。")


if __name__ == "__main__":
    main()
