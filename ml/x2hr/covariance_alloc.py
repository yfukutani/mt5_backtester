"""V026：候補1位「保有ポジションの共分散に応じた小幅な連続配分」の適格性判定（Codex設計）。

既存dealログ（時刻・magic・profit）だけを使い、新規のMT5測定・EA実装を行わずに、
日次×枠の共分散に基づく連続配分（基準配分の0.75〜1.25倍）が到達確率を改善するかを
粗く見積もる。設計はCodexへの相談（scratchpad/codex_v026_covariance.md）にそのまま従う。

【既知の限界（Codexの指摘・そのまま）】
- 時刻・magic・profitだけでは保有数量・方向・保有期間・含み損益が分からず、
  同時保有リスクの直接評価にはならない
- 決済時の倍率を全profitに掛けるため、エントリー時に数量を固定する実取引とは
  一致しない（dynamic_k.pyと同種の限界）
- ペア差の95%区間は固定された履歴に対するモンテカルロ誤差であり、将来の改善を
  保証する区間ではない
- 全体倍率kは配分側専用の探索をせず、V024で確定したケリー近傍値(k=1.0)を流用する
"""
from __future__ import annotations

import csv
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc

CAPITAL = cc.CAPITAL
RUIN = 0.10
TARGET_MULT = 2.0
K_FIXED = 1.0          # V024で確定したケリー近傍値。配分側専用の倍率探索はしない
WARMUP_DAYS = 180
COV_WINDOW = 180
MIN_NONZERO_DAYS = 20
HORIZON_DAYS = 60      # 「2ヶ月」の近似（Codex指定）
N_PATHS = 20000
BLOCK_DAYS = 20
WORST_DAY_FIXED = date(2026, 3, 2)   # 暗号枠パラメータ掃引で確認済みの最悪日


