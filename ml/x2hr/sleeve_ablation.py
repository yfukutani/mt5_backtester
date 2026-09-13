"""V031：新たな軸（第2弾）——**到達確率そのものを目的関数にした枠の取捨選択**。

【動機：V026が失敗した理由を裏返す】
V026（共分散配分）は全9条件で−2.4〜−2.9pt悪化した。Codexと共有した原因分析は
「**共分散の高い枠（GOLD系）が同時に期待値の最も高い枠でもあった**」——つまり
**共分散という代理指標が、真の目的（到達確率）と逆を向いていた**というものだった。

ならば代理指標をやめ、**到達確率そのものを目的関数にして枠を取捨選択すれば良い。**
これはV026とは別の軸である（V026は全枠を残したまま0.75〜1.25倍に重み付けした。
本検証は枠を「入れる/入れない」の離散選択にし、目的関数を代理指標から本命に変える）。

【なぜ効く可能性があるか】
期限付きの2倍到達問題では、ブックの1取引あたりの m/s²（≒シャープの二乗）が大きいほど
必要な倍率kが下がり、同じ破綻ラインでより高い到達確率が得られる。期待値が薄く分散だけ
大きい枠が混ざっていれば、**それを外すだけでブック全体の m/s² が上がる**。
一方で枠を外すと**取引頻度が下がり、期限内の試行回数Hが減る**——これは逆風になる。
どちらが勝つかは測らないと分からない。

【測定設計（事前登録・選択方法は1つに固定する）】
V024の教訓（複数の選択方法を試してOOSで良かったものを報告する＝多重比較バイアス）に
従い、**以下の手順を1回だけ実行する。**

1. **IS窓を日付で前半・後半に分ける**（前半のみで選択する）
2. IS前半で **貪欲前向き選択**（空集合から始め、加えて到達確率が最も上がる枠を1つずつ追加）。
   各部分集合について倍率kはグリッド総当たりで最良を選ぶ
3. IS前半で到達確率が最大になった「枠の部分集合 + k」を**固定する**
4. その固定した構成を **IS後半**（未使用の独立データ）へ適用
5. さらに **OOS窓**へ適用
6. 比較対象は「全枠 + IS前半で選んだ最良k」（同じ手続きで選んだ定数k方策）

**継続基準（事前に宣言する）**: IS後半・OOSの**両方**で全枠比 +2pt以上、かつ
対応付き95%CI下限 > 0。片方でも満たさなければ却下する。

【重要な限界】
枠の取捨選択は探索自由度が大きい（15枠の部分集合は32,767通り。貪欲法でも120通りを見る）。
IS前半だけで選ぶ手続きにしてあるが、**IS後半とOOSは「1回だけ」使う**。
ここで良い結果が出ても、選び直して再報告することはしない。
"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

CAPITAL = cc.CAPITAL
RUIN = 0.10
MONTHS = cc.MONTHS
N_PATHS = 20000
L = 20
K_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
DEADLINES = (2.0, 6.0)

MAGIC_NAME = {
    20260622: "PB USDJPY",   20260627: "PB GBPJPY",   20260628: "PB AUDJPY",
    20260640: "PB GOLD",     20260610: "RSI USDJPY",  20260605: "RSI EURUSD",
    20260774: "RSI GBPUSD",  20260650: "Carry AUDJPY", 20260680: "VBO USDJPY",
    20260710: "ETH TrendHold", 20261000: "SCA USDJPY", 20261001: "SCA GBPJPY",
    20261002: "SCA GOLD1",   20261003: "SCA GOLD2",   20260720: "BTC funding",
    20260629: "PairTrade",
}


# ---------------------------------------------------------------- データ
def load_by_magic(window):
    """窓の (time, profit, magic) を返す（correct_ceiling と同じ実行結果・同じ除外規則）。"""
    fx, gold = dkl.resolve_runs()
    rows = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            p = float(r["profit"])
            if m == 0 or p == 0.0:
                continue
            rows.append((int(r["time"]), p, m))
    rows.sort()
    return rows


def subset_trades(rows, magics):
    return np.array([p for _, p, m in rows if m in magics], dtype=float)


def run_constant(paths, k, horizon):
    """定数倍率kでの到達・破綻シミュレーション（比例サイジング）。"""
    n_paths, H = paths.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    for step in range(H):
        if not alive.any():
            break
        new_eq = eq + paths[:, step] * k * (eq / CAPITAL)
        eq = np.where(alive, new_eq, eq)
        hit = alive & (eq >= CAPITAL * 2.0)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return dict(p_hit=float((state == 1).mean()), p_ruin=float((state == 2).mean()),
                p_exp=float((state == 0).mean()), success=(state == 1))


def evaluate(trades, months, deadline, seed, k_list):
    """与えられた取引列について、期限deadlineでk_listを総当たりし最良を返す。"""
    if len(trades) < 3 * L:
        return None
    H = int(round(len(trades) / months * deadline))
    if H < 5:
        return None
    paths = dk.generate_paths(trades, H, N_PATHS, L, seed)
    best = None
    for k in k_list:
        r = run_constant(paths, k, H)
        if best is None or r["p_hit"] > best[1]["p_hit"]:
            best = (k, r)
    return dict(k=best[0], H=H, n=len(trades), **{kk: vv for kk, vv in best[1].items()})


def sleeve_stats(rows, magics):
    out = []
    for m in sorted(magics):
        p = np.array([x[1] for x in rows if x[2] == m], dtype=float)
        if len(p) < 2:
            continue
        mu, sd = p.mean(), p.std(ddof=1)
        out.append((m, len(p), mu, sd, mu / sd if sd > 0 else 0.0,
                    mu / (sd ** 2) * CAPITAL if sd > 0 else 0.0))
    return out


# ---------------------------------------------------------------- メイン
def main():
    deadline = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0

    rows_is = load_by_magic("IS")
    rows_oos = load_by_magic("OOS")
    magics = sorted({m for _, _, m in rows_is} & {m for _, _, m in rows_oos})

    # IS窓を日付で前半・後半に分ける
    t0, t1 = rows_is[0][0], rows_is[-1][0]
    tmid = (t0 + t1) // 2
    is_a = [r for r in rows_is if r[0] < tmid]
    is_b = [r for r in rows_is if r[0] >= tmid]
    mo_a = MONTHS["IS"] * (tmid - t0) / (t1 - t0)
    mo_b = MONTHS["IS"] - mo_a

    print("=" * 96)
    print(f"V031：到達確率そのものを目的関数にした枠の取捨選択（期限 {deadline:g}ヶ月）")
    print("=" * 96)
    print(f"IS前半 {len(is_a)}取引 / {mo_a:.1f}ヶ月   "
          f"IS後半 {len(is_b)}取引 / {mo_b:.1f}ヶ月   OOS {len(rows_oos)}取引")
    print(f"対象枠 {len(magics)}件\n")

    print("【IS前半の枠別統計（参考・選択には使わない）】")
    print(f"{'枠':>16}{'取引数':>7}{'平均円':>9}{'標準偏差':>9}"
          f"{'シャープ/取引':>13}{'m/s²(資金比)':>13}")
    for m, n, mu, sd, sh, ks in sorted(sleeve_stats(is_a, magics),
                                       key=lambda x: -x[4]):
        print(f"{MAGIC_NAME.get(m, str(m)):>16}{n:>7}{mu:>9.1f}{sd:>9.0f}"
              f"{sh:>13.4f}{ks:>13.4f}")

    # --- 手順1-2: IS前半で貪欲前向き選択 ---
    print(f"\n【IS前半で貪欲前向き選択】（k={K_GRID} を毎回総当たり）")
    chosen = set()
    remaining = set(magics)
    history = []
    best_overall = None
    seed_sel = 770000 + int(deadline * 100)
    while remaining:
        cand_best = None
        for m in sorted(remaining):
            trial = chosen | {m}
            tr = subset_trades(is_a, trial)
            res = evaluate(tr, mo_a, deadline, seed_sel, K_GRID)
            if res is None:
                continue
            if cand_best is None or res["p_hit"] > cand_best[1]["p_hit"]:
                cand_best = (m, res)
        if cand_best is None:
            break
        m, res = cand_best
        chosen.add(m)
        remaining.discard(m)
        history.append((len(chosen), m, res))
        mark = ""
        if best_overall is None or res["p_hit"] > best_overall[1]["p_hit"]:
            best_overall = (set(chosen), res)
            mark = " ★最良更新"
        print(f"  {len(chosen):>2}枠目 +{MAGIC_NAME.get(m, str(m)):<16} "
              f"k={res['k']:<4} H={res['H']:<4} n={res['n']:<5} "
              f"P(2倍)={100*res['p_hit']:5.1f}%{mark}")

    sel_magics, sel_res = best_overall
    print(f"\n  → IS前半で選ばれた構成: {len(sel_magics)}枠 / k={sel_res['k']} / "
          f"P(2倍)={100*sel_res['p_hit']:.1f}%")
    print("    採用: " + ", ".join(MAGIC_NAME.get(m, str(m)) for m in sorted(sel_magics)))
    dropped = sorted(set(magics) - sel_magics)
    print("    除外: " + (", ".join(MAGIC_NAME.get(m, str(m)) for m in dropped)
                        if dropped else "なし（全枠採用）"))

    # 比較対象：全枠でIS前半から選んだ最良k
    full_a = evaluate(subset_trades(is_a, set(magics)), mo_a, deadline, seed_sel, K_GRID)
    print(f"  （比較対象）全枠 k={full_a['k']} / P(2倍)={100*full_a['p_hit']:.1f}%  "
          f"→ IS前半での差 {100*(sel_res['p_hit'] - full_a['p_hit']):+.2f}pt")

    if not dropped:
        print("\n  枠を1つも外さなかったため、以降の検証は不要。**この軸は却下。**")
        return

    # --- 手順4-5: IS後半・OOSへ適用（構成もkも固定・選び直さない） ---
    k_sel, k_full = sel_res["k"], full_a["k"]
    print("\n" + "=" * 96)
    print("【固定した構成を独立データへ適用（構成もkも選び直さない）】")
    print("=" * 96)
    print(f"  選択構成: {len(sel_magics)}枠 k={k_sel}   /   全枠: {len(magics)}枠 k={k_full}")
    print(f"\n{'データ':>10}{'方策':>10}{'取引数':>7}{'H':>5}"
          f"{'P(2倍)':>9}{'P(破綻)':>9}{'P(期限切れ)':>12}")

    verdicts = []
    for label, rows_, months_ in (("IS後半", is_b, mo_b), ("OOS", rows_oos, MONTHS["OOS"])):
        seed = 880000 + int(deadline * 100) + (0 if label == "IS後半" else 7)
        out = {}
        for nm, mags, kk in (("選択構成", sel_magics, k_sel), ("全枠", set(magics), k_full)):
            tr = subset_trades(rows_, mags)
            H = int(round(len(tr) / months_ * deadline))
            paths = dk.generate_paths(tr, H, N_PATHS, L, seed)
            r = run_constant(paths, kk, H)
            out[nm] = r
            print(f"{label:>10}{nm:>10}{len(tr):>7}{H:>5}{100*r['p_hit']:>8.1f}%"
                  f"{100*r['p_ruin']:>8.1f}%{100*r['p_exp']:>11.1f}%")
        # 取引列が違うのでパスは共有できない。独立標本としての差と誤差を出す
        pa, pb = out["選択構成"]["p_hit"], out["全枠"]["p_hit"]
        se = math.sqrt(pa * (1 - pa) / N_PATHS + pb * (1 - pb) / N_PATHS)
        lo, hi = (pa - pb) - 1.96 * se, (pa - pb) + 1.96 * se
        ok = (pa - pb) >= 0.02 and lo > 0
        verdicts.append(ok)
        print(f"{'':>10}  差(選択-全枠): {100*(pa-pb):+.2f}pt "
              f"95%CI[{100*lo:+.2f},{100*hi:+.2f}]pt "
              f"→ 継続基準(+2pt以上かつCI下限>0): {'✅満たす' if ok else '❌満たさない'}")

    print("\n" + "=" * 96)
    if all(verdicts):
        print("判定: ✅ IS後半・OOSの両方で継続基準を満たした。この軸は有望。")
    else:
        print("判定: ❌ 継続基準を満たさない。**この軸は却下。**")
    print("=" * 96)


if __name__ == "__main__":
    main()
