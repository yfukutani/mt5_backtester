"""V078：**破綻ラインと期限の下での「本当の天井」**（2026-09-13）。

【V056の天井式は誤りだった（自己訂正・Codexの指摘と自分の観測が一致）】

V056は「到達確率の天井は `Φ(期限シャープ)`」とし、
「天井を上げる手段は厳密に2つだけ」と断定した。**これは誤りである。**

Codexの指摘（2026-09-13）：

> V056が導出したのは `P(k·X_T ≥ G) = Φ(S_T − G/(k·σ_T))` という
> **一定倍率・正規近似における「期限末の損益が目標以上となる確率」**である。
> 今回測っているのは「期限までに、破綻より先に、2倍へ到達する確率」であり、
> 途中到達と期限末の確率は異なる。ドリフトゼロのブラウン運動でも、
> **途中到達確率は期限末超過確率の2倍になる。**
> したがって `Φ(期限シャープ)` を、複利・動的サイジング・破綻停止を含む
> 今回の到達確率の普遍的な天井として扱うことはできない。

自分の観測（V077）も同じ矛盾を示していた：

| 期限 | Φ(期限シャープ)＝V056の「天井」 | 実測（弱局面OOS） | 差 |
|---|---:|---:|---:|
| 12ヶ月 | 90.6% | **41.9%** | **−48.7pt** |

**2つの効果が逆向きに効いている。**
- 途中到達を数えるので、期限末の確率より**上がる**（Codexの指摘）
- 破綻ラインで吸収され、複利の分散ドラッグが効くので**下がる**

**どちらも無視していたのがV056の誤りである。ここで両方を正しく扱う。**

【正しい定式化】

資金を対数で見る。目標は `+log2 = +0.6931`、破綻は `+log0.1 = −2.3026`。
1取引あたりリターン率の平均 μ_r・標準偏差 σ_r、倍率 k のとき、
対数資金は近似的にブラウン運動で——

    1取引あたりドリフト = k·μ_r − (k·σ_r)²/2      （複利の分散ドラッグ）
    1取引あたりボラ     = k·σ_r

期限内 N 取引で、**期限ボラ `u ≡ k·σ_r·sqrt(N)`** と置くと、

    期限ドリフト = u·H − u²/2     （H ≡ 期限シャープ = (μ_r/σ_r)·sqrt(N)）
    期限ボラ     = u

**期限内の到達確率は、期限シャープ H と選んだ u だけで決まる。**
**資金額にも1取引の大きさにも依存しない。** u は k で自由に選べるので——

    P_max(H) = max_u  P( +0.6931 に、−2.3026 より先に、期限内に到達 )

**これが「破綻ライン10%・期限あり」での本当の天井である。**

【解き方】
後退方程式 `∂v/∂τ = (u²/2)·v_xx + (uH − u²/2)·v_x` を後退オイラー法で解く。
境界は `v(log0.1)=0`（破綻・吸収）、`v(log2)=1`（到達・吸収）。答えは `v(0, τ=1)`。
**モンテカルロではないので誤差は離散化のみ。** 一点をモンテカルロで照合する。

【限界】
- 拡散近似（1取引の損益が独立同分布の正規）。実際は裾が厚く系列相関がある
- 最小ロット制約を含まない（含めれば**さらに低くなる**）
- 破綻時に即停止する前提（実際は証拠金不足でもっと早く止まりうる）
- 期限内の取引数 N を確定値として扱っている（実際は変動する）
- 「u を自由に選べる」としているが、実際の k は離散で最小ロット制約もある
"""
from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl

LOG_TARGET = math.log(2.0)
LOG_RUIN = math.log(0.10)
NX = 401
NT = 1200
U_GRID = np.arange(0.20, 6.01, 0.20)
QUIET_END = datetime(2020, 1, 1, tzinfo=timezone.utc)


