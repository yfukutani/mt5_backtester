"""V070：**暦の連続した期間・全起点評価**（Codexが基準に推奨した設計）。

【Codexの指示（V069への回答）】
> 最初は「**連続した実際の3ヶ月」の全起点評価を基準にする**ことを勧めます。
> これは欠陥ではなく、**限られた履歴をそのまま評価する方法**です。
>
> 1. 起点は観測期間内の**暦日**から選ぶ
> 2. 初期残高10万円・**建玉なし**を初期条件とする
> 3. 起点以後の入口イベントと、その建玉の決済イベントを**時刻順に**処理する
> 4. 期限は起点に**暦の月数**を加えた日時とする
> 5. 期限をまたぐ建玉の決済益を前倒し計上しない
>
> **起点前に入った建玉の決済だけを取り込まないことが重要です。**

【V069のバグ（Codexが発見）を構造的に回避する】
V069は `lot_hist[step − lag]` として**別取引の丸め結果を流用**していた。
本スクリプトはイベント順に処理し、**入口時点で、その建玉自身の基準ロットを、
その時点の資金で丸める**ため、このバグは起こらない。

【起点の間隔について】
Codex：「55ヶ月には**重ならない3ヶ月区間は約18個しかない**。
起点を日次に増やしても独立な情報量は増えない」

したがって**週次起点**（7日刻み）で十分であり、計算量も現実的になる。

【この評価の性質（Codexの但し書き）】
- 測っているのは「**含み損益・証拠金制約を無視した、確定損益残高の期限内到達確率**」で
  あり、**実現可能な到達確率の上限でも下限でもない**
- 起点が重なるため独立な情報量は起点数ほど多くない
- 期限をまたぐ建玉があると、期限時点の資産価値は未評価
- 履歴の取引機会を再生する近似であり、建玉なしでEAを再稼働した場合の
  シグナル列を厳密に再現するものではない
"""
from __future__ import annotations

import bisect
import csv
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl

CAPITAL = 100000.0
MIN_LOT = 0.01
STEP = 0.01
RUIN = 0.10
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
FLAT_TOL = 0.01
ORIGIN_STEP_DAYS = 7        # 週次起点
CASES = [("2倍・3ヶ月", 2.0, 3), ("2倍・6ヶ月", 2.0, 6),
         ("2倍・12ヶ月", 2.0, 12), ("2倍・18ヶ月", 2.0, 18),
         ("1.2倍・3ヶ月", 1.2, 3), ("1.3倍・3ヶ月", 1.3, 3),
         ("1.5倍・3ヶ月", 1.5, 3)]
WINDOW_RANGE = {
    "IS": (datetime(2021, 6, 21, tzinfo=timezone.utc),
           datetime(2026, 6, 20, tzinfo=timezone.utc)),
    "OOS": (datetime(2016, 11, 9, tzinfo=timezone.utc),
            datetime(2021, 6, 20, tzinfo=timezone.utc)),
}


def load_events(window):
    """入口時刻順に並べた (t_in, t_out, profit, volume) を返す。"""
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["magic"]) == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"])))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol in rows:
            if entry == 0:
                opened[pid] = (t, vol)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((o[0], t, profit, o[1]))
    rec.sort()
    t_in = [x[0] for x in rec]
    return rec, t_in


def simulate(rec, t_in_sorted, t0, t1, k, mult):
    """起点t0から期限t1まで、建玉なしで開始してイベント順に処理する。

    戻り値: 1=到達 / 2=破綻 / 0=期限切れ
    """
    i0 = bisect.bisect_left(t_in_sorted, t0)
    i1 = bisect.bisect_left(t_in_sorted, t1)
    if i1 <= i0:
        return 0
    eq = CAPITAL
    pend = []          # (t_out, 倍率, profit) を時刻順に保つ
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
            if t > t1:
                continue           # 期限をまたぐ決済は計上しない
            eq += profit * m
            if eq >= CAPITAL * mult:
                return 1
            if eq <= CAPITAL * RUIN:
                return 2
        else:
            ti, to, profit, vol = rec[ei]
            ei += 1
            x = eq / CAPITAL
            actual = max(MIN_LOT, math.floor(vol * k * x / STEP + 1e-9) * STEP)
            pend.append((to, actual / vol, profit))
    return 0


