"""V035：方策族の**上界**を先読みで測る（Codex優先度2位）。

【Codexの指示（V033・Q4の2位）】
> A/B/Cのパラメータ追加探索を繰り返すのではなく、定義した方策集合で最適値または上界を
> 調べます。これは個別案を増殖させず、まとめて評価する手段です。
> **「A/B/Cが十分良いのか、それとも方策の形が制約になっているのか」を調べる最後の診断**。

【⚠️ 本スクリプトの値は「先読み」であり、実運用では達成できない】
OOS窓そのものを見て、方策族ごとに到達確率が最大になるパラメータを選ぶ。
**これは意図的な先読みである。** 目的は成績の主張ではなく、

> **「パラメータ選択を完璧に当てられたとしても、この方策族では何%までしか行けないのか」**

という**上界**を知ること。上界が85%未満なら、

> 指定した生成モデル・情報集合・許容注文量の範囲では、**どのパラメータを選んでも
> 85%に届かない**

と言える。これはCodexが設計した「閉じ方」の第二段階にあたる（ただし方策族はA/B/Cと
定数kに限られるため、**全方策の上界ではない**——この限界は必ず併記する）。

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
N_PATHS = 10000          # 上界の診断なので本測定(20,000)より軽くする
TARGET = 0.85


def build_grids(s_is):
    g = []
    for k in np.arange(0.1, 8.01, 0.1):
        g.append(("const", (round(float(k), 2),), dk.policy_constant(float(k))))
    for k0 in np.arange(0.25, 4.01, 0.25):
        for a in (0.5, 1.0, 2.0):
            g.append(("A", (round(float(k0), 2), a), dk.policy_A(float(k0), a)))
    for k0 in np.arange(0.25, 8.01, 0.25):
        g.append(("B", (round(float(k0), 2),), dk.policy_B(float(k0))))
    for c in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
        g.append(("C", (c,), dk.policy_C(c, s_is)))
    return g


def main():
    limits = [float(a) for a in sys.argv[1:]] or [2.0, 3.0, 4.0, 5.0, 6.0, 12.0]
    books = dkl.build_books()
    pr_is, lg_is, _ = books["IS"]
    pr_o, lg_o, _ = books["OOS"]
    s_is = float(pr_is.std(ddof=1)) / cc.CAPITAL
    rate_is = len(pr_is) / MONTHS["IS"]
    grids = build_grids(s_is)

    print("=" * 100)
    print("V035：方策族の上界を先読みで測る（Codex優先度2位）")
    print("=" * 100)
    print("⚠️ 本表の値はOOS窓自身を見てパラメータを選んだ**先読み**であり、実運用では")
    print("   達成できない。目的は『完璧に当てても何%までか』という上界を知ること。")
    print(f"   方策候補 {len(grids)}件（定数{sum(1 for x in grids if x[0]=='const')} / "
          f"A{sum(1 for x in grids if x[0]=='A')} / B{sum(1 for x in grids if x[0]=='B')} / "
          f"C{sum(1 for x in grids if x[0]=='C')}）  パス{N_PATHS:,}本\n")

    print(f"{'期限':>6}{'H':>6}{'族':>7}{'最良パラメータ':>18}"
          f"{'OOS到達(先読み)':>16}{'破綻':>8}{'期限切れ':>10}{'85%':>6}")
    summary = []
    for lim in limits:
        H = int(round(rate_is * lim))
        pp, pl = dkl.generate_paths_lag(pr_o, lg_o, H, N_PATHS,
                                        seed=710000 + int(lim * 100))
        best_by_fam = {}
        for fam, prm, fn in grids:
            r = dkl.run_policy_lag(pp, pl, fn, entry_sizing=True)
            cur = best_by_fam.get(fam)
            if cur is None or r["p_hit"] > cur[1]["p_hit"]:
                best_by_fam[fam] = (prm, r)
        overall = max(best_by_fam.items(), key=lambda kv: kv[1][1]["p_hit"])
        for fam in ("const", "A", "B", "C"):
            prm, r = best_by_fam[fam]
            star = " ★" if fam == overall[0] else ""
            print(f"{lim:>5.0f}月{H:>6}{fam:>7}{str(prm):>18}"
                  f"{100*r['p_hit']:>15.1f}%{100*r['p_ruin']:>7.1f}%"
                  f"{100*r['p_exp']:>9.1f}%"
                  f"{'✅' if r['p_hit'] >= TARGET else '❌':>6}{star}")
        summary.append((lim, H, overall[0], overall[1][0], overall[1][1]["p_hit"]))
        print()

    print("=" * 100)
    print("【まとめ：方策族A/B/C＋定数kの上界（先読み・達成不可能）】")
    print("=" * 100)
    print(f"{'期限':>6}{'最良族':>8}{'パラメータ':>16}{'上界':>9}"
          f"{'85%まで':>10}{'判定':>28}")
    for lim, H, fam, prm, p in summary:
        if p < TARGET:
            v = "✅ どのパラメータでも85%未達"
        else:
            v = "— 先読みなら85%到達（実運用不可）"
        print(f"{lim:>5.0f}月{fam:>8}{str(prm):>16}{100*p:>8.1f}%"
              f"{100*(TARGET-p):>+9.1f}pt{v:>28}")

    print("\n【限界】方策族はA/B/Cと定数kに限られる。**全方策の上界ではない。**")
    print("        『どの方策でも届かない』と言うには、許容行動を覆う計算が別途必要（Codex）。")
    print("\n完了。")


if __name__ == "__main__":
    main()
