"""V029：動的サイジングの「エントリー時 vs 決済時のk不一致」を修正して再測定する。

【Codexの指摘（C11）】
`dynamic_k.py` は、決済損益 profit に対して**決済時点の**状態（残り時間h・資金水準x）から
求めたkを掛けている。しかし実際のEAは**エントリー時点で**ロットを決める。保有期間が長い枠
（PB は数日、Carry は数週間）では、決済時のkとエントリー時のkが大きく食い違う。

**これは動的方策に有利な方向のバイアスになりうる。** 例えば方策B（目標距離×残り時間）は
「資金が減ったら増額」する。決済時に資金が減っていればkを上げるが、その取引は既に終わって
おり、上げたkが適用されるのは**その負け取引そのもの**である。つまり「負けると分かっている
取引のロットだけを後から増やす／減らす」という、実装不可能な情報の使い方になっていた。

【修正内容】
dealログから position_id で建玉の保有区間を復元し、各取引に **lag（エントリーから決済まで
の間にブック全体で何件の取引が決済されたか）** を付与する。シミュレーションでは
step s で決済される取引のサイズ倍率を **M[s − lag]**（＝エントリー時点の状態から決めた倍率）
とする。到達・破綻の判定は従来どおり決済時に行う。

【測定設計（事前登録）】
- 選択手続きはV014/V015と**完全に同一**（IS窓でグリッド総当たり→p_hit最大を選ぶ）。
  修正後エンジンで選び直し、OOS/FULLに適用する。選択方法を後から変えない。
- 旧エンジン（決済時サイジング）の結果も同じパスで併記し、**規約の違いが何ptだったか**を示す。
- lagの分布も出力する（不一致がそもそも無視できるかを先に確認するため）。
"""
from __future__ import annotations

import bisect
import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk

CAPITAL = cc.CAPITAL
RUIN = dk.RUIN
MONTHS = cc.MONTHS
K_CAP = dk.K_CAP
N_PATHS = dk.N_PATHS
L = dk.L


# ---------------------------------------------------------------- lag付きブックの構築
def deal_rows(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["magic"]) == 0:
            continue
        rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                     float(r["profit"])))
    rows.sort()
    return rows


def positions_from(path):
    """(t_out, profit, t_in) を復元する。profit==0 の決済は correct_ceiling と同様に除外。"""
    opened = {}
    out = []
    unmatched = 0
    for t, entry, pid, profit in deal_rows(path):
        if entry == 0:
            opened[pid] = t
        else:
            t_in = opened.pop(pid, None)
            if t_in is None:
                unmatched += 1
                continue
            if profit == 0.0:
                continue
            out.append((t, profit, t_in))
    out.sort()
    return out, unmatched


def resolve_runs():
    """correct_ceiling.load() と同じ実行結果を指すパスを窓ごとに返す。"""
    fx, gold = {}, {}
    for f in ("results.csv", "results_grid.csv"):
        p = cc.FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                fx[r["window"]] = cc.FX / "run_deals" / r["deals"]
    for f in ("results.csv", "results_is.csv"):
        p = cc.GOLD / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
                gold[r["window"]] = cc.GOLD / "run_deals" / r["deals"]
    return fx, gold


def build_books():
    """窓 -> (profits, lags) を作る。lag は「エントリー〜決済の間にブックで決済された件数」。"""
    fx, gold = resolve_runs()
    books = {}
    for w in ("IS", "OOS", "FULL"):
        if w not in fx or w not in gold:
            continue
        pos, unm = positions_from(fx[w])
        pg, unm2 = positions_from(gold[w])
        pos = sorted(pos + pg)
        t_out = [p[0] for p in pos]
        profits = np.array([p[1] for p in pos], dtype=float)
        lags = np.empty(len(pos), dtype=np.int32)
        for i, (to, _, ti) in enumerate(pos):
            # ti 時点で「すでに決済済み」の件数 = t_out < ti の個数
            settled_at_entry = bisect.bisect_left(t_out, ti)
            lags[i] = max(0, i - settled_at_entry)
        books[w] = (profits, lags, unm + unm2)
    return books


# ---------------------------------------------------------------- シミュレーション
def generate_paths_lag(profits, lags, horizon_steps, n_paths, seed):
    """ブロックブートストラップ。損益とlagを同じ添字で取り出す（lagは取引に付随する）。"""
    rng = np.random.default_rng(seed)
    n = len(profits)
    n_blocks = horizon_steps // L + 2
    starts = rng.integers(0, n, size=(n_paths, n_blocks))
    offsets = np.arange(L)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    idx = idx.reshape(n_paths, -1)[:, :horizon_steps]
    return profits[idx], lags[idx]