def evaluate(rec, t_in_sorted, w, k, mult, months):
    a, b = WINDOW_RANGE[w]
    res = []
    d = a
    span = timedelta(days=months * 30.4375)
    while d + span <= b:
        res.append(simulate(rec, t_in_sorted, int(d.timestamp()),
                            int((d + span).timestamp()), k, mult))
        d += timedelta(days=ORIGIN_STEP_DAYS)
    r = np.array(res) if res else np.array([0])
    return (float((r == 1).mean()), float((r == 2).mean()),
            float((r == 0).mean()), len(r))


def main():
    print("=" * 112)
    print("V070：暦の連続した期間・全起点評価（Codexが基準に推奨した設計）")
    print("=" * 112)
    print(f"資金{CAPITAL:,.0f}円 / 破綻ライン{100*RUIN:.0f}% / 最小ロット制約あり")
    print(f"起点は{ORIGIN_STEP_DAYS}日刻み。建玉なしで開始し、起点以後に入った建玉だけを扱う。")
    print("期限をまたぐ決済は計上しない。**ブートストラップを使わない実履歴の評価。**\n")
    print("⚠️ Codex：55ヶ月には**重ならない3ヶ月区間は約18個しかない**。")
    print("   起点を増やしても独立な情報量は増えない。\n")

    data = {}
    for w in ("IS", "OOS"):
        rec, ti = load_events(w)
        data[w] = (rec, ti)
        a, b = WINDOW_RANGE[w]
        print(f"  {w}窓: {len(rec)}建玉 / {a:%Y-%m-%d} 〜 {b:%Y-%m-%d}")
    print()

    print(f"{'条件':>16}{'IS選択k':>9}{'平坦域':>16}"
          f"│{'IS起点':>8}{'IS到達':>9}{'IS破綻':>9}"
          f"│{'OOS起点':>9}{'OOS到達':>9}{'OOS破綻':>9}{'OOS期限切れ':>12}{'70%':>6}")
    for label, mult, months in CASES:
        hits = {}
        for k in K_GRID:
            h, _, _, _ = evaluate(*data["IS"], "IS", k, mult, months)
            hits[k] = h
        best = max(hits.values())
        flat = [k for k in K_GRID if hits[k] >= best - FLAT_TOL]
        k_sel = flat[len(flat) // 2]
        ih, ir, ie, ino = evaluate(*data["IS"], "IS", k_sel, mult, months)
        oh, orr, oe, ono = evaluate(*data["OOS"], "OOS", k_sel, mult, months)
        print(f"{label:>16}{k_sel:>9}{str(flat):>16}"
              f"│{ino:>8}{100*ih:>8.1f}%{100*ir:>8.1f}%"
              f"│{ono:>9}{100*oh:>8.1f}%{100*orr:>8.1f}%{100*oe:>11.1f}%"
              f"{'✅' if oh >= 0.70 else '❌':>6}")

    print("\n" + "=" * 112)
    print("【この評価の性質（Codexの但し書き）】")
    print("=" * 112)
    print("  ・測っているのは『含み損益・証拠金制約を無視した、確定損益残高の")
    print("    期限内到達確率』であり、**実現可能な到達確率の上限でも下限でもない**")
    print("  ・起点が重なるため独立な情報量は起点数ほど多くない（OOSで実質約18区間）")
    print("  ・期限をまたぐ建玉があると、期限時点の資産価値は未評価")
    print("  ・履歴の取引機会を再生する近似であり、建玉なしでEAを再稼働した場合の")
    print("    シグナル列を厳密に再現するものではない")
    print("\n完了。")


if __name__ == "__main__":
    main()
