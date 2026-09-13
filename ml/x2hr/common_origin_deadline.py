"""V072：**共通起点・固定k**で期限延長の効果を測る（Codexの最優先提案）。

【V070の比較が無効だった理由（Codexが発見）】
V070は期限ごとに `while d + span <= b:` で起点を絞っていた。
**18ヶ月評価では窓の末尾18ヶ月に入る起点が使えない。**
OOS窓（2016-11〜2021-06）で18ヶ月の起点は**2019年12月まで**しか取れず、
**到達率79〜82%だった2020-2021年の起点が丸ごと落ちる。**
さらに期限ごとにkを選び直していた。

> **37.3%→36.8%は、期限延長の効果と、起点構成・k変更の効果を混ぜた比較です。**（Codex）

そして理論上：

> V070は決済ごとに目標を確認し、到達するとその場で成功を返します。この定義なら、
> **同じ起点・同じk・同じ運用経路では、3ヶ月以内の成功が18ヶ月で失敗へ変わることは
> ありません。** 1{3ヶ月以内に到達} ≤ 1{18ヶ月以内に到達}

**したがって正しく測れば、期限延長で到達率が下がることはあり得ない。**

【本スクリプトの設計（Codexの指定どおり）】
> 18ヶ月を最後まで観測できる起点だけを使い、**同じkについて**3・6・12・18ヶ月の
> 累積到達割合を並べてください。可能なら、**各起点の最初の到達日を1本の18ヶ月経路から
> 取得**します。
>
> 見るべきなのは「**3ヶ月で未到達だった起点のうち、6・12・18ヶ月まで待つことで
> 何件が追加成功したか**」です。

- 起点は「起点＋18暦月 ≤ 窓の終わり」を満たすものだけ（全期限で共通）
- **kは固定**（ISで選んだ1つを全期限に使う）
- 各起点について**1本の18ヶ月経路**を走らせ、**初回到達日**を記録する
- そこから3/6/12/18ヶ月の累積到達割合を出す（**構成上、単調非減少になる**）
- **暦月は正しく加算する**（V070の `days = months*30.4375` は平均月長の近似だった）

【限界】
- 起点が重なるため独立ではない（Codex：「非重複でも相場局面を共有し、独立とは限らない」）
- 測っているのは「含み損益・証拠金制約を無視した、確定損益残高の期限内到達割合」
- 追加建て・部分決済・反転があると `opened[pid]` の一対一対応が崩れる可能性
- 同一時刻のイベント順序は実際の約定順を保持していない
- `profit` 列のみを読んでおり、手数料・スワップが別列なら純損益と一致しない
"""
from __future__ import annotations

import bisect
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co

CAPITAL = co.CAPITAL
MIN_LOT = co.MIN_LOT
STEP = co.STEP
RUIN = co.RUIN
K_GRID = co.K_GRID
FLAT_TOL = co.FLAT_TOL
MAX_MONTHS = 18
CHECK_MONTHS = [1, 2, 3, 4, 6, 9, 12, 18]
ORIGIN_STEP_DAYS = 7
MULTS = [2.0, 1.5, 1.3, 1.2]


def add_months(d, m):
    """暦月を正しく加算する（V070の平均月長近似を修正）。"""
    y = d.year + (d.month - 1 + m) // 12
    mo = (d.month - 1 + m) % 12 + 1
    # 月末日の調整
    day = d.day
    while True:
        try:
            return d.replace(year=y, month=mo, day=day)
        except ValueError:
            day -= 1


def first_reach(rec, t_in_sorted, t0, t_end, k, mult):
    """1本の経路を t0 から t_end まで走らせ、初回到達時刻を返す。

    戻り値: (到達時刻 or None, 破綻時刻 or None)
    """
    i0 = bisect.bisect_left(t_in_sorted, t0)
    i1 = bisect.bisect_left(t_in_sorted, t_end)
    eq = CAPITAL
    pend = []
    pi = 0
    ei = i0
    while ei < i1 or pi < len(pend):
        t_ev = rec[ei][0] if ei < i1 else None
        if pi < len(pend):
            pend[pi:] = sorted(pend[pi:])
            t_pd = pend[pi][0]
        else:
            t_pd = None
        if t_pd is not None and (t_ev is None or t_pd <= t_ev):
            t, m, profit = pend[pi]
            pi += 1
            if t > t_end:
                continue
            eq += profit * m
            if eq >= CAPITAL * mult:
                return t, None
            if eq <= CAPITAL * RUIN:
                return None, t
        else:
            ti, to, profit, vol = rec[ei]
            ei += 1
            x = eq / CAPITAL
            actual = max(MIN_LOT, math.floor(vol * k * x / STEP + 1e-9) * STEP)
            pend.append((to, actual / vol, profit))
    return None, None