# ---------------------------------------------------------------- データ読み込み
def ea_deals_magic(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        m = int(r["magic"])
        if p == 0.0 or m == 0:
            continue
        out.append((int(r["time"]), m, p))
    out.sort()
    return out


def load_all_with_magic():
    runs = {}
    for f in ("results.csv", "results_grid.csv"):
        p = cc.FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                runs[r["window"]] = cc.FX / "run_deals" / r["deals"]
    fx = {w: ea_deals_magic(p) for w, p in runs.items()}

    gold = {}
    for f in ("results.csv", "results_is.csv"):
        p = cc.GOLD / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
                gold[r["window"]] = ea_deals_magic(cc.GOLD / "run_deals" / r["deals"])

    both = {}
    for w in ("IS", "OOS", "FULL"):
        if w in fx and w in gold:
            both[w] = sorted(fx[w] + gold[w])
    return both


# ---------------------------------------------------------------- 日次パネル
def build_daily_panel(deals):
    """(time, magic, profit) のリストから、暦日×magicの損益パネルを作る。
    ログ全体の最小日〜最大日を暦日で埋め、決済のない日は0にする。"""
    by_day = {}
    magics = set()
    for t, m, p in deals:
        d = datetime.fromtimestamp(t, tz=timezone.utc).date()
        magics.add(m)
        by_day.setdefault(d, {}).setdefault(m, 0.0)
        by_day[d][m] += p
    days = sorted(by_day.keys())
    magics = sorted(magics)
    full_days = []
    d = days[0]
    while d <= days[-1]:
        full_days.append(d)
        d += timedelta(days=1)
    panel = np.zeros((len(full_days), len(magics)))
    for i, d in enumerate(full_days):
        row = by_day.get(d, {})
        for j, m in enumerate(magics):
            panel[i, j] = row.get(m, 0.0)
    return full_days, magics, panel


# ---------------------------------------------------------------- 共分散・配分
def estimate_covariance(panel, idx, window=COV_WINDOW):
    lo = max(0, idx - window)
    hist = panel[lo:idx]        # 当日は含めない（先読み回避）
    if hist.shape[0] < 2:
        return None, None
    S = np.cov(hist, rowvar=False, ddof=1)
    if S.ndim == 0:
        S = np.array([[S]])
    D = np.diag(np.diag(S))
    Sigma = 0.5 * S + 0.5 * D
    nonzero_counts = (hist != 0).sum(axis=0)
    return Sigma, nonzero_counts


def compute_weights(Sigma, nonzero_counts, m, min_nonzero=MIN_NONZERO_DAYS):
    adjustable = nonzero_counts >= min_nonzero
    if adjustable.sum() < 2:
        return np.ones(m)
    c = Sigma.sum(axis=1)
    trace_m = np.trace(Sigma) / m
    denom = max(trace_m, 1e-9)
    c_bar_a = c[adjustable].mean()
    z = (c - c_bar_a) / denom

    def weights_for_lambda(lam):
        a = np.clip(1 - 0.25 * z + lam, 0.75, 1.25)
        return np.where(adjustable, a, 1.0)

    lo, hi = -2.0, 2.0
    for _ in range(60):
        mid = (lo + hi) / 2
        a = weights_for_lambda(mid)
        mean_adj = a[adjustable].mean()
        if mean_adj < 1:
            lo = mid
        else:
            hi = mid
    return weights_for_lambda((lo + hi) / 2)


def replay(panel, magics, exclude_days=frozenset()):
    """全期間で日次ウォークフォワード配分を計算し、baseline/weighted の日次合算損益列を返す。
    warmup(180日)より前はNoneを入れて後で除外する。exclude_daysはその日を評価・共分散推定
    の両方から除く（インデックスは詰めずNaNにして後段でフィルタする）。"""
    n_days, m = panel.shape
    baseline = panel.sum(axis=1).copy()
    weighted = np.full(n_days, np.nan)
    valid = np.ones(n_days, dtype=bool)

    # 除外日はパネルからも見えないようにする（共分散推定・評価の両方）
    panel_eff = panel.copy()
    for i in range(n_days):
        pass  # exclude_daysの適用はdays配列を使う呼び出し側で行う

    for idx in range(n_days):
        if idx < WARMUP_DAYS:
            continue
        Sigma, nz = estimate_covariance(panel_eff, idx)
        if Sigma is None:
            continue
        w = compute_weights(Sigma, nz, m)
        weighted[idx] = float((panel_eff[idx] * w).sum())
    return baseline, weighted, valid


# ---------------------------------------------------------------- 到達確率シミュレーション
def generate_day_blocks(n_days, horizon, n_paths, block=BLOCK_DAYS, seed=20260912):
    rng = np.random.default_rng(seed)
    n_blocks = horizon // block + 2
    starts = rng.integers(0, n_days, size=(n_paths, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n_days
    return idx.reshape(n_paths, -1)[:, :horizon]


def simulate(daily_series, day_idx_paths, k=K_FIXED):
    seq = daily_series[day_idx_paths]     # (n_paths, horizon)
    n_paths, H = seq.shape
    eq = np.full(n_paths, CAPITAL)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    for step in range(H):
        if not alive.any():
            break
        p = seq[:, step]
        new_eq = eq + k * p * (eq / CAPITAL)
        eq = np.where(alive, new_eq, eq)
        hit = alive & (eq >= CAPITAL * TARGET_MULT)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    p_hit = float((state == 1).mean())
    p_ruin = float((state == 2).mean())
    return p_hit, p_ruin, (state == 1)


def paired_diff(succ_a, succ_b, n):
    d = succ_a.astype(float) - succ_b.astype(float)
    mean_d = float(d.mean())
    se = float(d.std(ddof=1) / math.sqrt(n))
    return mean_d, (mean_d - 1.96 * se, mean_d + 1.96 * se)


# ---------------------------------------------------------------- メイン
def run_window(window_name, deals, exclude_label, exclude_day):
    days, magics, panel = build_daily_panel(deals)
    if exclude_day is not None and exclude_day in days:
        idx_ex = days.index(exclude_day)
        panel = np.delete(panel, idx_ex, axis=0)
        days = days[:idx_ex] + days[idx_ex + 1:]

    baseline, weighted, valid = replay(panel, magics)
    n_days = len(days)
    eval_start = WARMUP_DAYS
    base_eval = baseline[eval_start:]
    weighted_eval = weighted[eval_start:]
    n_eval = len(base_eval)

    day_paths = generate_day_blocks(n_eval, HORIZON_DAYS, N_PATHS,
                                     seed=hash((window_name, exclude_label)) % (2**31))
    p_hit_b, p_ruin_b, succ_b = simulate(base_eval, day_paths)
    p_hit_w, p_ruin_w, succ_w = simulate(weighted_eval, day_paths)
    diff, ci = paired_diff(succ_w, succ_b, N_PATHS)

    print(f"  [{window_name}/{exclude_label}] n_eval_days={n_eval}  枠数={len(magics)}")
    print(f"    baseline: P(2倍)={100*p_hit_b:.2f}%  P(破綻)={100*p_ruin_b:.2f}%")
    print(f"    配分後  : P(2倍)={100*p_hit_w:.2f}%  P(破綻)={100*p_ruin_w:.2f}%")
    print(f"    差(配分後-baseline): {100*diff:+.2f}pt  95%CI [{100*ci[0]:+.2f}, {100*ci[1]:+.2f}]pt")
    return dict(p_hit_b=p_hit_b, p_hit_w=p_hit_w, p_ruin_b=p_ruin_b, p_ruin_w=p_ruin_w,
                diff=diff, ci=ci)


def find_worst_baseline_day(deals):
    days, magics, panel = build_daily_panel(deals)
    baseline = panel.sum(axis=1)
    worst_idx = int(np.argmin(baseline))
    return days[worst_idx], baseline[worst_idx]


def main():
    books = load_all_with_magic()

    print("=" * 90)
    print("候補1位（共分散配分）の適格性判定 — k固定=1.0・期限60暦日（2ヶ月近似）")
    print("=" * 90)

    for w in ("IS", "OOS", "FULL"):
        if w not in books:
            continue
        print(f"\n### 窓: {w} ###")
        worst_day, worst_val = find_worst_baseline_day(books[w])
        print(f"  baseline最悪日: {worst_day}（{worst_val:,.0f}円）")

        run_window(w, books[w], "全日", None)
        run_window(w, books[w], "2026-03-02除外", WORST_DAY_FIXED)
        if worst_day != WORST_DAY_FIXED:
            run_window(w, books[w], f"基準最悪日({worst_day})除外", worst_day)


if __name__ == "__main__":
    main()
