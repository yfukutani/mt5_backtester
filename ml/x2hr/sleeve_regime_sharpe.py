"""V090：**枠別×期間別のシャープ**（簡易検証・2026-09-13）。

【対象の案】100案の C32・C40・Codex31
- C32：枠別×期間別のシャープを実測し、**2016-2019（弱局面）に正だった枠だけを増量**
- C40：2016-2019に正だった枠だけのサブブックを作り、上限を把握する
- Codex31：GOLDの箱型レンジ内回転（**弱局面で何が効いていたか**を先に知りたい）

【なぜ必要か】
V078・V080より、方針Aに必要なのは **H を 0.480 → 0.50（取引数1.1倍相当）**。
**弱局面で正の寄与をしている枠が分かれば、そこを増やすのが最短。**
逆に弱局面で負の枠があれば、それが H を押し下げている。

【限界】
- 枠を選ぶ時点で選択バイアスが入る。**弱局面で選んで弱局面で評価すれば必ず良く見える**
- したがって**期間を分けて「他の期間でも正か」を見る**
- 枠ごとの取引数が少ないと t値は当てにならない。件数を必ず併記する
- 枠を削ると取引数が減り、`H = S×√N` の N が減る。**質の改善が √ の損失を上回る必要がある**
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl

PERIODS = [
    ("2016-11〜2018-12 弱前半", datetime(2016, 11, 9, tzinfo=timezone.utc),
     datetime(2019, 1, 1, tzinfo=timezone.utc)),
    ("2019-01〜2019-12 弱後半", datetime(2019, 1, 1, tzinfo=timezone.utc),
     datetime(2020, 1, 1, tzinfo=timezone.utc)),
    ("2020-01〜2021-06 金大相場", datetime(2020, 1, 1, tzinfo=timezone.utc),
     datetime(2021, 6, 21, tzinfo=timezone.utc)),
    ("2021-06〜2024-01 IS前半", datetime(2021, 6, 21, tzinfo=timezone.utc),
     datetime(2024, 1, 1, tzinfo=timezone.utc)),
    ("2024-01〜2026-06 IS後半", datetime(2024, 1, 1, tzinfo=timezone.utc),
     datetime(2026, 6, 21, tzinfo=timezone.utc)),
]
WEAK_IDX = [0, 1]
MIN_N = 25


def load(window):
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            if m == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"]), m))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol, m in rows:
            if entry == 0:
                opened[pid] = (t, vol, m)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((o[0], t, profit, o[1], o[2]))
    rec.sort()
    return rec


def stat(p):
    a = np.asarray(p, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0, 0.0, 0.0
    s = float(a.mean() / a.std(ddof=1))
    t = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
    return s, t, float(a.sum())


def horizon_H(profits, months_span, months=6.0):
    a = np.asarray(profits, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0 or months_span <= 0:
        return 0.0
    s = float(a.mean() / a.std(ddof=1))
    n = len(a) * months / months_span
    return s * math.sqrt(max(n, 0.0))


def main():
    print("=" * 126)
    print("V090：枠別×期間別のシャープ（簡易検証）")
    print("=" * 126)
    print("★ `CLAUDE.md` の段階2。**採用の根拠にはしない。**")
    print("  方針Aに必要なのは H 0.480 → 0.50。**弱局面で効いている枠**を特定する。\n")

    rec = sorted(load("OOS") + load("IS"))
    magics = sorted({x[4] for x in rec})
    print(f"  全期間 {len(rec)}建玉 / {len(magics)}枠\n")

    print("=" * 126)
    print("【1. 枠別×期間別の1取引シャープ】括弧内は件数。**件数が少ないt値は当てにならない**")
    print("=" * 126)
    print(f"{'magic':>10}" + "".join(f"{p[0][:14]:>17}" for p in PERIODS))
    rows = {}
    for mg in magics:
        cells, row = "", {}
        for pi, (pname, a, b) in enumerate(PERIODS):
            sub = [x[2] for x in rec
                   if x[4] == mg and a <= datetime.fromtimestamp(
                       x[0], tz=timezone.utc) < b]
            if len(sub) < MIN_N:
                cells += f"{'—':>17}"
                row[pi] = None
                continue
            s, t, tot = stat(sub)
            row[pi] = (s, t, tot, len(sub))
            cells += f"{f'{s:+.3f}({len(sub)})':>17}"
        rows[mg] = row
        print(f"{mg:>10}{cells}")

    # ---------- 2. 弱局面で正の枠 ----------
    print("\n" + "=" * 126)
    print("【2. 弱局面（2016-11〜2019-12）で正の枠と、その他期間での成績】")
    print("=" * 126)
    span_weak = (PERIODS[1][2] - PERIODS[0][1]).days / 30.44
    print(f"{'magic':>10}{'弱局面 件数':>12}{'弱局面 S':>11}{'弱局面 t':>10}"
          f"{'弱局面 純益':>13}{'金大相場 S':>12}{'IS前半 S':>11}{'IS後半 S':>11}"
          f"{'判定':>8}")
    good, bad = [], []
    for mg in magics:
        sub = [x[2] for x in rec
               if x[4] == mg and PERIODS[0][1] <= datetime.fromtimestamp(
                   x[0], tz=timezone.utc) < PERIODS[1][2]]
        if len(sub) < MIN_N:
            continue
        s, t, tot = stat(sub)
        others = []
        for pi in (2, 3, 4):
            r = rows[mg].get(pi)
            others.append(f"{r[0]:+.3f}" if r else "—")
        ok = s > 0
        (good if ok else bad).append((mg, s, t, tot, len(sub)))
        print(f"{mg:>10}{len(sub):>12}{s:>+11.4f}{t:>10.2f}{tot:>13,.0f}"
              f"{others[0]:>12}{others[1]:>11}{others[2]:>11}"
              f"{'正' if ok else '負':>8}")

    # ---------- 3. サブブックの期限シャープ ----------
    print("\n" + "=" * 126)
    print("【3. サブブックの期限シャープ（6ヶ月）】**枠を削ると N が減ることに注意**")
    print("=" * 126)
    weak = [x for x in rec
            if PERIODS[0][1] <= datetime.fromtimestamp(x[0], tz=timezone.utc)
            < PERIODS[1][2]]
    books = {
        "全枠": magics,
        "弱局面で正の枠のみ": [m for m, *_ in good],
        "弱局面で負の枠を除く": [m for m in magics if m not in [b[0] for b in bad]],
    }
    print(f"{'ブック':<24}{'枠数':>6}{'弱局面 件数':>12}{'1取引S':>10}"
          f"{'**H(6月)**':>12}{'方針A必要0.50':>16}")
    for bname, ms in books.items():
        sub = [x[2] for x in weak if x[4] in set(ms)]
        if len(sub) < MIN_N:
            continue
        s, _, _ = stat(sub)
        H = horizon_H(sub, span_weak, 6.0)
        print(f"{bname:<24}{len(set(ms)):>6}{len(sub):>12}{s:>10.4f}"
              f"{H:>12.3f}{'OK' if H >= 0.50 else 'NG':>16}")

    print("\n" + "=" * 126)
    print("【限界】")
    print("=" * 126)
    print("  ・**弱局面で選んで弱局面で評価すれば必ず良く見える**（選択バイアス）")
    print("  ・枠ごとの件数が少ないとt値は当てにならない")
    print("  ・枠を削ると N が減る。質の改善が √N の損失を上回る必要がある")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
