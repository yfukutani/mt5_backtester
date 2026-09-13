"""V092：**期間をまたいで一貫して正の枠を増量する**（簡易検証・2026-09-13）。

【V090で分かったこと】
弱局面で負に見えた枠（SCA USDJPY・SCA GOLD1）は、**その後の全期間で正**だった。
→ **弱局面を見て枠を削る案（C32・C40）は棄却した。**

代わりに、**期間をまたいで一貫して正の枠**が見つかった。

| 枠 | 弱局面 S (件数) | 金大相場 | IS前半 | IS後半 |
|---|---:|---:|---:|---:|
| RSI GBPUSD (20260774) | **+0.473** (38) | — | +0.138 | +0.230 |
| RSI USDJPY (20260610) | +0.208 (55) | −0.044 | +0.011 | +0.168 |
| PB GOLD (20260640) | +0.119 (36) | — | — | +0.465 |

**これらは削るのではなく増やす対象。** 取引数 N も同時に増えるので
`H = 1取引S × √N` の両方に効く。

【却下済みの類似案との違い】
- V026（共分散に基づく配分）：全9条件で −2.4〜−2.9pt
- V031（到達確率を目的にした枠の取捨選択）：IS +6.68pt → OOS −9.10pt
- V090（弱局面で負の枠を削る）：**他期間で正なので棄却**

**本案の選抜基準は「成績の最大化」ではなく「期間をまたいだ符号の安定性」である。**
これは上の3つと違う軸だが、**うまくいく保証はない。**

【2方向とも測る（どちらか一方では公平でない）】

| 方向 | 選抜に使う期間 | 評価する期間 | 意味 |
|---|---|---|---|
| **前向き（運用可能）** | 2016-11〜2019-12（弱局面） | 2020-01〜2026-06 | **実際に運用できる手順** |
| 後ろ向き（安定性の確認） | 2020-01〜2026-06 | 2016-11〜2019-12（弱局面） | 枠の質が安定しているかの確認のみ |

**後ろ向きは未来の情報を使うので運用手順にはならない。** 安定性の確認にのみ使う。

【限界】
- 増量は「その枠の損益を定数倍する」近似。**最小ロット制約を無視している**
  （実際には0.01ロットの枠を2倍にしても0.02にしかならず、比例はするが刻みが粗い）
- 枠ごとの件数が少ない（36〜55件）。**符号の安定性そのものが偶然かもしれない**
- 増量すると相関のある枠が同時に効き、分散が想定より増える可能性
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
LATER = (datetime(2020, 1, 1, tzinfo=timezone.utc),
         datetime(2026, 6, 21, tzinfo=timezone.utc))
SUB_WEAK = [(datetime(2016, 11, 9, tzinfo=timezone.utc),
             datetime(2018, 6, 1, tzinfo=timezone.utc)),
            (datetime(2018, 6, 1, tzinfo=timezone.utc),
             datetime(2020, 1, 1, tzinfo=timezone.utc))]
SUB_LATER = [(datetime(2020, 1, 1, tzinfo=timezone.utc),
              datetime(2021, 6, 21, tzinfo=timezone.utc)),
             (datetime(2021, 6, 21, tzinfo=timezone.utc),
              datetime(2024, 1, 1, tzinfo=timezone.utc)),
             (datetime(2024, 1, 1, tzinfo=timezone.utc),
              datetime(2026, 6, 21, tzinfo=timezone.utc))]
MIN_N = 25
BOOSTS = [1.5, 2.0, 3.0]


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
                             int(r["position_id"]), float(r["profit"]),
                             float(r["volume"]), m))
            rows.sort()
            opened = {}
            for t, entry, pid, profit, vol, m in rows:
                if entry == 0:
                    opened[pid] = (t, vol, m)
                else:
                    o = opened.pop(pid, None)
                    if o is None or profit == 0.0 or o[1] <= 0:
                        continue
                    rec.append((o[0], profit, o[2] if False else m))
    rec.sort()
    return rec


def in_range(t, a, b):
    d = datetime.fromtimestamp(t, tz=timezone.utc)
    return a <= d < b


def select_stable(rec, subs):
    """与えた小期間**すべて**で1取引シャープが正の枠を返す。
    件数が MIN_N 未満の小期間は判定から外す（そこでは判断しない）。"""
    mags = sorted({m for _, _, m in rec})
    out = []
    detail = {}
    for mg in mags:
        signs, ok = [], True
        seen = 0
        for a, b in subs:
            p = [x[1] for x in rec if x[2] == mg and in_range(x[0], a, b)]
            if len(p) < MIN_N:
                signs.append(None)
                continue
            seen += 1
            arr = np.array(p, dtype=float)
            s = float(arr.mean() / arr.std(ddof=1)) if arr.std(ddof=1) > 0 else 0.0
            signs.append(s)
            if s <= 0:
                ok = False
        detail[mg] = signs
        if ok and seen >= 2:
            out.append(mg)
    return out, detail


def book_stats(rec, mags_boost, boost, a, b, months_span):
    """増量後の1取引シャープと期限シャープ（6ヶ月）。"""
    p = []
    for t, prof, mg in rec:
        if not in_range(t, a, b):
            continue
        p.append(prof * (boost if mg in mags_boost else 1.0))
    arr = np.array(p, dtype=float)
    if len(arr) < 3 or arr.std(ddof=1) == 0:
        return 0.0, 0.0, len(arr)
    s = float(arr.mean() / arr.std(ddof=1))
    n6 = len(arr) * 6.0 / months_span
    return s, s * math.sqrt(max(n6, 0.0)), len(arr)


def main():
    print("=" * 118)
    print("V092：期間をまたいで一貫して正の枠を増量する（簡易検証）")
    print("=" * 118)
    print("★ `CLAUDE.md` の段階2。**採用の根拠にはしない。**")
    print("  選抜基準は『成績の最大化』ではなく『期間をまたいだ符号の安定性』。")
    print("  V026（共分散配分）・V031（到達確率で取捨選択）・V090（弱局面で削る）とは別の軸。\n")

    rec = load_all()
    span_weak = (WEAK[1] - WEAK[0]).days / 30.44
    span_later = (LATER[1] - LATER[0]).days / 30.44
    print(f"  全期間 {len(rec)}建玉 / 弱局面 {span_weak:.1f}ヶ月 / "
          f"以後 {span_later:.1f}ヶ月\n")

    # ---------- 前向き（運用可能な手順） ----------
    print("=" * 118)
    print("【前向き：弱局面で選抜 → 以後の期間で評価】**これが実際に運用できる手順**")
    print("=" * 118)
    sel_f, det_f = select_stable(rec, SUB_WEAK)
    print("  弱局面を2つに割って、**両方で正**だった枠：")
    for mg in sel_f:
        s = det_f[mg]
        cells = " / ".join("—" if v is None else f"{v:+.3f}" for v in s)
        print(f"    {sab.MAGIC_NAME.get(mg, str(mg)):<16} {cells}")
    if not sel_f:
        print("    **なし**")
    print()
    base_s, base_H, base_n = book_stats(rec, set(), 1.0, *LATER, span_later)
    print(f"{'増量':>6}{'枠数':>6}{'以後 件数':>11}{'以後 1取引S':>13}"
          f"{'以後 H(6月)':>13}{'基準比':>10}")
    print(f"{'なし':>6}{0:>6}{base_n:>11}{base_s:>13.4f}{base_H:>13.3f}"
          f"{'—':>10}")
    for b in BOOSTS:
        s, H, n = book_stats(rec, set(sel_f), b, *LATER, span_later)
        print(f"{b:>6.1f}{len(sel_f):>6}{n:>11}{s:>13.4f}{H:>13.3f}"
              f"{H-base_H:>+10.3f}")

    # ---------- 後ろ向き（安定性の確認のみ） ----------
    print("\n" + "=" * 118)
    print("【後ろ向き：2020年以後で選抜 → 弱局面で評価】**未来の情報を使うので運用手順ではない**")
    print("=" * 118)
    sel_b, det_b = select_stable(rec, SUB_LATER)
    print("  2020年以後を3つに割って、**全部で正**だった枠：")
    for mg in sel_b:
        s = det_b[mg]
        cells = " / ".join("—" if v is None else f"{v:+.3f}" for v in s)
        print(f"    {sab.MAGIC_NAME.get(mg, str(mg)):<16} {cells}")
    if not sel_b:
        print("    **なし**")
    print()
    bs, bH, bn = book_stats(rec, set(), 1.0, *WEAK, span_weak)
    print(f"{'増量':>6}{'枠数':>6}{'弱局面 件数':>13}{'弱局面 1取引S':>15}"
          f"{'**H(6月)**':>13}{'基準比':>10}{'方針A 0.50':>13}")
    print(f"{'なし':>6}{0:>6}{bn:>13}{bs:>15.4f}{bH:>13.3f}{'—':>10}"
          f"{'OK' if bH >= 0.50 else 'NG':>13}")
    for b in BOOSTS:
        s, H, n = book_stats(rec, set(sel_b), b, *WEAK, span_weak)
        print(f"{b:>6.1f}{len(sel_b):>6}{n:>13}{s:>15.4f}{H:>13.3f}"
              f"{H-bH:>+10.3f}{'OK' if H >= 0.50 else 'NG':>13}")

    # ---------- 参考：両方向で選ばれた枠 ----------
    both = sorted(set(sel_f) & set(sel_b))
    print("\n" + "=" * 118)
    print("【参考：前向き・後ろ向きの両方で選ばれた枠】")
    print("=" * 118)
    if both:
        for mg in both:
            print(f"    {sab.MAGIC_NAME.get(mg, str(mg))}")
    else:
        print("    **なし**——枠の質は期間をまたいで安定していない")

    print("\n" + "=" * 118)
    print("【限界】")
    print("=" * 118)
    print("  ・増量は損益の定数倍という近似。**最小ロット制約を無視している**")
    print("  ・枠ごとの件数が少ない。**符号の安定性そのものが偶然かもしれない**")
    print("  ・増量すると相関のある枠が同時に効き、分散が想定より増える可能性")
    print("  ・後ろ向きは未来の情報を使う。**運用手順ではなく安定性の確認**")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