def solve_batch(Hs, us, which="reach"):
    """(H, u) の組を一括で解き、確率の配列を返す。後退オイラー法。

    which="reach" なら「破綻より先に期限内で2倍へ到達する確率」、
    which="ruin"  なら「到達より先に期限内で破綻する確率」。
    """
    H = np.asarray(Hs, dtype=float)
    u = np.asarray(us, dtype=float)
    P = len(H)
    m = u * H - 0.5 * u * u
    s2 = u * u
    xs = np.linspace(LOG_RUIN, LOG_TARGET, NX)
    dx = xs[1] - xs[0]
    dt = 1.0 / NT
    a = s2 * dt / (2.0 * dx * dx)          # α'
    b = m * dt / (2.0 * dx)                # β'
    lo = -(a - b)                          # 下対角（各組でスカラー）
    di = 1.0 + 2.0 * a
    up = -(a + b)
    n = NX - 2

    # --- 行列は時間について一定なので Thomas の cp を一度だけ作る ---
    cp = np.empty((n, P))
    den = np.empty((n, P))
    den[0] = di
    cp[0] = up / den[0]
    for i in range(1, n):
        den[i] = di - lo * cp[i - 1]
        cp[i] = up / den[i]
    inv_den = 1.0 / den

    hi_bc = 1.0 if which == "reach" else 0.0
    lo_bc = 0.0 if which == "reach" else 1.0
    v = np.zeros((NX, P))
    v[0] = lo_bc
    v[-1] = hi_bc
    dp = np.empty((n, P))
    for _ in range(NT):
        rhs = v[1:-1].copy()
        rhs[-1] -= up * hi_bc
        rhs[0] -= lo * lo_bc
        dp[0] = rhs[0] * inv_den[0]
        for i in range(1, n):
            dp[i] = (rhs[i] - lo * dp[i - 1]) * inv_den[i]
        v[n] = dp[n - 1]
        for i in range(n - 2, -1, -1):
            v[i + 1] = dp[i] - cp[i] * v[i + 2]
        v[0] = lo_bc
        v[-1] = hi_bc
    i0 = int(np.argmin(np.abs(xs - 0.0)))
    w = (0.0 - xs[i0]) / dx
    return v[i0] * (1 - w) + v[i0 + 1] * w


def mc_check(H, u, paths=200000, steps=800, seed=7):
    rng = np.random.default_rng(seed)
    dt = 1.0 / steps
    drift = (u * H - 0.5 * u * u) * dt
    vol = u * math.sqrt(dt)
    x = np.zeros(paths)
    hit = np.zeros(paths, dtype=bool)
    dead = np.zeros(paths, dtype=bool)
    for _ in range(steps):
        live = ~(hit | dead)
        x[live] += drift + vol * rng.standard_normal(int(live.sum()))
        hit |= live & (x >= LOG_TARGET)
        dead |= (~hit) & live & (x <= LOG_RUIN)
    return float(hit.mean())


