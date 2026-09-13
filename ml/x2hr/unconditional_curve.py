"""V054：到達時期を**無条件の累積確率**で出し直す（Codex指摘の訂正）。

【何を間違えたか】
V044・V045・V047・V048で報告した「中央値」「90%点」は、
`stop[state == 1]` ——**到達したパスだけ**から計算した分位点だった。

> 「90%のパスが25.2ヶ月以内」ではなく、**「成功パスの90%点が25.2ヶ月相当」**です。
> 全開始パスに対する到達率なら、約 96.5% × 90% = 86.85% に相当します。
> 中央値10ヶ月も成功条件付きです。（Codex・V053査読）

**「90%のパスが25.2ヶ月以内に2倍になる」と読める書き方をしていたが、誤りである。**

【本スクリプトが出すもの】
条件付き分位点をやめ、**無条件の累積確率**で出す。

    P(T ヶ月以内に2倍へ到達)   ← 全開始パスに対する割合
    P(T ヶ月以内に破綻)
    P(T ヶ月時点で未決着)

これなら「何ヶ月で何%」が誤解なく読める。評価はV048と同じ条件
（最小ロット制約あり・年ブロック再標本化あり）で行う。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import realistic_sim as rs

N_PATHS = 20000
SEEDS = (101, 202, 303)
K_GRID = [0.5, 1.0, 1.5, 2.0]
CHECKPOINTS = [3, 6, 12, 18, 24, 36, 60, 120]
MONTHS = cc.MONTHS
LONG_MONTHS = 240.0


def main():
    print("=" * 112)
    print("V054：到達時期を**無条件の累積確率**で出し直す（Codex指摘の訂正）")
    print("=" * 112)
    print("これまで報告していた『中央値』『90%点』は**到達したパスだけ**の分位点だった。")
    print("『90%のパスが25.2ヶ月以内』は誤り。正しくは『成功パスの90%点が25.2ヶ月相当』。")
    print("本表は**全開始パスに対する無条件の累積確率**である。\n")
    print("条件：最小ロット制約あり（V047）＋年ブロック再標本化あり（V045）＝V048の★両方\n")

    for window in ("IS", "OOS"):
        tt, pr, vo = rs.build(window)
        rate = len(pr) / MONTHS[window]
        H = int(round(rate * LONG_MONTHS))
        yb = rs.year_blocks(tt, pr, vo)
        print("=" * 112)
        print(f"【{window}窓】{len(pr)}取引 / 月{rate:.1f}件 / 年ブロック{len(yb)}個")
        print("=" * 112)
        hdr = f"{'k':>5}{'区分':>12}"
        for c in CHECKPOINTS:
            hdr += f"{f'{c}ヶ月':>9}"
        print(hdr)
        for k in K_GRID:
            acc_hit = np.zeros(len(CHECKPOINTS))
            acc_ruin = np.zeros(len(CHECKPOINTS))
            for sd in SEEDS:
                pp, vv = rs.gen_year(yb, H, N_PATHS, seed=150000 + sd)
                st, stp = rs.run(pp, vv, k, True)
                steps_cp = [int(round(rate * c)) for c in CHECKPOINTS]
                for i, sc in enumerate(steps_cp):
                    acc_hit[i] += float(((st == 1) & (stp <= sc)).mean())
                    acc_ruin[i] += float(((st == 2) & (stp <= sc)).mean())
            acc_hit /= len(SEEDS)
            acc_ruin /= len(SEEDS)
            line = f"{k:>5}{'到達':>12}"
            for v in acc_hit:
                line += f"{100*v:>8.1f}%"
            print(line)
            line = f"{'':>5}{'破綻':>12}"
            for v in acc_ruin:
                line += f"{100*v:>8.1f}%"
            print(line)
            line = f"{'':>5}{'未決着':>12}"
            for h, r in zip(acc_hit, acc_ruin):
                line += f"{100*(1-h-r):>8.1f}%"
            print(line)
            print()

    print("=" * 112)
    print("【読み方】")
    print("=" * 112)
    print("  ・『到達』行が、その月数までに2倍へ届いた**全パス中の割合**")
    print("  ・3行の合計は常に100%")
    print("  ・『未決着』が大きい列は、まだ決着していないパスが多いということ")
    print("\n完了。")


if __name__ == "__main__":
    main()
