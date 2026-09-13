"""V099：**不毛な月に稼げる枠はあるか**（簡易検証・2026-09-13）。

【V098で確定したこと】
弱局面（38ヶ月）は**純益の80%を上位3ヶ月（全体の8%）で稼いでいる**。
**12ヶ月移動合計がマイナスの窓が26%**あり、そこからは2倍にできない。

**問題はサイジングでも枠配分でもなく、取引列そのものに不毛な期間があること。**
→ **残る道は「時期の異なる収益源を足す」ことだけ。**

【評価基準を変える】
これまでは追加枠を「1取引シャープ」で評価していた（V066でSCA-FXを42%と測った等）。
**それでは『いつ稼ぐか』が分からない。**

本スクリプトは次の基準で測る。

| 基準 | 意味 |
|---|---|
| **不毛月の損益** | ブック全体がマイナスの月に、その枠はいくら稼いだか |
| **月次相関** | ブック（その枠を除く）との月次損益の相関。**低い・負が良い** |
| **最悪の移動窓の改善** | その枠を抜くと6/12ヶ月移動合計の最小値がどう変わるか |
| **マイナス窓の割合** | その枠を抜くとマイナスの窓が増えるか減るか |

**1取引シャープが低くても、不毛月に稼ぐ枠は価値がある。**
逆に、シャープが高くてもブックと同時に沈む枠は、この目的には役に立たない。

【限界】
- 枠を抜く／足すの効果は線形近似（損益をそのまま足し引き）。**最小ロット制約を無視**
- 弱局面は38ヶ月。**月次38点しかなく、相関の推定は粗い**
- 枠ごとの件数が少ないと月次損益はほぼゼロになり、見かけ上「相関が低い」
- **既存の枠の中に答えがあるとは限らない。** なければ「新しい収益源が要る」が結論
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
import sleeve_ablation as sab

WEAK = (datetime(2016, 11, 9, tzinfo=timezone.utc),
        datetime(2020, 1, 1, tzinfo=timezone.utc))
IS_W = (datetime(2021, 6, 21, tzinfo=timezone.utc),
        datetime(2026, 6, 21, tzinfo=timezone.utc))
MIN_N = 20


def load_all():
    fx, gold = dkl.resolve_runs()
    rec = []
    for window in ("OOS", "IS"):
        for src in (fx.get(window), gold.get(window)):
            if src is None:
                continue
            rows = []
            for r in csv.DictReader(open(src, encoding="utf-8")):
                m = int(r["magic"])
                if m == 0:
                    continue
                rows.append((int(r["time"]), int(r["entry"]),
                             int(r["position_id"]), float(r["profit"]), m))
            rows.sort()
            opened = {}
            for t, entry, pid, profit, m in rows:
                if entry == 0:
                    opened[pid] = (t, m)
                else:
                    o = opened.pop(pid, None)
                    if o is None or profit == 0.0:
                        continue
                    rec.append((o[0], profit, m))
    rec.sort()
    return rec


def month_matrix(rec, a, b):
    """(月キー一覧, {magic: 月次損益ベクトル}) を返す。"""
    months = []
    d = datetime(a.year, a.month, 1, tzinfo=timezone.utc)
    while d < b:
        months.append((d.year, d.month))
        d = (datetime(d.year + 1, 1, 1, tzinfo=timezone.utc) if d.month == 12
             else datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc))
    idx = {k: i for i, k in enumerate(months)}
    mags = sorted({m for _, _, m in rec
                   if a <= datetime.fromtimestamp(_ if False else 0,
                                                  tz=timezone.utc) or True})
    mags = sorted({m for t, _, m in rec
                   if a <= datetime.fromtimestamp(t, tz=timezone.utc) < b})
    mat = {m: np.zeros(len(months)) for m in mags}
    cnt = {m: 0 for m in mags}
    for t, prof, m in rec:
        d = datetime.fromtimestamp(t, tz=timezone.utc)
        if not (a <= d < b):
            continue
        mat[m][idx[(d.year, d.month)]] += prof
        cnt[m] += 1
    return months, mat, cnt


def rolling(v, w):
    if len(v) < w:
        return np.array([])
    return np.array([v[i:i + w].sum() for i in range(len(v) - w + 1)])


def report(label, a, b, rec):
    months, mat, cnt = month_matrix(rec, a, b)
    mags = sorted(mat)
    book = np.sum([mat[m] for m in mags], axis=0)
    barren = book <= 0
    print("=" * 122)
    print(f"【{label}】{len(months)}ヶ月 / ブック純益 {book.sum():+,.0f}円 / "
          f"不毛な月 {int(barren.sum())}ヶ月")
    print("=" * 122)
    print(f"{'枠':<16}{'件数':>6}{'純益':>12}{'1取引S':>9}"
          f"{'**不毛月の損益**':>18}{'不毛月で正':>12}"
          f"{'他枠との月次相関':>18}{'抜くと12月窓の最小':>20}")
    base12 = rolling(book, 12)
    base_min = base12.min() if len(base12) else float("nan")
    base_neg = (base12 <= 0).mean() if len(base12) else float("nan")
    print(f"{'（ブック全体）':<16}{sum(cnt.values()):>6}{book.sum():>12,.0f}"
          f"{'—':>9}{book[barren].sum():>18,.0f}{'—':>12}{'—':>18}"
          f"{base_min:>20,.0f}")
    rows = []
    for m in mags:
        if cnt[m] < MIN_N:
            continue
        v = mat[m]
        others = book - v
        s = 0.0
        # 1取引シャープは月次ではなく取引単位で
        p = np.array([x[1] for x in rec
                      if x[2] == m and a <= datetime.fromtimestamp(
                          x[0], tz=timezone.utc) < b], dtype=float)
        if len(p) >= 3 and p.std(ddof=1) > 0:
            s = float(p.mean() / p.std(ddof=1))
        corr = (float(np.corrcoef(v, others)[0, 1])
                if v.std() > 0 and others.std() > 0 else float("nan"))
        r12 = rolling(others, 12)
        wo_min = r12.min() if len(r12) else float("nan")
        n_pos = int((v[barren] > 0).sum())
        rows.append((m, cnt[m], v.sum(), s, v[barren].sum(),
                     n_pos, int(barren.sum()), corr, wo_min))
    rows.sort(key=lambda r: -r[4])
    for (m, n, tot, s, bar, npos, nbar, corr, wo) in rows:
        print(f"{sab.MAGIC_NAME.get(m, str(m)):<16}{n:>6}{tot:>12,.0f}"
              f"{s:>9.4f}{bar:>18,.0f}{f'{npos}/{nbar}':>12}"
              f"{corr:>18.3f}{wo:>20,.0f}")
    print()
    return book, mat, barren, base_min, base_neg


def main():
    print("=" * 122)
    print("V099：不毛な月に稼げる枠はあるか（簡易検証）")
    print("=" * 122)
    print("★ V098より、問題は**利益の出ない長い期間**。評価基準を変える。")
    print("  『1取引シャープ』ではなく『**ブックが不毛な月に稼げるか**』で見る。\n")
    print("  **不毛月の損益がプラスで、月次相関が低い（負なら理想）枠**が価値を持つ。\n")

    rec = load_all()
    bw, mw, barw, minw, negw = report("OOS 弱局面（2016-11〜2019-12）",
                                      *WEAK, rec)
    bi, mi, bari, mini, negi = report("IS窓（2021-06〜2026-06）", *IS_W, rec)

    # ---------- 2. 両窓で不毛月に稼いだ枠 ----------
    print("=" * 122)
    print("【2. 両方の窓で『不毛月にプラス』だった枠】**これが増やすべき型**")
    print("=" * 122)
    good = []
    for m in sorted(set(mw) & set(mi)):
        bw_sum = mw[m][barw].sum()
        bi_sum = mi[m][bari].sum()
        if bw_sum > 0 and bi_sum > 0:
            good.append((m, bw_sum, bi_sum))
    if not good:
        print("  **なし。** 既存の枠には、両窓とも不毛月に稼ぐものがない。")
        print("  → **既存ブックの中に答えはない。新しい収益源が要る。**")
    for m, a_, b_ in sorted(good, key=lambda x: -(x[1])):
        print(f"  {sab.MAGIC_NAME.get(m, str(m)):<16}"
              f"弱局面の不毛月 {a_:+,.0f}円 / IS窓の不毛月 {b_:+,.0f}円")

    # ---------- 3. 必要な収益源の大きさ ----------
    print("\n" + "=" * 122)
    print("【3. どれだけの収益源が要るか】弱局面の12ヶ月移動合計を正にするには")
    print("=" * 122)
    r12 = rolling(bw, 12)
    print(f"  現状の12ヶ月移動合計：最小 {r12.min():+,.0f}円 / "
          f"中央 {np.median(r12):+,.0f}円 / マイナスの窓 "
          f"{int((r12 <= 0).sum())}/{len(r12)}")
    print(f"\n{'毎月の上乗せ':>14}{'12月移動の最小':>18}{'マイナス窓':>12}"
          f"{'12月で2倍に必要な+10万':>24}")
    for add in (0, 2000, 5000, 10000, 15000, 20000):
        v = bw + add
        rr = rolling(v, 12)
        need = int((rr < 100000).sum())
        print(f"{add:>13,}円{rr.min():>18,.0f}"
              f"{int((rr <= 0).sum()):>10}/{len(rr)}"
              f"{f'{len(rr)-need}/{len(rr)}':>24}")
    print("\n  ※ これは k=1・素の損益。実際は倍率kが掛かるので必要額はこれより小さい")
    print("  ※ 現在のブックの弱局面の月次平均は "
          f"{bw.mean():+,.0f}円（k=1）")

    print("\n" + "=" * 122)
    print("【限界】")
    print("=" * 122)
    print("  ・枠を抜く／足すの効果は線形近似。**最小ロット制約を無視している**")
    print("  ・弱局面は38ヶ月。月次38点しかなく、相関の推定は粗い")
    print("  ・件数が少ない枠は月次損益がほぼゼロになり、見かけ上『相関が低い』")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
