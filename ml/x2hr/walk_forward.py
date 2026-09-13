"""V039：期間依存性の診断——ウォークフォワード検証（Codex設計・V038）。

【なぜこれをやるのか】
V036で「C族の格子を他族と同じ広さにしたら、IS選択が一貫してC(c=2.0)を選び、
OOSで18ヶ月88.3%・24ヶ月93.3%」という、これまでで最良の結果が出た。
Codexに信用してよいか問うたところ、判定は次のとおりだった。

> **「有望な探索結果。ただし、独立検証としての合格ではない」**
>
> 問題は動機の「純潔」ではなく、情報の流れです。
> 「OOSでC族が強いと知る → C族の探索範囲を修正する → 同じOOSで改善を確認する」
> この流れには**OOSから設計へのフィードバック**があります。最終コードでパラメータを
> ISだけから選んでも、**候補集合を決めた上位の判断にはOOSが使われています。**
>
> また、**「同じ数値格子＝公平」も成立しません。** 定数k、A/Bのk0、Cのcは、
> 同じ数値でも実際のエクスポージャーが違います。

Codexが提示した代替は「既知履歴での**期間依存性の診断**」である。
**これは独立検証ではない**（既に見た履歴を使うため）が、
「この選択手続きが、時期を変えても同じように機能するか」は測れる。

【Codexが指定した設計（そのまま実装する）】
> - 直前36ヶ月で推定・候補選択。
> - 続く24ヶ月で評価。
> - 開始点を24ヶ月ずつ進め、**重ならない評価区間を3つ**作る。
> - 各境界で、将来に決済される取引の利益を学習に入れない。
> - `s_IS`、頻度、候補選択は**各学習区間だけ**で計算する。
> - **36ヶ月は提案上の固定値であり、結果を見て調整しない。**

【検証対象（Codexの指示により事前に固定する）】
> 次のどちらを検証するのか決めます。
> - C(2.0)という固定方策。
> - **ISから60候補の最良を選ぶ選択手続き。**   ← こちらを検証する
> 今回の研究の主張を検証するなら、後者が自然です。

したがって本スクリプトは**「60候補から学習区間だけで最良を選ぶ手続き」**を検証する。
各foldで選ばれる方策が違っても構わない——それが手続きの実力である。

【⚠️ この測定で言えないこと】
- 独立検証ではない（FULL窓はIS窓・OOS窓を含み、既に何度も見ている）
- 評価区間は3つしかなく、85%の精密な立証には弱い（Codex）
- 「24ヶ月相当」は取引数ベースであり、実際の暦24ヶ月ではない
"""
from __future__ import annotations

import bisect
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

N_PATHS = 10000
SEEDS = (101, 202, 303)
TARGET = 0.85
TRAIN_MONTHS = 36.0        # Codex提案の固定値。結果を見て調整しない
TEST_MONTHS = 24.0
STEP_MONTHS = 24.0
CONST_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
FULL_START = datetime(2016, 11, 9, tzinfo=timezone.utc)


def candidates(s_train):
    """全族同一格子（60候補）。族ごとの格子幅の違いを避けるための設計上の選択であり、
    Codexが指摘するとおり『唯一の公平な設計』ではない。"""
    out = [("const", (k,), dk.policy_constant(k)) for k in CONST_GRID]
    for k0 in CONST_GRID:
        for a in (0.5, 1.0, 2.0):
            out.append(("A", (k0, a), dk.policy_A(k0, a)))
    for k0 in CONST_GRID:
        out.append(("B", (k0,), dk.policy_B(k0)))
    for c in CONST_GRID:
        out.append(("C", (c,), dk.policy_C(c, s_train)))
    return out


def build_full():
    """FULL窓の (t_out, profit, lag) を復元する（dynamic_k_lag と同じ規則）。"""
    fx, gold = dkl.resolve_runs()
    pos, unm = dkl.positions_from(fx["FULL"])
    pg, unm2 = dkl.positions_from(gold["FULL"])
    pos = sorted(pos + pg)
    t_out = [p[0] for p in pos]
    profits = np.array([p[1] for p in pos], dtype=float)
    times = np.array(t_out, dtype=np.int64)
    lags = np.empty(len(pos), dtype=np.int32)
    for i, (to, _, ti) in enumerate(pos):
        lags[i] = max(0, i - bisect.bisect_left(t_out, ti))
    return times, profits, lags, unm + unm2


def slice_months(times, profits, lags, m0, m1):
    """FULL開始からm0〜m1ヶ月の区間を、**決済時刻**で切り出す。

    決済時刻で切るため、境界をまたぐ建玉（学習区間中に建てて評価区間で決済）は
    自動的に評価区間側に入る。Codexの「将来に決済される取引の利益を学習に入れない」
    という要請を満たす。ただしlagは全体順序で計算しているため、区間内での相対位置とは
    ずれる（限界として明記）。
    """
    t0 = int(FULL_START.timestamp() + m0 * 30.4375 * 86400)
    t1 = int(FULL_START.timestamp() + m1 * 30.4375 * 86400)
    m = (times >= t0) & (times < t1)
    return profits[m], lags[m], int(m.sum())


