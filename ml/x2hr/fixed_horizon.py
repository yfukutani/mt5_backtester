"""V030：期限H を「IS窓の頻度」で固定して再測定する（Codex指摘C13・案a）。

【Codexの指摘】
`dynamic_k.py` / `dynamic_k_lag.py` は `H = round(窓の取引数 ÷ 窓の月数 × 期限月数)` として
おり、**評価窓自身の頻度**をHに使っている。Hは次の2つの役割を同時に果たす。

- **評価期限**：パスをH取引で打ち切る
- **方策への情報**：そのHを既知として、残り取引数 `h = H − step` から倍率を決める

> 「運用開始時に実行できる方策のOOS検証」という主張に対しては、後者は**評価窓からの
> 情報漏洩**です。ISで選んだのは方策族・パラメータであって、実行時に必要なHまで
> ISで固定したわけではありません。（Codex）

Codexは3案（a: IS頻度で全窓固定 / b: 暦日ベースへ作り直し / c: 感応度分析のみ）のうち
**「まず案aを採用し、限定した感応度分析を添えるのが妥当。案cだけでは先読みを除去できない」**
と判定した。本スクリプトは案a＋感応度分析を実装する。

【Codexの事前の見立て（重要）】
> **「未来情報を使った」ことと「必ず楽観方向に歪んだ」ことは分ける必要があります。**
> 旧データでは IS頻度 34.22件/月 vs OOS頻度 33.49件/月 で**差は約2.2%**であり、
> 30%規模ではありません。歪みの方向は一定ではありません。

【測定】
1. 期限ごとに `H_fix = round(ISの取引数 ÷ ISの月数 × 期限月数)` を固定し、全窓に適用する
2. IS前半で方策を選び直さない——V029でIS窓から選んだ方策をそのまま使う
   （選択手続きを変えると多重比較になるため）
3. 感応度として H_fix × 0.7 / 1.0 / 1.3 も測る
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

# V029でIS窓から選ばれた方策（選び直さない）
SELECTED = {
    2.0: dict(const=("const", (3.0,)), dyn=("B", (3.0,))),
    6.0: dict(const=("const", (1.0,)), dyn=("A", (1.0, 1.0))),
}


def main():
    limits = [float(a) for a in sys.argv[1:]] or [2.0, 6.0]
    books = dkl.build_books()
    pr_is, lg_is, _ = books["IS"]
    s_is = float(pr_is.std(ddof=1)) / cc.CAPITAL
    fam_fn = {"const": lambda p: dk.policy_constant(p[0]),
              "A": lambda p: dk.policy_A(*p),
              "B": lambda p: dk.policy_B(p[0]),
              "C": lambda p: dk.policy_C(p[0], s_is)}

    print("=" * 100)
    print("V030：期限Hを「IS窓の頻度」で固定して再測定（Codex指摘C13・案a）")
    print("=" * 100)
    print("\n【窓ごとの取引頻度】")
    print(f"{'窓':>6}{'取引数':>8}{'月数':>7}{'月間頻度':>10}{'IS比':>8}")
    rate_is = len(pr_is) / MONTHS["IS"]
    for w in ("IS", "OOS", "FULL"):
        pr, _, _ = books[w]
        rate = len(pr) / MONTHS[w]
        print(f"{w:>6}{len(pr):>8}{MONTHS[w]:>7.0f}{rate:>10.2f}{rate/rate_is:>8.3f}")

    for lim in limits:
        sel = SELECTED.get(lim)
        if sel is None:
            print(f"\n期限{lim:g}ヶ月はV029で方策を選んでいないため飛ばす")
            continue
        cfn = fam_fn[sel["const"][0]](sel["const"][1])
        dfn = fam_fn[sel["dyn"][0]](sel["dyn"][1])
        H_fix = int(round(rate_is * lim))

        print("\n" + "=" * 100)
        print(f"【期限{lim:g}ヶ月】constant k={sel['const'][1][0]} / "
              f"動的={sel['dyn'][0]}{sel['dyn'][1]}   H_fix(IS頻度)={H_fix}")
        print("=" * 100)
        print(f"{'窓':>6}{'H':>16}{'方策':>10}{'P(2倍)':>9}{'P(破綻)':>9}"
              f"{'P(期限切れ)':>12}{'差(動的-const)':>16}{'95%CI':>22}")

        for w in ("IS", "OOS", "FULL"):
            pr, lg, _ = books[w]
            H_own = int(round(len(pr) / MONTHS[w] * lim))
            variants = [("窓自身(旧)", H_own), ("IS固定×0.7", int(round(H_fix * 0.7))),
                        ("IS固定×1.0", H_fix), ("IS固定×1.3", int(round(H_fix * 1.3)))]
            for name, H in variants:
                if H < 5:
                    continue
                pp, pl = dkl.generate_paths_lag(pr, lg, H, N_PATHS,
                                                seed=50000 + int(lim * 100) + hash(w) % 97)
                rc = dkl.run_policy_lag(pp, pl, cfn, entry_sizing=True)
                rd = dkl.run_policy_lag(pp, pl, dfn, entry_sizing=True)
                d, ci = dk.paired_diff(rd, rc, N_PATHS)
                tag = f"{name}({H})"
                print(f"{w:>6}{tag:>16}{'constant':>10}{100*rc['p_hit']:>8.1f}%"
                      f"{100*rc['p_ruin']:>8.1f}%{100*rc['p_exp']:>11.1f}%"
                      f"{'':>16}{'':>22}")
                print(f"{'':>6}{'':>16}{'動的'+sel['dyn'][0]:>10}{100*rd['p_hit']:>8.1f}%"
                      f"{100*rd['p_ruin']:>8.1f}%{100*rd['p_exp']:>11.1f}%"
                      f"{100*d:>+15.2f}pt"
                      f"{f'[{100*ci[0]:+.2f}, {100*ci[1]:+.2f}]':>22}")
            print()

    print("完了。")


if __name__ == "__main__":
    main()