def run_window(rec, ti, w, k, mult):
    """共通起点で18ヶ月経路を走らせ、各起点の初回到達時刻を集める。"""
    a, b = co.WINDOW_RANGE[w]
    out = []
    d = a
    while add_months(d, MAX_MONTHS) <= b:
        t_end = add_months(d, MAX_MONTHS)
        hit, ruin = first_reach(rec, ti, int(d.timestamp()),
                                int(t_end.timestamp()), k, mult)
        out.append((d, hit, ruin))
        d += timedelta(days=ORIGIN_STEP_DAYS)
    return out


def cumulative(res, months):
    """months ヶ月以内に到達した割合（同一経路の初回到達日から計算）。"""
    ok = 0
    ru = 0
    for d, hit, ruin in res:
        lim = int(add_months(d, months).timestamp())
        if ruin is not None and ruin <= lim and (hit is None or ruin < hit):
            ru += 1
        elif hit is not None and hit <= lim:
            ok += 1
    n = len(res)
    return ok / n, ru / n, n


def wilson(p, n):
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def main():
    print("=" * 112)
    print("V072：共通起点・固定kで期限延長の効果を測る（Codexの最優先提案）")
    print("=" * 112)
    print(f"起点は「起点＋{MAX_MONTHS}暦月 ≤ 窓の終わり」を満たすものだけ（全期限で共通）")
    print("kは固定。各起点について1本の18ヶ月経路を走らせ、**初回到達日**を記録する。")
    print("→ 構成上、累積到達割合は**単調非減少**になる。下がったら実装の誤り。\n")
    print("⚠️ V070の比較は期限ごとに起点集合とkが違っており、**無効だった。**")
    print("   OOS窓で18ヶ月の起点は2019年12月までしか取れず、")
    print("   **到達率79〜82%だった2020-2021年の起点が丸ごと落ちていた。**\n")

    data = {w: co.load_events(w) for w in ("IS", "OOS")}

    for mult in MULTS:
        print("=" * 112)
        print(f"【目標 {mult:g}倍】")
        print("=" * 112)
        # --- kをIS窓で選ぶ（3ヶ月基準・共通起点で） ---
        hits = {}
        for k in K_GRID:
            res = run_window(*data["IS"], "IS", k, mult)
            h, _, _ = cumulative(res, 3)
            hits[k] = h
        best = max(hits.values())
        flat = [k for k in K_GRID if hits[k] >= best - FLAT_TOL]
        k_sel = flat[len(flat) // 2]
        print(f"  IS窓・3ヶ月で選んだk: {k_sel}（平坦域 {flat}）"
              f"——**全期限でこのkを固定して使う**\n")

        for w in ("IS", "OOS"):
            res = run_window(*data[w], w, k_sel, mult)
            print(f"  --- {w}窓（共通起点 {len(res)}個）---")
            print(f"{'期限':>7}{'到達':>9}{'破綻':>9}{'未決着':>9}"
                  f"{'3ヶ月からの追加':>16}{'Wilson 95%区間':>22}")
            base = None
            for m in CHECK_MONTHS:
                h, r, n = cumulative(res, m)
                if m == 3:
                    base = h
                add = f"{100*(h-base):+.1f}pt" if base is not None and m > 3 else "—"
                lo, hi = wilson(h, n)
                print(f"{m:>6}月{100*h:>8.1f}%{100*r:>8.1f}%{100*(1-h-r):>8.1f}%"
                      f"{add:>16}{f'[{100*lo:.1f}, {100*hi:.1f}]%':>22}")
            # 3ヶ月で未到達だったものが後で何件成功したか
            h3, _, n = cumulative(res, 3)
            h18, _, _ = cumulative(res, 18)
            miss3 = int(round(n * (1 - h3)))
            gain = int(round(n * (h18 - h3)))
            print(f"    → 3ヶ月で未到達だった{miss3}起点のうち、"
                  f"**18ヶ月まで待つと{gain}件が追加で到達**"
                  f"（{100*gain/max(miss3,1):.1f}%）")
            print()

    print("=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・起点が重なるため独立ではない（非重複でも相場局面を共有する）")
    print("  ・測っているのは『含み損益・証拠金制約を無視した、確定損益残高の到達割合』")
    print("  ・Wilson区間は『18回の独立二項試行』を仮定した参考値であり、")
    print("    **V070/V072に付けられる正式な信頼区間ではない**（Codex）")
    print("  ・追加建て・部分決済・反転があると建玉の一対一対応が崩れる可能性")
    print("  ・同一時刻のイベント順序は実際の約定順を保持していない")
    print("  ・profit列のみを読んでおり、手数料・スワップが別列なら純損益と一致しない")
    print("\n完了。")


if __name__ == "__main__":
    main()
