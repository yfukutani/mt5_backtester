"""V097：**ギャップの分解 — 分布の形か、時間依存か**（2026-09-13）。

【Codexの推奨】
> ③系列相関・同時損失を最優先で疑う。
> 同じ平均・分散の正規乱数と、実損益を独立再標本化した系列を比較。
> これで歪度・厚い裾など周辺分布全体の差を測る。
> 「枠別に日をシャッフル」「全枠をまとめて日をシャッフル」「全枠共通の連続ブロック」
> の比較で、同時依存と時間依存を分離する。

【V095・V096で分かったこと】

| 期限 | HJBの正しい基準（実際の条件） | 実測 | ギャップ |
|---|---:|---:|---:|
| 6ヶ月 | 59.6% | 50.7% | **−8.9pt** |
| 12ヶ月 | 67.1% | 33.0% | **−34.1pt** |

**6ヶ月のkはHJBの想定とぴったり一致していた**（k_match=4.00 vs 使ったk=4.0）ので、
**リスク水準のずれではギャップを説明できない。**

【本スクリプトの分解】
同じ期限・同じ方策・同じ倍率で、**取引列の作り方だけを変えて**到達率を比べる。

| 系列 | 作り方 | 壊すもの |
|---|---|---|
| **実履歴** | そのまま | — |
| **日ブロック入替** | 日単位の塊を入れ替える | **長期の依存**（局面の持続）だけ壊す |
| **取引シャッフル** | 取引の順序を完全にランダム化 | **すべての時間依存**を壊す |
| **正規化** | 平均・分散を保った正規乱数に置換 | 時間依存＋**分布の形**（裾・歪み） |

**実履歴 → 日ブロック → 取引シャッフル → 正規 と改善していくなら、
段階ごとに「長期依存」「短期依存」「分布の形」の寄与が読める。**

**正規化した系列の到達率が拡散近似の理論値に近づけば、
拡散近似そのものは正しく、差は実データの性質から来ていると言える。**

【限界】
- シャッフルは建玉の重なり（同時保有）を壊す。**入口・出口の時刻は元のまま**なので
  損益だけを差し替える近似
- 日ブロック入替は日をまたぐ建玉の扱いが曖昧になる
- 弱局面は約38ヶ月。**どの系列でも標本は増えない**
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_aware_sizing as das
import deadline_committed as dc
import policy_decomposition as pd
import target_policy_gap as tpg

QUIET_END = tpg.QUIET_END
CAP = 3.0
SEEDS = (11, 22, 33, 44, 55)


def variance_ratio(rec, a, b):
    """日次に集計した損益の分散比。1より大きければ正の系列相関。"""
    day = {}
    for t, _, prof, _ in rec:
        d = datetime.fromtimestamp(t, tz=timezone.utc)
        if not (a <= d < b):
            continue
        key = d.date()
        day[key] = day.get(key, 0.0) + prof
    keys = sorted(day)
    y = np.array([day[k] for k in keys], dtype=float)
    out = {}
    v1 = float(y.var(ddof=1))
    for q in (2, 5, 10, 20, 60):
        m = len(y) // q
        if m < 5:
            continue
        agg = y[:m * q].reshape(m, q).sum(axis=1)
        out[q] = float(agg.var(ddof=1)) / (q * v1) if v1 > 0 else float("nan")
    return len(y), v1, out


def shuffle_trades(rec, rng):
    """損益だけを取引間で入れ替える（時刻は元のまま）。"""
    prof = np.array([x[2] for x in rec], dtype=float)
    rng.shuffle(prof)
    return [(a, b, float(p), d) for (a, b, _, d), p in zip(rec, prof)]


def shuffle_day_blocks(rec, rng):
    """日単位の塊ごと損益を入れ替える（日内の同時性は保つ）。"""
    idx_by_day = {}
    for i, (t, _, _, _) in enumerate(rec):
        d = datetime.fromtimestamp(t, tz=timezone.utc).date()
        idx_by_day.setdefault(d, []).append(i)
    days = sorted(idx_by_day)
    order = list(range(len(days)))
    rng.shuffle(order)
    prof = [x[2] for x in rec]
    out = list(prof)
    for src_pos, dst_pos in enumerate(order):
        src, dst = idx_by_day[days[dst_pos]], idx_by_day[days[src_pos]]
        for j, i in enumerate(dst):
            out[i] = prof[src[j % len(src)]]
    return [(a, b, float(p), d) for (a, b, _, d), p in zip(rec, out)]


def normalize(rec, rng):
    """平均・分散を保った正規乱数に置換する。"""
    prof = np.array([x[2] for x in rec], dtype=float)
    g = rng.normal(prof.mean(), prof.std(ddof=1), size=len(prof))
    return [(a, b, float(p), d) for (a, b, _, d), p in zip(rec, g)]


def evaluate(rec, k, pol, cap, start, end_cap, months):
    ti = [x[0] for x in rec]
    hit = ruin = n = 0
    d = start
    while cod.add_months(d, months) <= end_cap:
        t_end = cod.add_months(d, months)
        h, r = dc.simulate(rec, ti, int(d.timestamp()), int(t_end.timestamp()),
                           k, pol, cap)
        hit += h
        ruin += r
        n += 1
        d += timedelta(days=7)
    return (hit / n if n else 0.0), (ruin / n if n else 0.0), n


def main():
    print("=" * 112)
    print("V097：ギャップの分解 — 分布の形か、時間依存か")
    print("=" * 112)
    print("★ Codexが最優先で疑った**③系列相関・同時損失**を直接測る。")
    print("  6ヶ月のkはHJBの想定とぴったり一致していた（k_match=4.00 vs 使ったk=4.0）ので、")
    print("  **リスク水準のずれではギャップを説明できない。**\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    pol = pd.HJB(das.Policy(H=0.48))

    # ---------- 1. 分散比 ----------
    print("=" * 112)
    print("【1. 日次損益の分散比】1より大きければ**正の系列相関**＝Hを過大評価している")
    print("=" * 112)
    for name, rec, a, b in (("OOS 弱局面", data["OOS"], a_oos, QUIET_END),
                            ("IS窓", data["IS"], a_is, b_is)):
        nd, v1, vr = variance_ratio(rec, a, b)
        cells = "".join(f"{f'{q}日:{v:.2f}':>12}" for q, v in vr.items())
        print(f"  {name:<12} 日数{nd:>5} 日次分散{v1:>12,.0f}{cells}")
    print("\n  → 20日・60日で1を大きく超えるなら、**長期の依存が効いている**")

    # ---------- 2. 系列の作り方を変えて到達率 ----------
    print("\n" + "=" * 112)
    print("【2. 系列の作り方を変えたときの到達率】弱局面・HJB方策・上限3倍")
    print("=" * 112)
    print(f"  シード{len(SEEDS)}本の平均。**実履歴→正規 と改善するなら、"
          f"差は実データの性質から来ている**")
    print(f"{'系列':<22}{'壊すもの':<26}"
          f"{'6月 到達':>10}{'6月 破綻':>10}{'12月 到達':>11}{'12月 破綻':>11}")

    def run_variant(fn, label, broke):
        res = {}
        for months, k in ((6, 4.0), (12, 2.0)):
            hs, rs = [], []
            for sd in (SEEDS if fn else (0,)):
                rec = fn(data["OOS"], np.random.default_rng(sd)) if fn \
                    else data["OOS"]
                h, r, _ = evaluate(rec, k, pol, CAP, a_oos, QUIET_END, months)
                hs.append(h)
                rs.append(r)
            res[months] = (float(np.mean(hs)), float(np.mean(rs)))
        print(f"{label:<22}{broke:<26}"
              f"{100*res[6][0]:>9.1f}%{100*res[6][1]:>9.1f}%"
              f"{100*res[12][0]:>10.1f}%{100*res[12][1]:>10.1f}%")
        return res

    base = run_variant(None, "**実履歴**", "—")
    dayb = run_variant(shuffle_day_blocks, "日ブロック入替", "長期の依存")
    shuf = run_variant(shuffle_trades, "取引シャッフル", "すべての時間依存")
    norm = run_variant(normalize, "**正規化**", "時間依存＋分布の形")

    # ---------- 3. 寄与の読み取り ----------
    print("\n" + "=" * 112)
    print("【3. 寄与の読み取り】拡散近似の理論値（V095の正しい基準）と比べる")
    print("=" * 112)
    theory = {6: 0.596, 12: 0.671}
    print(f"{'期限':>5}{'実履歴':>9}{'日ブロック':>12}{'取引シャッフル':>16}"
          f"{'正規化':>9}{'拡散の理論値':>14}")
    for months in (6, 12):
        print(f"{months:>4}月{100*base[months][0]:>8.1f}%"
              f"{100*dayb[months][0]:>11.1f}%{100*shuf[months][0]:>15.1f}%"
              f"{100*norm[months][0]:>8.1f}%{100*theory[months]:>13.1f}%")
    print()
    for months in (6, 12):
        print(f"  {months}ヶ月の分解：")
        print(f"    長期の依存        {100*(dayb[months][0]-base[months][0]):>+7.1f}pt")
        print(f"    短期の依存・同時性 {100*(shuf[months][0]-dayb[months][0]):>+7.1f}pt")
        print(f"    分布の形（裾・歪み）{100*(norm[months][0]-shuf[months][0]):>+7.1f}pt")
        print(f"    残り（最小ロット等）{100*(theory[months]-norm[months][0]):>+7.1f}pt")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・シャッフルは建玉の重なりを壊す。入口・出口の時刻は元のまま")
    print("  ・日ブロック入替は日をまたぐ建玉の扱いが曖昧")
    print("  ・弱局面は約38ヶ月。**どの系列でも標本は増えない**")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
