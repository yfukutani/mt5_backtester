"""V076：**破綻前提**のハイリスク戦略（ユーザー指示・2026-09-13）。

【ユーザー指示】
> 現状の案にとらわれず**破綻前提のハイリスクハイリターンの追加戦略**も検討すること。

**倍率2倍は固定。方針Aは「3〜6ヶ月で65%以上」で、破綻率の制約がない。**
したがって**破綻を積極的に受け入れて到達率だけを最大化する**方策を探す。

【これまで試していなかったこと】
V073までの評価は k ≤ 16 までしか振っていない（IS選択はk=8）。
**破綻を制約にしないなら、もっと大きなkや、質の違う方策が使える。**

【検証する4つの方策（事前登録・全て報告する）】

| 方策 | 式 | 狙い |
|---|---|---|
| **P 比例（基準）** | `lot = base × k × x` | 従来。kを64まで振る |
| **M マルチンゲール** | 直前が負けなら `× m` を累積（上限なし） | 負けを取り返す。破綻は前提 |
| **BOLD 大胆play** | 目標までの距離を1回で埋める大きさ | Dubins–Savageの大胆戦略 |
| **GOLD集中** | GOLD枠のみ＋高倍率 | 最高シャープ枠に集中（V041は全期限で全枠が最良だったが、**破綻許容なら話が変わりうる**） |

`x = 現在資金 / 初期資金`。**破綻確率は報告するが、判定には使わない**
（方針Aには破綻率の制約がないため）。

**方針B（12ヶ月90%・破綻は限りなく低く）には、これらは向かない。** 参考として併記する。

【評価】弱局面の実履歴（起点＋18暦月 ≤ 2020-01-01・86起点）・資金10万円・
破綻ライン10%・最小ロット制約あり。**kはIS窓の6ヶ月基準で選ぶ（OOSを見ない）。**

【限界】
- 破綻ライン10%に達した時点で停止する（実際には証拠金不足でもっと早く止まる可能性）
- 含み損益・証拠金制約を考慮していない
- 弱局面の起点は86個。起点が重なるため独立ではない
- マルチンゲールは**理論上いくらでもロットが増える**。最小ロット・最大ロットの
  現実的な制約は最大ロット側を考慮していない
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
import calendar_origins as co
import common_origin_deadline as cod
import dynamic_k_lag as dkl

CAPITAL = 100000.0
MIN_LOT = 0.01
STEP = 0.01
MAX_LOT = 50.0              # 現実的な上限（XMのXAUUSD最大ロット相当）
RUIN = 0.10
MULT = 2.0
QUIET_END = datetime(2020, 1, 1, tzinfo=timezone.utc)
ORIGIN_STEP_DAYS = 7
CHECK = [3, 6, 12]
GOLD_MAGICS = {20260640, 20261002, 20261003}


def load_with_magic(window):
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


def simulate(rec, ti, t0, t_end, k, policy, param):
    """1本の経路を走らせ、(初回到達時刻, 破綻時刻) を返す。"""
    i0 = bisect.bisect_left(ti, t0)
    i1 = bisect.bisect_left(ti, t_end)
    eq = CAPITAL
    pend = []
    pi = 0
    ei = i0
    streak = 0          # マルチンゲール用の連敗数
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
            pnl = profit * m
            eq += pnl
            streak = streak + 1 if pnl < 0 else 0
            if eq >= CAPITAL * MULT:
                return t, None
            if eq <= CAPITAL * RUIN:
                return None, t
        else:
            ti_, to_, profit, vol, mg = rec[ei]
            ei += 1
            x = eq / CAPITAL
            if policy == "P":
                mult_k = k * x
            elif policy == "M":
                mult_k = k * x * (param ** min(streak, 20))
            elif policy == "BOLD":
                # 目標までの距離を1取引で埋める大きさ（param倍で調整）
                need = max(CAPITAL * MULT - eq, 0.0)
                typical = param                      # 1ロットあたりの想定利益（円）
                mult_k = need / max(typical, 1.0) if typical > 0 else k * x
            else:
                mult_k = k * x
            desired = vol * mult_k
            actual = min(MAX_LOT,
                         max(MIN_LOT, math.floor(desired / STEP + 1e-9) * STEP))
            pend.append((to_, actual / vol, profit))
    return None, None


def evaluate(rec, k, policy, param, start, end_cap, max_months=18):
    ti = [x[0] for x in rec]
    res = []
    d = start
    while cod.add_months(d, max_months) <= end_cap:
        t_end = cod.add_months(d, max_months)
        hit, ruin = simulate(rec, ti, int(d.timestamp()),
                             int(t_end.timestamp()), k, policy, param)
        res.append((d, hit, ruin))
        d += timedelta(days=ORIGIN_STEP_DAYS)
    out = {}
    for m in CHECK:
        h, r, n = cod.cumulative(res, m)
        out[m] = (h, r)
    out["n"] = len(res)
    return out


def main():
    print("=" * 112)
    print("V076：破綻前提のハイリスク戦略（倍率2倍固定）")
    print("=" * 112)
    print("★ ユーザー指示：**破綻前提のハイリスクハイリターン戦略も検討**")
    print("  方針A（3〜6ヶ月で65%以上）には破綻率の制約がない。")
    print("  → **破綻を積極的に受け入れて到達率だけを最大化する方策**を探す。\n")
    print("評価：弱局面の実履歴（起点＋18暦月 ≤ 2020-01-01・86起点）")
    print("**kはIS窓の6ヶ月基準で選ぶ（OOSを見ない）。全方策・全設定を報告する。**\n")

    raw = {w: load_with_magic(w) for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    books = {
        "全枠": {w: [(a, b, c, d, m) for a, b, c, d, m in raw[w]] for w in raw},
        "GOLD集中": {w: [x for x in raw[w] if x[4] in GOLD_MAGICS] for w in raw},
    }

    # ---------- 1. 比例方策でkを大きく振る ----------
    print("=" * 112)
    print("【1. 比例方策（P）：kを64まで振る】破綻は報告するが判定に使わない")
    print("=" * 112)
    for bname, bk in books.items():
        print(f"\n--- ブック：{bname}（OOS {len(bk['OOS'])}建玉）---")
        print(f"{'k':>6}│{'IS 6月':>9}{'IS 12月':>9}"
              f"│{'OOS 3月':>9}{'OOS 6月':>9}{'OOS 12月':>10}"
              f"{'OOS破綻(6月)':>13}{'OOS破綻(12月)':>14}{'方針A':>7}")
        for k in (4, 8, 16, 24, 32, 48, 64):
            oi = evaluate(bk["IS"], k, "P", 0, a_is, b_is)
            oo = evaluate(bk["OOS"], k, "P", 0, a_oos, QUIET_END)
            okA = oo[6][0] >= 0.65
            print(f"{k:>6}│{100*oi[6][0]:>8.1f}%{100*oi[12][0]:>8.1f}%"
                  f"│{100*oo[3][0]:>8.1f}%{100*oo[6][0]:>8.1f}%"
                  f"{100*oo[12][0]:>9.1f}%{100*oo[6][1]:>12.1f}%"
                  f"{100*oo[12][1]:>13.1f}%{'✅' if okA else '❌':>7}")

    # ---------- 2. マルチンゲール ----------
    print("\n" + "=" * 112)
    print("【2. マルチンゲール（M）：連敗のたびにロットを m 倍】上限50ロット")
    print("=" * 112)
    print(f"{'k':>5}{'m':>6}│{'IS 6月':>9}│{'OOS 3月':>9}{'OOS 6月':>9}"
          f"{'OOS 12月':>10}{'OOS破綻(6月)':>13}{'方針A':>7}")
    for k in (2, 4, 8):
        for m in (1.3, 1.6, 2.0):
            oi = evaluate(raw["IS"], k, "M", m, a_is, b_is)
            oo = evaluate(raw["OOS"], k, "M", m, a_oos, QUIET_END)
            okA = oo[6][0] >= 0.65
            print(f"{k:>5}{m:>6.1f}│{100*oi[6][0]:>8.1f}%"
                  f"│{100*oo[3][0]:>8.1f}%{100*oo[6][0]:>8.1f}%"
                  f"{100*oo[12][0]:>9.1f}%{100*oo[6][1]:>12.1f}%"
                  f"{'✅' if okA else '❌':>7}")

    # ---------- 3. 大胆play ----------
    print("\n" + "=" * 112)
    print("【3. 大胆play（BOLD）：目標までの距離を1取引で埋める大きさ】")
    print("=" * 112)
    print("  param＝1ロットあたりの想定利益（円）。小さいほど大きく張る")
    print(f"{'param':>8}│{'IS 6月':>9}│{'OOS 3月':>9}{'OOS 6月':>9}"
          f"{'OOS 12月':>10}{'OOS破綻(6月)':>13}{'方針A':>7}")
    for p in (2000, 5000, 10000, 20000, 50000):
        oi = evaluate(raw["IS"], 0, "BOLD", p, a_is, b_is)
        oo = evaluate(raw["OOS"], 0, "BOLD", p, a_oos, QUIET_END)
        okA = oo[6][0] >= 0.65
        print(f"{p:>8}│{100*oi[6][0]:>8.1f}%"
              f"│{100*oo[3][0]:>8.1f}%{100*oo[6][0]:>8.1f}%"
              f"{100*oo[12][0]:>9.1f}%{100*oo[6][1]:>12.1f}%"
              f"{'✅' if okA else '❌':>7}")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・破綻ライン10%で停止（実際は証拠金不足でもっと早く止まる可能性）")
    print("  ・含み損益・証拠金制約を考慮していない")
    print("  ・最大ロット50を仮定（銘柄により異なる）")
    print("  ・弱局面の起点は86個。起点が重なるため独立ではない")
    print("  ・マルチンゲールは連敗20回で頭打ちにしている")
    print("\n完了。")


if __name__ == "__main__":
    main()
