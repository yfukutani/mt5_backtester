"""V036：期限（R4）を決めるための判断材料を一覧化する（Codex優先度3位）。

【Codexの指示（V033・Q4の3位）】
> 期限変更の判断材料を作り、探索を終了する。同じ方策を継続した場合と、長期用に別途固定した
> 方策を区別して、期限別の到達・破綻・期限切れを比較します。
> **元の2ヶ月上限を維持するなら、現状は未達として終了。期限延長を認めるなら、
> 別要件として評価を続ける。**

【⚠️ 初版の3つの誤りをCodexの査読（V037）で修正済み】

1. **初版はC族の格子に (1,2,3,4) を使っていた。** これはV035で「OOS上のピークがc=3〜4」と
   **見た後に**選んだ格子であり、先読み（researcher degrees of freedom）にあたる。
   V024で犯したのと同じ誤りなので、**他の族と同じ CONST_GRID に揃えた。**
2. **初版は定数と動的をISでそれぞれ選んだ後、OOSで良かった方を「最良」欄に採用していた。**
   これは上位の選択段階での先読みである。**選択もISで行う**よう修正した。
3. **初版はV024のIS前半選択を実装しておらず、24ヶ月の両手続き比較になっていなかった。**
   手続きを2つ（IS全体選択・IS前半選択）並べて出すよう修正した。

【出力する列の読み方（Codex指摘）】
- 「楽観上限」は **P(到達)+P(期限切れ)** であり、**実測した継続成績ではない。**
  最終到達確率 = P(期限内到達) + P(期限切れ) × P(その後到達∣期限切れ) の
  最後の項を**1に置いた**値である。**「そのまま続ければこの確率で到達する」とは読めない。**
- 表示の 0.0% は丸めであり、真の破綻確率ゼロを意味しない。

【評価条件】V029のエントリー時サイジング / H=IS頻度で固定（V030案a） / 破綻ライン10%
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

MONTHS = cc.MONTHS
N_PATHS = 10000
SEEDS = (101, 202, 303)
TARGET = 0.85
DEADLINES = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 9.0, 12.0, 18.0, 24.0, 36.0)

CONST_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]


def candidates(s_is):
    """全族で同じ格子（CONST_GRID）を使う。OOSを見ずに決められる選び方に統一する。"""
    out = [("const", (k,), dk.policy_constant(k)) for k in CONST_GRID]
    for k0 in CONST_GRID:
        for a in (0.5, 1.0, 2.0):
            out.append(("A", (k0, a), dk.policy_A(k0, a)))
    for k0 in CONST_GRID:
        out.append(("B", (k0,), dk.policy_B(k0)))
    for c in CONST_GRID:
        out.append(("C", (c,), dk.policy_C(c, s_is)))
    return out


def split_is(pr, lg, frac=0.5):
    """IS窓を取引順で前半・後半に分ける（V024のIS前半選択を再現するため）。"""
    n = len(pr)
    m = int(n * frac)
    return (pr[:m], lg[:m]), (pr[m:], lg[m:])


def select_on(pr, lg, H, cands, seeds, seed_base):
    """与えられた取引列で全候補を評価し、族ごとの最良と全体最良を返す（p_hit最大）。"""
    scores = {}
    for fam, prm, fn in cands:
        vals = []
        for sd in seeds:
            p, l = dkl.generate_paths_lag(pr, lg, H, N_PATHS, seed=seed_base + sd)
            vals.append(dkl.run_policy_lag(p, l, fn, entry_sizing=True)["p_hit"])
        scores[(fam, prm)] = float(np.mean(vals))
    best_const = max((x for x in scores if x[0] == "const"), key=scores.get)
    best_dyn = max((x for x in scores if x[0] != "const"), key=scores.get)
    best_all = max(scores, key=scores.get)
    return scores, best_const, best_dyn, best_all


def eval_oos(fn, pr_o, lg_o, H, seeds, seed_base):
    hs, rs, es = [], [], []
    for sd in seeds:
        p, l = dkl.generate_paths_lag(pr_o, lg_o, H, N_PATHS, seed=seed_base + sd)
        r = dkl.run_policy_lag(p, l, fn, entry_sizing=True)
        hs.append(r["p_hit"]); rs.append(r["p_ruin"]); es.append(r["p_exp"])
    return float(np.mean(hs)), float(np.mean(rs)), float(np.mean(es))


def main():
    books = dkl.build_books()
    pr_is, lg_is, _ = books["IS"]
    pr_o, lg_o, _ = books["OOS"]
    s_is = float(pr_is.std(ddof=1)) / cc.CAPITAL
    rate_is = len(pr_is) / MONTHS["IS"]
    cands = candidates(s_is)
    fnmap = {(f, p): fn for f, p, fn in cands}
    (pr_a, lg_a), _ = split_is(pr_is, lg_is)

    print("=" * 120)
    print("V036：期限（R4）を決めるための判断材料（Codex優先度3位・V037の査読を反映）")
    print("=" * 120)
    print("条件: エントリー時サイジング(V029) / H=IS頻度で固定(V030案a) / 破綻ライン10%")
    print(f"      候補{len(cands)}件を全族同一格子で総当たり→シード{len(SEEDS)}本平均で選択→OOSへ適用")
    print("      ※ 選択はすべてIS側で行う。OOSを見て選び直していない\n")

    print("【手続き1：IS窓**全体**で選択】")
    print(f"{'期限':>6}{'H':>6}│{'IS選択(定数)':>12}{'OOS到達':>9}{'OOS破綻':>9}{'期限切れ':>9}"
          f"│{'IS選択(動的)':>16}{'OOS到達':>9}{'OOS破綻':>9}{'期限切れ':>9}"
          f"│{'IS最良族':>10}")
    rows = []
    for lim in DEADLINES:
        H = int(round(rate_is * lim))
        sc, bc, bd, ba = select_on(pr_is, lg_is, H, cands, SEEDS,
                                   810000 + int(lim * 100))
        ch, cr, ce = eval_oos(fnmap[bc], pr_o, lg_o, H, SEEDS, 820000 + int(lim * 100))
        dh, dr, de = eval_oos(fnmap[bd], pr_o, lg_o, H, SEEDS, 820000 + int(lim * 100))
        rows.append((lim, H, bc, ch, cr, ce, bd, dh, dr, de, ba))
        print(f"{lim:>5.0f}月{H:>6}│{f'k={bc[1][0]}':>12}{100*ch:>8.1f}%{100*cr:>8.1f}%"
              f"{100*ce:>8.1f}%│{f'{bd[0]}{bd[1]}':>16}{100*dh:>8.1f}%{100*dr:>8.1f}%"
              f"{100*de:>8.1f}%│{f'{ba[0]}{ba[1]}':>10}")

    print("\n【手続き2：IS窓**前半のみ**で選択（V024の手続き）】")
    print(f"{'期限':>6}{'H':>6}│{'IS前半選択(定数)':>16}{'OOS到達':>9}"
          f"│{'IS前半選択(動的)':>18}{'OOS到達':>9}")
    rows2 = []
    for lim in DEADLINES:
        H = int(round(rate_is * lim))
        H_a = max(5, int(round(len(pr_a) / (MONTHS["IS"] / 2) * lim)))
        sc, bc, bd, ba = select_on(pr_a, lg_a, H_a, cands, SEEDS,
                                   830000 + int(lim * 100))
        ch, _, _ = eval_oos(fnmap[bc], pr_o, lg_o, H, SEEDS, 820000 + int(lim * 100))
        dh, _, _ = eval_oos(fnmap[bd], pr_o, lg_o, H, SEEDS, 820000 + int(lim * 100))
        rows2.append((lim, bc, ch, bd, dh))
        print(f"{lim:>5.0f}月{H:>6}│{f'k={bc[1][0]}':>16}{100*ch:>8.1f}%"
              f"│{f'{bd[0]}{bd[1]}':>18}{100*dh:>8.1f}%")

    print("\n" + "=" * 120)
    print("【判断材料：期限ごとに何が得られるか（選択もISで行った結果のみ）】")
    print("=" * 120)
    print("※「楽観上限」は P(到達)+P(期限切れ)。**実測した継続成績ではなく、期限切れを")
    print("   全員救済できると仮定した上限**。そのまま続ければこの確率で到達する、とは読めない。")
    print(f"\n{'期限':>6}{'IS最良方策':>12}{'OOS到達':>9}{'資金9割喪失':>12}"
          f"{'期限切れ':>9}{'R3(85%)':>9}{'楽観上限':>10}│{'IS前半選択の場合':>18}")
    for (lim, H, bc, ch, cr, ce, bd, dh, dr, de, ba), (l2, bc2, ch2, bd2, dh2) in zip(rows, rows2):
        # 選択もISで行う：IS最良族が定数なら定数、そうでなければ動的
        if ba[0] == "const":
            p, ruin, exp_, label = ch, cr, ce, f"定数k={bc[1][0]}"
            alt = ch2
        else:
            p, ruin, exp_, label = dh, dr, de, f"{bd[0]}{bd[1]}"
            alt = dh2
        print(f"{lim:>5.0f}月{label:>12}{100*p:>8.1f}%{100*ruin:>11.1f}%"
              f"{100*exp_:>8.1f}%{'✅達成' if p >= TARGET else '❌未達':>9}"
              f"{100*(p+exp_):>9.1f}%│{100*alt:>17.1f}%")

    print("\n" + "=" * 120)
    print("【Codexが示した最終結論の文面（V037）】")
    print("=" * 120)
    print("  検証済み方策と追加の有限候補探索では、元の2ヶ月要件に対する85%達成を")
    print("  立証できなかったため、探索を終了する。履歴不確実性を含む検証と方策集合全体の")
    print("  上界証明は未完了であり、到達不可能とは結論しない。")
    print("\n完了。")


if __name__ == "__main__":
    main()