def load_simple(window):
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["magic"]) == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"])))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol in rows:
            if entry == 0:
                opened[pid] = (t, vol)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((o[0], profit))
    rec.sort()
    return rec


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main():
    print("=" * 104)
    print("V078：破綻ライン10%と期限の下での**本当の天井**（倍率2倍固定）")
    print("=" * 104)
    print("★ V056の『天井＝Φ(期限シャープ)』は誤りだった。自己訂正としてここで正しい天井を出す。")
    print("  ・途中到達を数えるので期限末の確率より**上がる**（Codexの指摘）")
    print("  ・破綻ラインで吸収され、複利の分散ドラッグが効くので**下がる**\n")
    print(f"  目標 log2 = {LOG_TARGET:+.4f} / 破綻 log0.1 = {LOG_RUIN:+.4f}")
    print(f"  後退オイラー法（空間{NX}分割・時間{NT}分割）・期限ボラ u を"
          f" {U_GRID[0]:.2f}〜{U_GRID[-1]:.2f} で総当たり\n")

    # ---------- H のグリッドで一括計算 ----------
    Hgrid = np.round(np.arange(0.2, 14.01, 0.2), 2)
    HH, UU = np.meshgrid(Hgrid, U_GRID, indexing="ij")
    flat = solve_batch(HH.ravel(), UU.ravel(), "reach").reshape(HH.shape)
    rflat = solve_batch(HH.ravel(), UU.ravel(), "ruin").reshape(HH.shape)
    pmax = flat.max(axis=1)
    ubest = U_GRID[flat.argmax(axis=1)]

    def look(H):
        i = int(np.argmin(np.abs(Hgrid - H)))
        return float(pmax[i]), float(ubest[i])

    # ---------- 数値の照合 ----------
    print("=" * 104)
    print("【0. 数値の照合】PDE解とモンテカルロ（20万経路）")
    print("=" * 104)
    for H, u in ((1.3, 1.0), (2.2, 1.5), (4.0, 2.0)):
        pde = float(solve_batch([H], [u])[0])
        mc = mc_check(H, u)
        print(f"  H={H:.1f} u={u:.1f} → PDE {100*pde:6.2f}% / MC {100*mc:6.2f}% "
              f"（差 {100*abs(pde-mc):.2f}pt）")

    # ---------- 1. H ごとの本当の天井 ----------
    print("\n" + "=" * 104)
    print("【1. 期限シャープ H ごとの本当の天井】")
    print("=" * 104)
    print(f"{'H':>6}{'Φ(H)＝V056の天井':>20}{'**本当の天井**':>18}"
          f"{'最適な期限ボラu':>18}{'差':>12}")
    for H in (0.5, 0.8, 1.0, 1.3, 1.5, 2.0, 2.2, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        pm, bu = look(H)
        print(f"{H:>6.2f}{100*phi(H):>19.1f}%{100*pm:>17.1f}%{bu:>18.2f}"
              f"{100*(pm-phi(H)):>11.1f}pt")

    # ---------- 2. 必要な H ----------
    print("\n" + "=" * 104)
    print("【2. 方針A（65%）・方針B（90%）に必要な期限シャープ H】")
    print("=" * 104)
    need = {}
    for tgt in (0.65, 0.90):
        idx = np.where(pmax >= tgt)[0]
        need[tgt] = float(Hgrid[idx[0]]) if len(idx) else float("inf")
        print(f"  到達率 {100*tgt:.0f}% に必要な H = **{need[tgt]:.2f}**"
              f"（V056の誤った式なら Φ⁻¹={_norm_inv(tgt):.2f} で足りるはずだった）")

    # ---------- 2b. 方針Bは破綻率の制約付き ----------
    print("\n" + "=" * 104)
    print("【2b. 方針B：到達90%**かつ**破綻が低い、を同時に満たすのに必要な H】")
    print("=" * 104)
    print("  ユーザーは方針Bについて『破綻率は限りなく低く』と指示している。")
    print("  『限りなく低く』は数値条件ではないので、**3水準を併記する**。")
    print(f"{'破綻の上限':>12}{'必要なH':>10}{'そのときのu':>12}"
          f"{'到達':>9}{'破綻':>9}{'弱局面から必要な取引数倍率':>28}")
    q6 = None
    needB = {}
    for rcap in (0.10, 0.05, 0.02):
        found = None
        for i, H in enumerate(Hgrid):
            ok = (flat[i] >= 0.90) & (rflat[i] <= rcap)
            if ok.any():
                j = int(np.argmax(np.where(ok, flat[i], -1)))
                found = (float(H), float(U_GRID[j]), float(flat[i, j]),
                         float(rflat[i, j]))
                break
        needB[rcap] = found
        if found is None:
            print(f"{100*rcap:>11.0f}%{'（不能）':>10}")
        else:
            H, uu, pr, rr = found
            print(f"{100*rcap:>11.0f}%{H:>10.2f}{uu:>12.2f}"
                  f"{100*pr:>8.1f}%{100*rr:>8.1f}%{'（後述）':>28}")

    # ---------- 3. 実測の H ----------
    print("\n" + "=" * 104)
    print("【3. 実測の期限シャープと、必要な取引数倍率】")
    print("=" * 104)
    raw = {w: load_simple(w) for w in ("IS", "OOS")}
    quiet = [x for x in raw["OOS"]
             if datetime.fromtimestamp(x[0], tz=timezone.utc) < QUIET_END]
    t0 = datetime.fromtimestamp(raw["OOS"][0][0], tz=timezone.utc)
    span_quiet = (QUIET_END - t0).days / 30.44
    sets = [("IS窓（2021-06〜2026-06）", raw["IS"], 60.0),
            ("OOS窓 全体（2016-11〜2021-06）", raw["OOS"], 55.0),
            ("**OOS 弱局面のみ（〜2020-01）**", quiet, span_quiet)]
    print(f"{'窓':<30}{'取引':>7}{'1取引S':>9}{'月あたり':>9}"
          f"{'H(3月)':>9}{'H(6月)':>9}{'H(12月)':>9}")
    hs = {}
    for name, rec, span in sets:
        p = np.array([x[1] for x in rec], dtype=float)
        s = float(p.mean() / p.std(ddof=1))
        per = len(rec) / span
        hs[name] = {m: s * math.sqrt(per * m) for m in (3, 6, 12)}
        print(f"{name:<30}{len(rec):>7}{s:>9.4f}{per:>9.1f}"
              f"{hs[name][3]:>9.3f}{hs[name][6]:>9.3f}{hs[name][12]:>9.3f}")

    print()
    print(f"{'窓':<30}{'方針A：6月65%に必要な取引数倍率':>32}"
          f"{'方針B：12月90%に必要な倍率':>28}")
    for name, _, _ in sets:
        fa = (need[0.65] / hs[name][6]) ** 2
        fb = (need[0.90] / hs[name][12]) ** 2
        print(f"{name:<30}{fa:>31.1f}倍{fb:>27.1f}倍")

    print()
    print("  方針Bに破綻率の上限を課した場合の、**弱局面からの必要な取引数倍率**：")
    hq = hs["**OOS 弱局面のみ（〜2020-01）**"][12]
    for rcap, found in needB.items():
        if found is None:
            print(f"    破綻 ≤ {100*rcap:.0f}% → **不能**")
        else:
            print(f"    破綻 ≤ {100*rcap:.0f}% → H={found[0]:.2f} が必要 ＝ "
                  f"**取引数 {(found[0]/hq)**2:.1f}倍**")

    # ---------- 4. 現状の天井 ----------
    print("\n" + "=" * 104)
    print("【4. 現状の H での本当の天井（弱局面OOS）と、実測との差】")
    print("=" * 104)
    q = hs["**OOS 弱局面のみ（〜2020-01）**"]
    actual = {3: 0.233, 6: 0.360, 12: 0.419}
    print(f"{'期限':>6}{'H':>8}{'V056の天井':>14}{'**本当の天井**':>18}"
          f"{'**実測**':>12}{'天井との差':>14}")
    for m in (3, 6, 12):
        pm, bu = look(q[m])
        print(f"{m:>4}月{q[m]:>8.3f}{100*phi(q[m]):>13.1f}%{100*pm:>17.1f}%"
              f"{100*actual[m]:>11.1f}%{100*(pm-actual[m]):>13.1f}pt")

    print("\n" + "=" * 104)
    print("【限界】")
    print("=" * 104)
    print("  ・拡散近似（1取引の損益が独立同分布の正規）。実際は裾が厚く系列相関がある")
    print("  ・最小ロット制約を含まない（含めれば**さらに低くなる**）")
    print("  ・破綻時に即停止する前提（実際は証拠金不足でもっと早く止まりうる）")
    print("  ・期限内の取引数を確定値として扱っている")
    print("  ・u を連続に選べる前提。実際の k は離散で最小ロット制約もある")
    print("\n完了。")


def _norm_inv(p):
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


if __name__ == "__main__":
    main()