def run_policy_lag(path_profit, path_lag, policy_fn, entry_sizing=True):
    """entry_sizing=True でエントリー時サイジング（修正版）、False で決済時（旧V014）。"""
    n_paths, H = path_profit.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    stop_step = np.full(n_paths, H, dtype=np.int32)
    mult_hist = np.zeros((n_paths, H), dtype=np.float32)   # 各stepで「有効だった」サイズ倍率
    rows = np.arange(n_paths)
    k_sum = 0.0
    k_cnt = 0
    cap_hits = 0

    for step in range(H):
        if not alive.any():
            break
        h = float(H - step)
        x = eq / CAPITAL
        k = np.clip(policy_fn(h, float(H), x), 0.0, K_CAP)
        mult_now = k * x                      # 倍率 × 資金比 ＝ 実際のロット比
        mult_hist[:, step] = mult_now
        if step % 5 == 0:
            sub = k[alive]
            if sub.size:
                k_sum += float(sub.sum())
                k_cnt += sub.size
                cap_hits += int((sub >= K_CAP - 1e-9).sum())

        if entry_sizing:
            src = np.maximum(step - path_lag[:, step], 0)   # エントリー時点のstep
            mult_use = mult_hist[rows, src]
        else:
            mult_use = mult_now

        new_eq = eq + path_profit[:, step] * mult_use
        eq = np.where(alive, new_eq, eq)
        hit_now = alive & (eq >= CAPITAL * 2.0)
        ruin_now = alive & (eq <= CAPITAL * RUIN)
        state[hit_now] = 1
        state[ruin_now] = 2
        stop_step[hit_now | ruin_now] = step + 1
        alive = alive & ~(hit_now | ruin_now)

    hit_steps = stop_step[state == 1]
    return dict(
        p_hit=float((state == 1).mean()),
        p_ruin=float((state == 2).mean()),
        p_exp=float((state == 0).mean()),
        median_steps=int(np.median(hit_steps)) if hit_steps.size else None,
        k_mean=(k_sum / k_cnt) if k_cnt else None,
        cap_hit_rate=(cap_hits / k_cnt) if k_cnt else 0.0,
        success=(state == 1),
    )