def select(pr, lg, H, cands, seed_base):
    scores = {}
    for fam, prm, fn in cands:
        vals = []
        for sd in SEEDS:
            p, l = dkl.generate_paths_lag(pr, lg, H, N_PATHS, seed=seed_base + sd)
            vals.append(dkl.run_policy_lag(p, l, fn, entry_sizing=True)["p_hit"])
        scores[(fam, prm)] = float(np.mean(vals))
    best = max(scores, key=scores.get)
    return best, scores[best], scores


def evaluate(fn, pr, lg, H, seed_base):
    hs, rs, es = [], [], []
    for sd in SEEDS:
        p, l = dkl.generate_paths_lag(pr, lg, H, N_PATHS, seed=seed_base + sd)
        r = dkl.run_policy_lag(p, l, fn, entry_sizing=True)
        hs.append(r["p_hit"]); rs.append(r["p_ruin"]); es.append(r["p_exp"])
    return float(np.mean(hs)), float(np.mean(rs)), float(np.mean(es))


def main():
    deadlines = [float(a) for a in sys.argv[1:]] or [18.0, 24.0]
    times, profits, lags, unm = build_full()

    print("=" * 112)
    print("V039：ウォークフォワード検証（Codex設計・期間依存性の診断）")
    print("=" * 112)
    print(f"FULL窓 {len(profits)}取引 / 未突合 {unm}件 / 開始 {FULL_START:%Y-%m-%d}")
    print(f"学習{TRAIN_MONTHS:.0f}ヶ月 → 評価{TEST_MONTHS:.0f}ヶ月、開始点を"
          f"{STEP_MONTHS:.0f}ヶ月ずつ進めて評価区間が重ならない3foldを作る")
    print("⚠️ これは**独立検証ではない**。FULL窓はIS窓・OOS窓を含み、既に何度も見ている。")
    print("   測れるのは「この選択手続きが時期を変えても同じように機能するか」だけ。\n")

    folds = []
    for i in range(3):
        tr0 = i * STEP_MONTHS
        tr1 = tr0 + TRAIN_MONTHS
        te0 = tr1
        te1 = te0 + TEST_MONTHS
        folds.append((i + 1, tr0, tr1, te0, te1))

    for dl in deadlines:
        print("=" * 112)
        print(f"【期限 {dl:g}ヶ月相当】")
        print("=" * 112)
        print(f"{'fold':>5}{'学習期間':>14}{'評価期間':>14}"
              f"{'学習取引':>9}{'評価取引':>9}{'H':>6}"
              f"{'学習で選んだ方策':>18}{'学習P':>8}│{'評価P':>8}{'評価破綻':>9}{'期限切れ':>9}")
        hits = []
        for fi, tr0, tr1, te0, te1 in folds:
            pr_tr, lg_tr, n_tr = slice_months(times, profits, lags, tr0, tr1)
            pr_te, lg_te, n_te = slice_months(times, profits, lags, te0, te1)
            if n_tr < 100 or n_te < 50:
                print(f"{fi:>5}  取引数が足りないため飛ばす（学習{n_tr} 評価{n_te}）")
                continue
            # s と 頻度は **学習区間だけ** から計算する
            s_tr = float(pr_tr.std(ddof=1)) / cc.CAPITAL
            rate_tr = n_tr / TRAIN_MONTHS
            H = max(5, int(round(rate_tr * dl)))
            cands = candidates(s_tr)
            fnmap = {(f, p): fn for f, p, fn in cands}
            best, p_tr, _ = select(pr_tr, lg_tr, H, cands,
                                   910000 + int(dl * 100) + fi * 1000)
            ph, pr_, pe = evaluate(fnmap[best], pr_te, lg_te, H,
                                   920000 + int(dl * 100) + fi * 1000)
            hits.append(ph)
            lab = f"{best[0]}{best[1]}" if best[0] != "const" else f"定数k={best[1][0]}"
            print(f"{fi:>5}{f'{tr0:.0f}-{tr1:.0f}月':>14}{f'{te0:.0f}-{te1:.0f}月':>14}"
                  f"{n_tr:>9}{n_te:>9}{H:>6}{lab:>18}{100*p_tr:>7.1f}%│"
                  f"{100*ph:>7.1f}%{100*pr_:>8.1f}%{100*pe:>8.1f}%")
        if hits:
            a = np.array(hits)
            print(f"\n  → 3foldの評価到達率: {'  '.join(f'{100*x:.1f}%' for x in a)}")
            print(f"     平均 {100*a.mean():.1f}%  最小 {100*a.min():.1f}%  "
                  f"最大 {100*a.max():.1f}%")
            print(f"     85%を超えたfold: {int((a >= TARGET).sum())}/{len(a)}")
        print()

    print("=" * 112)
    print("【この結果の読み方（Codex）】")
    print("=" * 112)
    print("  ・既に見た履歴なので**独立検証ではなく期間依存性の診断**")
    print("  ・3区間しかないため、85%の精密な立証には弱い設計")
    print("  ・「〜ヶ月相当」は取引数ベースであり、実際の暦月ではない")
    print("  ・foldごとに選ばれる方策が違ってよい。検証対象は**選択手続き**であって")
    print("    個別の方策ではない")
    print("\n完了。")


if __name__ == "__main__":
    main()
