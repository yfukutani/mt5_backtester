"""V034：失敗内訳（破綻 vs 期限切れ）の確定と、期限後継続の楽観上限（Codex優先度1位）。

【Codexの指示（V033・Q4の1位）】
> 評価条件を揃え、現在の到達確率と失敗内訳を確定する。
> 目的は、**何pt足りず、破綻と期限切れのどちらが主因かを確定すること**。

【Codexの提案（V033・Q3）】
> 期限切れパスを全て救済できると仮定した **P_hit + P_expiry** は、
> **既存方策を期限後まで継続する場合の楽観上限**として安く計算できます。
> ただし、期限前の方策まで変更した場合の上限には使えません。

【評価条件を揃える】
- サイジング：V029のエントリー時方式（`dynamic_k_lag.run_policy_lag(entry_sizing=True)`）
- H：V030の案a（IS窓の頻度で固定し、全窓に同じHを適用）
- 倍率kの選択：IS窓でグリッド総当たり（OOSを見て選び直さない）
- 破綻ライン：10%（R7の暫定値）

【失敗内訳の読み方】
- **破綻が主因**なら、倍率kを下げる余地がある（安全側に振れば期限切れは増えるが破綻は減る）
- **期限切れが主因**なら、倍率kを上げる余地がある——ただしIS選択がkを上げないなら、
  それは「IS窓では上げると悪化した」ことを意味し、OOSだけを見て上げるのは先読みになる

【複数シードで履歴標本の不確実性を見る】
Codexは「シード差だけでなく、暦日ブロックの再標本化による履歴標本の不確実性も評価する」
ことを求めた。本スクリプトは複数シードでの再標本化のばらつきを出す（完全な履歴不確実性の
評価ではない——同じ2,053取引を並べ替えているだけである点は限界として明記する）。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

MONTHS = cc.MONTHS
N_PATHS = dkl.N_PATHS
K_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
SEEDS = (11, 22, 33, 44, 55)
DEADLINES = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 12.0, 24.0)

# V029/V030でIS窓から選ばれた動的方策（該当する期限のみ・選び直さない）
DYN = {2.0: ("B", (3.0,)), 6.0: ("A", (1.0, 1.0))}


def mean_ci(vals):
    a = np.asarray(vals, dtype=float)
    m = float(a.mean())
    if a.size < 2:
        return m, m, m
    se = float(a.std(ddof=1) / math.sqrt(a.size))
    return m, m - 1.96 * se, m + 1.96 * se


def main():
    books = dkl.build_books()
    pr_is, lg_is, _ = books["IS"]
    s_is = float(pr_is.std(ddof=1)) / cc.CAPITAL
    rate_is = len(pr_is) / MONTHS["IS"]
    fam_fn = {"A": lambda p: dk.policy_A(*p), "B": lambda p: dk.policy_B(p[0]),
              "C": lambda p: dk.policy_C(p[0], s_is)}

    print("=" * 108)
    print("V034：失敗内訳（破綻 vs 期限切れ）の確定と、期限後継続の楽観上限")
    print("=" * 108)
    print("条件: エントリー時サイジング(V029) / H=IS頻度で固定(V030案a) / "
          "kはIS選択 / 破綻ライン10%")
    print(f"      シード{len(SEEDS)}本の平均と95%CI（再標本化のばらつき。履歴標本の"
          f"不確実性そのものではない）\n")

    print(f"{'期限':>6}{'H':>6}{'方策':>10}{'IS選択k':>9}"
          f"{'OOS到達':>9}{'OOS破綻':>9}{'OOS期限切れ':>12}"
          f"{'主因':>8}{'85%まで':>9}{'楽観上限':>10}")

    rows = []
    for lim in DEADLINES:
        H = int(round(rate_is * lim))
        # --- IS窓でkを選ぶ（シード平均で選ぶ。OOSは見ない） ---
        scores = {k: [] for k in K_GRID}
        for sd in SEEDS:
            p_is, l_is = dkl.generate_paths_lag(pr_is, lg_is, H, N_PATHS,
                                                seed=610000 + int(lim * 100) + sd)
            for k in K_GRID:
                r = dkl.run_policy_lag(p_is, l_is, dk.policy_constant(k),
                                       entry_sizing=True)
                scores[k].append(r["p_hit"])
        k_sel = max(K_GRID, key=lambda k: float(np.mean(scores[k])))

        policies = [("constant", dk.policy_constant(k_sel), f"{k_sel}")]
        if lim in DYN:
            fam, prm = DYN[lim]
            policies.append((f"動的{fam}", fam_fn[fam](prm), f"{prm}"))

        for name, fn, kdesc in policies:
            hits, ruins, exps = [], [], []
            for sd in SEEDS:
                p_o, l_o = dkl.generate_paths_lag(books["OOS"][0], books["OOS"][1],
                                                  H, N_PATHS,
                                                  seed=620000 + int(lim * 100) + sd)
                r = dkl.run_policy_lag(p_o, l_o, fn, entry_sizing=True)
                hits.append(r["p_hit"]); ruins.append(r["p_ruin"]); exps.append(r["p_exp"])
            mh, lo, hi = mean_ci(hits)
            mr, _, _ = mean_ci(ruins)
            me, _, _ = mean_ci(exps)
            cause = "破綻" if mr > me else "期限切れ"
            upper = mh + me
            rows.append((lim, H, name, kdesc, mh, lo, hi, mr, me, cause, upper))
            print(f"{lim:>5.0f}月{H:>6}{name:>10}{kdesc:>9}"
                  f"{100*mh:>8.1f}%{100*mr:>8.1f}%{100*me:>11.1f}%"
                  f"{cause:>8}{100*(0.85-mh):>+8.1f}pt{100*upper:>9.1f}%")

    print("\n" + "=" * 108)
    print("【Codexの判定水準：片側95%上限が85%未満なら『当該固定方策は85%未達』を支持】")
    print("=" * 108)
    print(f"{'期限':>6}{'方策':>10}{'到達平均':>10}{'95%CI上限':>11}{'判定':>22}")
    for lim, H, name, kdesc, mh, lo, hi, mr, me, cause, upper in rows:
        v = "✅ 85%未達を支持" if hi < 0.85 else ("— 判定保留（CIが85%を跨ぐ）"
                                              if lo < 0.85 else "❌ 85%達成")
        print(f"{lim:>5.0f}月{name:>10}{100*mh:>9.1f}%{100*hi:>10.1f}%{v:>22}")

    print("\n" + "=" * 108)
    print("【楽観上限：期限切れパスを全て救済できると仮定した P(到達)+P(期限切れ)】")
    print("=" * 108)
    print("※ 既存方策を期限後もそのまま継続した場合の上限。期限前の方策を変えた場合には使えない。")
    print(f"{'期限':>6}{'方策':>10}{'到達':>9}{'+期限切れ':>11}{'楽観上限':>10}{'85%':>8}")
    for lim, H, name, kdesc, mh, lo, hi, mr, me, cause, upper in rows:
        print(f"{lim:>5.0f}月{name:>10}{100*mh:>8.1f}%{100*me:>10.1f}%"
              f"{100*upper:>9.1f}%{'✅' if upper >= 0.85 else '❌':>8}")

    print("\n完了。")


if __name__ == "__main__":
    main()