# ---------------------------------------------------------------- メイン
def main():
    limits = [float(a) for a in sys.argv[1:]] or [2.0, 6.0]
    books = build_books()

    print("=" * 96)
    print("V029：エントリー時サイジングへの修正（Codex指摘C11）")
    print("=" * 96)
    print("\n【lagの分布】エントリーから決済までにブックで決済された取引件数")
    print(f"{'窓':>6}{'取引数':>8}{'未突合':>7}{'lag平均':>9}{'中央値':>8}"
          f"{'90%点':>8}{'最大':>8}{'lag=0率':>9}")
    for w in ("IS", "OOS", "FULL"):
        if w not in books:
            continue
        pr, lg, unm = books[w]
        print(f"{w:>6}{len(pr):>8}{unm:>7}{lg.mean():>9.1f}{int(np.median(lg)):>8}"
              f"{int(np.percentile(lg, 90)):>8}{lg.max():>8}{100*(lg == 0).mean():>8.1f}%")

    pr_is, lg_is, _ = books["IS"]
    n_is = len(pr_is)
    mean_is = float(pr_is.mean())
    sd_is = float(pr_is.std(ddof=1))
    s_is = sd_is / CAPITAL
    print(f"\nIS推定: 平均{mean_is:.1f}円 / 標準偏差{sd_is:.0f}円 / s_IS={s_is:.6f}")

    const_grid = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 8]
    A_grid = [(k0, a) for k0 in const_grid for a in (0.5, 1.0)]
    B_grid = const_grid
    C_grid = [0.75, 1.0, 1.25]
    fam_fn = {"const": lambda p: dk.policy_constant(p[0]),
              "A": lambda p: dk.policy_A(*p),
              "B": lambda p: dk.policy_B(p[0]),
              "C": lambda p: dk.policy_C(p[0], s_is)}

    selected = {}
    for lim in limits:
        H_is = int(round(n_is / MONTHS["IS"] * lim))
        p_is, l_is = generate_paths_lag(pr_is, lg_is, H_is, N_PATHS,
                                        seed=20260912 + int(lim * 10))
        cands = ([("const", (k,)) for k in const_grid]
                 + [("A", p) for p in A_grid]
                 + [("B", (k,)) for k in B_grid]
                 + [("C", (c,)) for c in C_grid])
        scored = []
        for fam, params in cands:
            r = run_policy_lag(p_is, l_is, fam_fn[fam](params), entry_sizing=True)
            scored.append((fam, params, r["p_hit"]))
        best_const = max((s for s in scored if s[0] == "const"), key=lambda s: s[2])
        by_fam = {f: max((s for s in scored if s[0] == f), key=lambda s: s[2])
                  for f in ("A", "B", "C")}
        best_dyn = max(by_fam.values(), key=lambda s: s[2])
        selected[lim] = (best_const, best_dyn)

        print("\n" + "=" * 96)
        print(f"【IS選択（修正後エンジン）】期限 {lim:g}ヶ月 / H={H_is}取引")
        print("=" * 96)
        print(f"  IS最良 constant: k={best_const[1][0]}  P(2倍)={100*best_const[2]:.1f}%")
        for f, s in by_fam.items():
            print(f"  IS最良 {f}: params={s[1]}  P(2倍)={100*s[2]:.1f}%")
        print(f"  → IS選択の動的方策: {best_dyn[0]}{best_dyn[1]}  "
              f"P(2倍)={100*best_dyn[2]:.1f}%"
              f"{'  ★動的が上回る' if best_dyn[2] > best_const[2] else '  （動的は上回らない）'}")

    print("\n" + "=" * 96)
    print("【固定方策を各窓へ適用：修正版（エントリー時） vs 旧版（決済時）】")
    print("=" * 96)
    for lim in limits:
        best_const, best_dyn = selected[lim]
        cfn = fam_fn[best_const[0]](best_const[1])
        dfn = fam_fn[best_dyn[0]](best_dyn[1])
        print(f"\n--- 期限{lim:g}ヶ月：constant k={best_const[1][0]} / "
              f"動的={best_dyn[0]}{best_dyn[1]} ---")
        print(f"{'窓':>5}{'規約':>14}{'方策':>10}{'P(2倍)':>9}{'P(破綻)':>9}"
              f"{'P(期限切れ)':>12}{'実現k平均':>10}")
        for w in ("IS", "OOS", "FULL"):
            if w not in books:
                continue
            pr, lg, _ = books[w]
            H = int(round(len(pr) / MONTHS[w] * lim))
            pp, pl = generate_paths_lag(pr, lg, H, N_PATHS,
                                        seed=30000 + int(lim * 100) + hash(w) % 97)
            store = {}
            for conv, es in (("修正(entry)", True), ("旧(exit)", False)):
                rc = run_policy_lag(pp, pl, cfn, entry_sizing=es)
                rd = run_policy_lag(pp, pl, dfn, entry_sizing=es)
                store[conv] = (rc, rd)
                for nm, r in (("constant", rc), ("動的" + best_dyn[0], rd)):
                    km = f"{r['k_mean']:.2f}" if r["k_mean"] is not None else "—"
                    print(f"{w:>5}{conv:>14}{nm:>10}{100*r['p_hit']:>8.1f}%"
                          f"{100*r['p_ruin']:>8.1f}%{100*r['p_exp']:>11.1f}%{km:>10}")
                d, ci = dk.paired_diff(rd, rc, N_PATHS)
                sig = "有意" if ci[0] > 0 else ("有意に劣る" if ci[1] < 0 else "有意差なし")
                print(f"{'':>5}{'':>14}  差(動的-const): {100*d:+.2f}pt "
                      f"95%CI[{100*ci[0]:+.2f},{100*ci[1]:+.2f}]pt ({sig})")
            # 規約そのものの影響（同一方策・同一パスでの対応付き差）
            for nm, i in (("constant", 0), ("動的", 1)):
                a = store["修正(entry)"][i]
                b = store["旧(exit)"][i]
                d, ci = dk.paired_diff(a, b, N_PATHS)
                print(f"{'':>5}{'':>14}  規約差({nm}: entry-exit): {100*d:+.2f}pt "
                      f"95%CI[{100*ci[0]:+.2f},{100*ci[1]:+.2f}]pt")

    print("\n完了。")


if __name__ == "__main__":
    main()
