"""V106：**SCAフィルタが不毛期間と到達率を直せるか**（簡易検証・2026-09-14）。

【V105で出た陽性】
SCA GBPJPY 1枠に絞ると、**IS窓で閾値を決めたフィルタが弱局面でも効いた。**

| フィルタ | 残る割合 | 必要な改善 | **実際の改善** | 判定 |
|---|---:|---:|---:|---|
| **レンジ幅：IS最良の層（最大25%）** | 21% | 120.4% | **+152.8%** | OK |
| **時間帯：IS平均が正の時のみ** | 55% | 34.4% | **+105.5%** | OK |
| **方向：IS優位側のみ（買い）** | 54% | 35.9% | **+128.8%** | OK |
| 曜日 | 63% | 26.2% | −122.3% | NG |

レンジ幅は**両窓で単調**（最大25%がどちらも最良：IS +0.1437 / 弱局面 +0.0738）。
SCAの中核仮説「**広いアジア時間レンジのブレイクほど質が高い**」と整合する。

【ただしV077の教訓】
V077では**期限シャープが上がったフィルタでも、実際の到達率は下がった**
（時間帯フィルタで 36.0% → 30.2%）。**1取引シャープの改善は到達率を保証しない。**

【本スクリプトで測ること】
1. **不毛期間**：フィルタ適用後、12ヶ月移動合計のマイナス窓はどうなるか
2. **到達率**：実際に2倍へ届く割合はどうなるか（kはIS窓から選ぶ）
3. **損益・想定月利・最大DD**（プロジェクトルール）

**2が本命。** ここで上がらなければ、V077と同じ結末になる。

【限界】
- フィルタは**取引を捨てる**ので取引数が減る。`H = S×√N` の N が減る
- 閾値はIS窓で決めたが、**OOSは何度も見ている**
- `rel_sl` はストップ距離であってレンジ幅そのものではない（代理）
- 実際にEAへ実装すると、**捨てた取引の後続（ナンピン・両建て等）も変わる**。
  本スクリプトはそれを無視した上限側の見積もり
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_committed as dc
import dynamic_k_lag as dkl
import target_policy_gap as tpg

SCA_GJ = 20261001
QUIET_END = tpg.QUIET_END
WEAK = (datetime(2016, 11, 9, tzinfo=timezone.utc), QUIET_END)
IS_W = (datetime(2021, 6, 21, tzinfo=timezone.utc),
        datetime(2026, 6, 21, tzinfo=timezone.utc))
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
CAPITAL = co.CAPITAL


def load_full():
    """(t_in, t_out, profit, volume, magic, hour, side, rel) を返す。"""
    fx, gold = dkl.resolve_runs()
    out = {}
    for window in ("OOS", "IS"):
        rec = []
        for src in (fx.get(window), gold.get(window)):
            if src is None:
                continue
            rows = []
            for r in csv.DictReader(open(src, encoding="utf-8")):
                m = int(r["magic"])
                if m == 0:
                    continue
                rows.append((int(r["time"]), int(r["entry"]),
                             int(r["position_id"]), float(r["profit"]),
                             float(r["volume"]), m, int(r["type"]),
                             float(r["price"]), float(r["sl"])))
            rows.sort()
            opened = {}
            for t, entry, pid, profit, vol, m, typ, price, sl in rows:
                if entry == 0:
                    rel = (abs(price - sl) / price
                           if sl > 0 and price > 0 else 0.0)
                    opened[pid] = (t, vol, m, typ, rel)
                else:
                    o = opened.pop(pid, None)
                    if o is None or profit == 0.0 or o[1] <= 0:
                        continue
                    d = datetime.fromtimestamp(o[0], tz=timezone.utc)
                    rec.append((o[0], t, profit, o[1], o[2], d.hour,
                                o[3], o[4]))
        rec.sort()
        out[window] = rec
    return out


def months_of(a, b):
    res, d = [], datetime(a.year, a.month, 1, tzinfo=timezone.utc)
    while d < b:
        res.append((d.year, d.month))
        d = (datetime(d.year + 1, 1, 1, tzinfo=timezone.utc) if d.month == 12
             else datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc))
    return res


def monthly(rec, a, b, keep=None):
    ms = months_of(a, b)
    idx = {k: i for i, k in enumerate(ms)}
    v = np.zeros(len(ms))
    for x in rec:
        d = datetime.fromtimestamp(x[0], tz=timezone.utc)
        if not (a <= d < b):
            continue
        if x[4] == SCA_GJ and keep is not None and not keep(x):
            continue
        v[idx[(d.year, d.month)]] += x[2]
    return ms, v


def rolling(v, w):
    if len(v) < w:
        return np.array([])
    return np.array([v[i:i + w].sum() for i in range(len(v) - w + 1)])


def to4(rec, keep=None):
    return [(a, b, c, d) for a, b, c, d, m, h, s, r in rec
            if not (m == SCA_GJ and keep is not None and
                    not keep((a, b, c, d, m, h, s, r)))]


def evaluate(rec4, k, start, end_cap, months):
    ti = [x[0] for x in rec4]
    hit = ruin = n = 0
    d = start
    while cod.add_months(d, months) <= end_cap:
        t_end = cod.add_months(d, months)
        h, r = dc.simulate(rec4, ti, int(d.timestamp()),
                           int(t_end.timestamp()), k, None, 0.0)
        hit += h
        ruin += r
        n += 1
        d += timedelta(days=7)
    return (hit / n if n else 0.0), (ruin / n if n else 0.0), n


def pick_k(rec4, start, end_cap, months):
    """R2ルール：IS最大から1pt以内のkの中央値。"""
    hs = [evaluate(rec4, k, start, end_cap, months)[0] for k in K_GRID]
    top = max(hs)
    near = [k for k, h in zip(K_GRID, hs) if h >= top - 0.01]
    best = float(np.median(near))
    if best not in K_GRID:
        best = min(near, key=lambda k: abs(k - best))
    return best, max(hs)


def main():
    print("=" * 116)
    print("V106：SCAフィルタが不毛期間と到達率を直せるか（簡易検証）")
    print("=" * 116)
    print("★ V105でフィルタ3種が `S_q/S > 1/√q` を越えた。**だが到達率は別問題。**")
    print("  V077では期限シャープが上がったフィルタでも到達率は下がった。\n")

    data = load_full()
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    # --- IS窓でフィルタの閾値を決める ---
    I = [x for x in data["IS"] if x[4] == SCA_GJ]
    rel_i = np.array([x[7] for x in I if x[7] > 0])
    q75 = float(np.quantile(rel_i, 0.75))
    by_h = {}
    for x in I:
        by_h.setdefault(x[5], []).append(x[2])
    good_h = {h for h, v in by_h.items() if len(v) >= 10 and np.mean(v) > 0}
    by_s = {}
    for x in I:
        by_s.setdefault(x[6], []).append(x[2])
    best_side = max(by_s.items(), key=lambda kv: float(np.mean(kv[1])))[0]

    FILTERS = [
        ("（フィルタなし・基準）", None),
        ("レンジ幅 上位25%のみ", lambda x: x[7] > q75),
        ("時間帯 IS優位のみ", lambda x: x[5] in good_h),
        ("方向 IS優位のみ", lambda x: x[6] == best_side),
        ("レンジ幅×時間帯", lambda x: x[7] > q75 and x[5] in good_h),
        ("時間帯×方向", lambda x: x[5] in good_h and x[6] == best_side),
        ("**3つ全部**", lambda x: x[7] > q75 and x[5] in good_h
         and x[6] == best_side),
    ]
    print(f"  IS窓で決めた閾値：レンジ幅 > {q75:.5f} / 有効な時間 {sorted(good_h)} / "
          f"方向 {'買い' if best_side == 0 else '売り'}\n")

    # ---------- 1. 不毛期間 ----------
    print("=" * 116)
    print("【1. 不毛期間】12ヶ月移動合計のマイナス窓")
    print("=" * 116)
    for label, (a, b), w in (("OOS 弱局面", WEAK, "OOS"), ("IS窓", IS_W, "IS")):
        print(f"\n--- {label} ---")
        print(f"{'フィルタ':<24}{'SCA残':>8}{'純益':>12}{'12月移動 最小':>16}"
              f"{'12月マイナス窓':>16}{'6月マイナス窓':>15}")
        n_all = len([x for x in data[w] if x[4] == SCA_GJ
                     and a <= datetime.fromtimestamp(x[0], tz=timezone.utc) < b])
        for name, fn in FILTERS:
            _, v = monthly(data[w], a, b, fn)
            keep_n = (n_all if fn is None else
                      len([x for x in data[w] if x[4] == SCA_GJ and fn(x)
                           and a <= datetime.fromtimestamp(
                               x[0], tz=timezone.utc) < b]))
            r12, r6 = rolling(v, 12), rolling(v, 6)
            print(f"{name:<24}{keep_n:>8}{v.sum():>12,.0f}{r12.min():>16,.0f}"
                  f"{f'{int((r12 <= 0).sum())}/{len(r12)}':>16}"
                  f"{f'{int((r6 <= 0).sum())}/{len(r6)}':>15}")

    # ---------- 2. 到達率 ----------
    print("\n" + "=" * 116)
    print("【2. 到達率】**これが本命。** kはIS窓からR2ルールで選ぶ")
    print("=" * 116)
    for months, tgt in ((6, 0.65), (12, 0.90)):
        print(f"\n--- 期限{months}ヶ月（判定 {100*tgt:.0f}%）---")
        print(f"{'フィルタ':<24}{'IS選択k':>9}{'IS到達':>9}{'IS破綻':>9}"
              f"│{'**OOS到達**':>13}{'OOS破綻':>10}{'判定':>7}")
        for name, fn in FILTERS:
            ris = to4(data["IS"], fn)
            roo = to4(data["OOS"], fn)
            k, _ = pick_k(ris, a_is, b_is, months)
            ih, ir, _ = evaluate(ris, k, a_is, b_is, months)
            oh, orr, _ = evaluate(roo, k, a_oos, QUIET_END, months)
            print(f"{name:<24}{k:>9.0f}{100*ih:>8.1f}%{100*ir:>8.1f}%"
                  f"│{100*oh:>12.1f}%{100*orr:>9.1f}%"
                  f"{'OK' if oh >= tgt else 'NG':>7}")

    print("\n" + "=" * 116)
    print("【限界】")
    print("=" * 116)
    print("  ・フィルタは取引を捨てるので `H = S×√N` の N が減る")
    print("  ・閾値はIS窓で決めたが、**OOSは何度も見ている**")
    print("  ・`rel_sl` はストップ距離であってレンジ幅そのものではない（代理）")
    print("  ・EAへ実装すると**捨てた取引の後続も変わる**。本スクリプトは上限側の見積もり")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
