"""V023：V007〜V011の「最良k」表全体を、先読みバイアスのない正しい手順で再計算する。

V015で、旧方式（各窓の結果を見てから、その窓で最良だったkを選ぶ）が先読みバイアスを
含むと判明した。本スクリプトはIS窓だけでkを選びOOS/FULLへ適用する正しい手順で全期限を測る。

【重要な追加修正】長い期限（特に24ヶ月）ではIS上での成績がk=0.3〜0.8あたりでほぼ
平ら（プラトー）になり、1回のIS bootstrapだけでkを選ぶと、その回のノイズで最適から
少しずれたkを選んでしまう。**IS選択自体を複数seedで平均し、ノイズを減らしてから
最良kを決める**ことで、より信頼できる選択にする。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk

CONST_GRID = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 8]
LIMITS = [1, 2, 3, 4, 5, 6, 12, 24]   # 2/6/12も再掲して一覧性を確保


def main():
    books = cc.load()
    t_is = [p for _, p in books[("both", "IS")]]
    n_is = len(t_is)
    rate_is = n_is / dk.MONTHS["IS"]

    is_seeds = [50000, 150000, 250000]   # IS選択自体のノイズを減らすための複数seed

    print(f"{'期限':>6}{'IS選択k':>9}{'IS':>9}{'OOS':>9}{'FULL':>9}{'OOS内訳(破綻/期限切れ)':>26}")
    rows = []
    for limit in LIMITS:
        H_is = int(round(rate_is * limit))
        avg_scores = {}
        for k in CONST_GRID:
            vals = []
            for s in is_seeds:
                paths_is = dk.generate_paths(t_is, H_is, dk.N_PATHS, dk.L, seed=s + limit)
                r = dk.run_policy(paths_is, dk.policy_constant(k), H_is)
                vals.append(r["p_hit"])
            avg_scores[k] = sum(vals) / len(vals)
        best_k = max(avg_scores, key=avg_scores.get)
        fn = dk.policy_constant(best_k)

        results = {}
        for w in ("IS", "OOS", "FULL"):
            t = [p for _, p in books[("both", w)]]
            n = len(t)
            rate = n / dk.MONTHS[w]
            H = int(round(rate * limit))
            # OOS/FULLも複数seedで平均し安定させる
            accs = None
            for s in (60000, 70000, 80000):
                paths = dk.generate_paths(t, H, dk.N_PATHS, dk.L, seed=s + limit * 100 + hash(w) % 97)
                r = dk.run_policy(paths, fn, H)
                if accs is None:
                    accs = {k2: [] for k2 in r}
                for k2, v in r.items():
                    if isinstance(v, (int, float)):
                        accs[k2].append(v)
            results[w] = {k2: (sum(v) / len(v) if v else None) for k2, v in accs.items()}

        oos = results["OOS"]
        detail = f"{100*oos['p_ruin']:.1f}%/{100*oos['p_exp']:.1f}%"
        print(f"{limit:>5}月{best_k:>9}{100*results['IS']['p_hit']:>8.1f}%"
              f"{100*results['OOS']['p_hit']:>8.1f}%{100*results['FULL']['p_hit']:>8.1f}%{detail:>26}")
        rows.append((limit, best_k, results))

    print("\n表（Markdown用）:")
    print("| 期限 | IS選択k | IS | OOS | FULL |")
    print("|---|---:|---:|---:|---:|")
    for limit, k, r in rows:
        print(f"| {limit}ヶ月 | {k} | {100*r['IS']['p_hit']:.1f}% | "
              f"{100*r['OOS']['p_hit']:.1f}% | {100*r['FULL']['p_hit']:.1f}% |")


if __name__ == "__main__":
    main()
