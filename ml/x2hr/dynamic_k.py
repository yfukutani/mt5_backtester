"""動的サイジング（時間・資金水準に応じてkを変える）を検証する（V014・Codex設計）。

【背景】V001〜V013はすべて期限を通じて一定の倍率kで測定してきた。Codexへの理論相談
（V014プロンプト）で、有限期限・有限バリアの到達確率最大化問題では、最適方策が
定数kではなく時間・資金水準に依存しうることが示された（Browne 1999の目標到達問題）。
本スクリプトはCodexが提示した測定設計をそのまま実装する。

【Codex設計の要点】
1. 3つの方策族（A: 時間のみで増額 / B: 目標距離×残り時間 / C: Browneの理論式をそのまま使う）
   を、少数パラメータ（1〜2個）に限定して評価する。
2. パス（取引系列）はポリシーごとに使い回さず、window×期限ごとに1回だけ生成し、
   全ポリシーに同じパスを見せる（ペア比較・分散低減）。
3. IS窓で選んだ固定ポリシーをOOS/FULL窓に適用する（選び直さない）。
4. 主要比較は「IS選択constant」対「IS選択動的ポリシー」。「OOS事後最良constant」は
   参考値として別掲する（選択手続きが異なるため混同しない）。
5. 継続基準: 主評価（2ヶ月・OOS）でIS選択constant比+2pt以上・対応付き95%CI下限>0。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc

CAPITAL = cc.CAPITAL
RUIN = 0.10
MONTHS = cc.MONTHS
K_CAP = 8.0
N_PATHS = 20000
L = 20


# ---------------------------------------------------------------- 正規分布（scipy不使用）
def norm_pdf(z):
    return np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def norm_ppf(p):
    """Acklamの有理近似（標準正規分布の逆累積分布関数）。"""
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low = 0.02425
    p_high = 1 - p_low
    out = np.empty_like(p)

    lo = p < p_low
    if lo.any():
        q = np.sqrt(-2 * np.log(p[lo]))
        out[lo] = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                  ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)

    mid = (~lo) & (p <= p_high)
    if mid.any():
        q = p[mid] - 0.5
        r = q * q
        out[mid] = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / \
                   (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

    hi = p > p_high
    if hi.any():
        q = np.sqrt(-2 * np.log(1 - p[hi]))
        out[hi] = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                   ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    return out


# ---------------------------------------------------------------- 方策族
def policy_constant(k):
    def f(h, H, x):
        return np.full_like(x, k)
    return f


def policy_A(k0, a):
    """時間のみで増額: k = k0 * (1 + a*(1 - h/H))"""
    def f(h, H, x):
        k = k0 * (1 + a * (1 - h / H))
        return np.full_like(x, k)
    return f


def policy_B(k0):
    """目標距離×残り時間: k = k0 * log(2/x)/log(2) * sqrt(H/h)"""
    def f(h, H, x):
        ratio = np.clip(2.0 / np.maximum(x, 1e-6), 1e-6, None)
        k = k0 * (np.log(ratio) / math.log(2.0)) * math.sqrt(H / h)
        return k
    return f


def policy_C(c, s_is):
    """Browne(1999)の理論式（下限0.1・目標2.0）をそのまま使う。"""
    def f(h, H, x):
        z = np.clip((x - RUIN) / (2.0 - RUIN), 1e-9, 1 - 1e-9)
        q = norm_ppf(z)
        k = c * ((2.0 - RUIN) / (s_is * np.maximum(x, 1e-6) * math.sqrt(h))) * norm_pdf(q)
        return k
    return f


# ---------------------------------------------------------------- パス生成・シミュレーション
def generate_paths(trades, horizon_steps, n_paths, L, seed):
    rng = np.random.default_rng(seed)
    n = len(trades)
    trades_arr = np.asarray(trades, dtype=float)
    n_blocks = horizon_steps // L + 2
    starts = rng.integers(0, n, size=(n_paths, n_blocks))
    offsets = np.arange(L)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n   # (n_paths, n_blocks, L)
    idx = idx.reshape(n_paths, -1)[:, :horizon_steps]
    return trades_arr[idx]   # (n_paths, horizon_steps)


def run_policy(paths, policy_fn, horizon_steps):
    n_paths, H = paths.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)     # 0=expired 1=hit 2=ruin
    stop_step = np.full(n_paths, H, dtype=np.int32)
    k_samples = []
    cap_hits = 0
    k_count = 0
    for step in range(H):
        if not alive.any():
            break
        h = float(H - step)
        x = eq / CAPITAL
        k = policy_fn(h, float(H), x)
        k = np.clip(k, 0.0, K_CAP)
        if step % 5 == 0:
            sub = k[alive]
            if sub.size:
                k_samples.append(sub)
                cap_hits += int((sub >= K_CAP - 1e-9).sum())
                k_count += sub.size
        profit = paths[:, step]
        new_eq = eq + profit * k * (eq / CAPITAL)
        eq = np.where(alive, new_eq, eq)
        hit_now = alive & (eq >= CAPITAL * 2.0)
        ruin_now = alive & (eq <= CAPITAL * RUIN)
        state[hit_now] = 1
        state[ruin_now] = 2
        stop_step[hit_now | ruin_now] = step + 1
        alive = alive & ~(hit_now | ruin_now)
    p_hit = float((state == 1).mean())
    p_ruin = float((state == 2).mean())
    p_exp = 1.0 - p_hit - p_ruin
    hit_steps = stop_step[state == 1]
    med = int(np.median(hit_steps)) if hit_steps.size else None
    k_all = np.concatenate(k_samples) if k_samples else np.array([])
    cap_rate = cap_hits / k_count if k_count else 0.0
    fail_final = eq[state != 1]
    return dict(
        p_hit=p_hit, p_ruin=p_ruin, p_exp=p_exp, median_steps=med,
        cap_hit_rate=cap_rate, k_mean=float(k_all.mean()) if k_all.size else None,
        fail_final_mean=float(fail_final.mean()) if fail_final.size else None,
        success=(state == 1),
    )


def paired_diff(res_a, res_b, n_paths):
    """res_a - res_b の対応のある差（同一パス）と95%CI。"""
    d = res_a["success"].astype(float) - res_b["success"].astype(float)
    mean_d = float(d.mean())
    se = float(d.std(ddof=1) / math.sqrt(n_paths))
    return mean_d, (mean_d - 1.96 * se, mean_d + 1.96 * se)


# ---------------------------------------------------------------- メイン
def main():
    books = cc.load()
    t_is = [p for _, p in books[("both", "IS")]]
    n_is = len(t_is)
    mean_is = sum(t_is) / n_is
    sd_is = math.sqrt(sum((x - mean_is) ** 2 for x in t_is) / (n_is - 1))
    s_is = sd_is / CAPITAL   # C族で使うIS推定の標準偏差（固定）

    const_grid = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 8]
    A_grid = [(k0, a) for k0 in const_grid for a in (0.5, 1.0)]
    B_grid = const_grid
    C_grid = [0.75, 1.0, 1.25]

    print(f"IS推定: 平均{mean_is:.1f}円 / 標準偏差{sd_is:.0f}円 / s_IS(x単位)={s_is:.6f}")
    print(f"方策数: constant={len(const_grid)} A={len(A_grid)} B={len(B_grid)} C={len(C_grid)}")

    results = {}   # (limit) -> dict(best_const=(k,params), best_dyn=(family,params))

    for limit_months in (2, 1):
        print("\n" + "=" * 90)
        print(f"【IS選択】期限 {limit_months}ヶ月")
        print("=" * 90)
        rate_is = n_is / MONTHS["IS"]
        H_is = int(round(rate_is * limit_months))
        paths_is = generate_paths(t_is, H_is, N_PATHS, L, seed=20260913 + limit_months)

        candidates = []
        for k in const_grid:
            candidates.append(("const", (k,), policy_constant(k)))
        for k0, a in A_grid:
            candidates.append(("A", (k0, a), policy_A(k0, a)))
        for k0 in B_grid:
            candidates.append(("B", (k0,), policy_B(k0)))
        for c in C_grid:
            candidates.append(("C", (c,), policy_C(c, s_is)))

        scored = []
        for fam, params, fn in candidates:
            r = run_policy(paths_is, fn, H_is)
            scored.append((fam, params, r["p_hit"], r))

        best_const = max((x for x in scored if x[0] == "const"), key=lambda x: x[2])
        best_dyn_by_fam = {}
        for fam in ("A", "B", "C"):
            best_dyn_by_fam[fam] = max((x for x in scored if x[0] == fam), key=lambda x: x[2])
        best_dyn = max(best_dyn_by_fam.values(), key=lambda x: x[2])

        print(f"  IS最良 constant: k={best_const[1][0]}  P(2倍)={100*best_const[2]:.1f}%")
        for fam, x in best_dyn_by_fam.items():
            print(f"  IS最良 {fam}: params={x[1]}  P(2倍)={100*x[2]:.1f}%")
        print(f"  → IS選択の動的方策: {best_dyn[0]}{best_dyn[1]}  P(2倍)={100*best_dyn[2]:.1f}%"
              f"{'  ★動的が上回る' if best_dyn[2] > best_const[2] else ''}")

        results[limit_months] = dict(const=(best_const[0], best_const[1]),
                                      dyn=(best_dyn[0], best_dyn[1]))

    fam_fn = {"const": policy_constant, "A": lambda p: policy_A(*p),
              "B": lambda p: policy_B(*p), "C": lambda p: policy_C(p[0], s_is)}

    print("\n" + "=" * 90)
    print("【固定方策をIS/OOS/FULLへ適用・ペア比較】")
    print("=" * 90)
    for limit_months in (2, 1):
        const_fam, const_params = results[limit_months]["const"]
        dyn_fam, dyn_params = results[limit_months]["dyn"]
        const_fn = fam_fn[const_fam](const_params) if const_fam != "const" else policy_constant(const_params[0])
        dyn_fn = fam_fn[dyn_fam](dyn_params)

        print(f"\n--- 期限{limit_months}ヶ月：constant={const_params} / 動的={dyn_fam}{dyn_params} ---")
        print(f"{'窓':>5}{'方策':>8}{'P(2倍)':>9}{'P(破綻)':>9}{'P(期限切れ)':>12}"
              f"{'到達中央値':>11}{'実現k平均':>10}{'上限到達率':>11}")
        for w in ("IS", "OOS", "FULL"):
            t = [p for _, p in books[("both", w)]]
            n = len(t)
            rate = n / MONTHS[w]
            H = int(round(rate * limit_months))
            paths = generate_paths(t, H, N_PATHS, L, seed=30000 + limit_months * 100 + hash(w) % 97)
            r_const = run_policy(paths, const_fn, H)
            r_dyn = run_policy(paths, dyn_fn, H)
            for name, r in (("constant", r_const), ("動的" + dyn_fam, r_dyn)):
                med = f"{r['median_steps']}" if r['median_steps'] is not None else "—"
                kmean = f"{r['k_mean']:.2f}" if r['k_mean'] is not None else "—"
                print(f"{w:>5}{name:>8}{100*r['p_hit']:>8.1f}%{100*r['p_ruin']:>8.1f}%"
                      f"{100*r['p_exp']:>11.1f}%{med:>11}{kmean:>10}{100*r['cap_hit_rate']:>10.1f}%")
            diff, ci = paired_diff(r_dyn, r_const, N_PATHS)
            sig = "有意" if ci[0] > 0 else ("有意に劣る" if ci[1] < 0 else "有意差なし")
            print(f"      差(動的-constant): {100*diff:+.2f}pt  95%CI [{100*ci[0]:+.2f}, {100*ci[1]:+.2f}]pt  ({sig})")

    print("\n完了。")


if __name__ == "__main__":
    main()
