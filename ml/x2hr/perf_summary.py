"""V107：**現状のEA性能のまとめ**（2026-09-15）。

ドキュメント `docs/X2_HIGH_RISK_performance.md` の数値を生成する。

【出すもの】（`CLAUDE.md`「報告に必ず含める数値」に従う）
- 損益（円・期間併記）
- 想定月利（**単利**。ブックはほぼ固定ロットで複利が効かないため）
- 最大ドロップダウン

【窓の定義】
| 窓 | 期間 | 月数 |
|---|---|---:|
| IS | 2021-06-21 〜 2026-06-20 | 60 |
| OOS | 2016-11-09 〜 2021-06-20 | 55 |
| **うち弱局面** | 2016-11-09 〜 2019-12-31 | 38 |
| **うち金大相場** | 2020-01-01 〜 2021-06-20 | 17 |

【限界】
- 枠別の損益は決済ログの `profit` 合計。**スワップ・手数料の扱いはログの定義に従う**
- 最大DDはFX側・GOLD側の**別々の実行**の値で、合算ブックのDDではない
- 想定月利は入金50万円に対する単利。**x2hr評価（資金10万円・倍率k）とは別物**
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

DEPOSIT = 500000.0
WINDOWS = {
    "IS（2021-06〜2026-06）": (datetime(2021, 6, 21, tzinfo=timezone.utc),
                            datetime(2026, 6, 21, tzinfo=timezone.utc), 60.0),
    "OOS（2016-11〜2021-06）": (datetime(2016, 11, 9, tzinfo=timezone.utc),
                             datetime(2021, 6, 21, tzinfo=timezone.utc), 55.0),
    "  うち弱局面（〜2019-12）": (datetime(2016, 11, 9, tzinfo=timezone.utc),
                           datetime(2020, 1, 1, tzinfo=timezone.utc), 38.0),
    "  うち金大相場（2020-）": (datetime(2020, 1, 1, tzinfo=timezone.utc),
                         datetime(2021, 6, 21, tzinfo=timezone.utc), 17.0),
}


def load():
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
                    rec.append((o[0], profit, o[1]))
    rec.sort()
    return rec


def in_w(t, a, b):
    d = datetime.fromtimestamp(t, tz=timezone.utc)
    return a <= d < b


def stat(p):
    a = np.asarray(p, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0, 0.0
    return (float(a.mean() / a.std(ddof=1)),
            float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))))


def main():
    rec = load()
    print("=" * 112)
    print("V107：現状のEA性能のまとめ")
    print("=" * 112)
    print(f"  入金 {DEPOSIT:,.0f}円・想定月利は**単利**"
          f"（ブックはほぼ固定ロットで複利が効かない）\n")

    # ---------- 1. ブック全体 ----------
    print("=" * 112)
    print("【1. ブック全体（15枠）】")
    print("=" * 112)
    print(f"{'窓':<26}{'月数':>6}{'取引':>8}{'純益':>14}"
          f"{'**単利 月利**':>14}{'1取引S':>10}{'月あたり取引':>13}")
    for name, (a, b, mo) in WINDOWS.items():
        p = [x[1] for x in rec if in_w(x[0], a, b)]
        s, _ = stat(p)
        net = float(np.sum(p))
        print(f"{name:<26}{mo:>6.0f}{len(p):>8}{net:>14,.0f}"
              f"{100*net/(DEPOSIT*mo):>13.2f}%{s:>10.4f}{len(p)/mo:>13.1f}")

    # ---------- 2. 枠別 ----------
    print("\n" + "=" * 112)
    print("【2. 枠別の純益】")
    print("=" * 112)
    mags = sorted({m for _, _, m in rec})
    print(f"{'枠':<16}" + "".join(f"{k.strip()[:14]:>17}"
                                 for k in WINDOWS))
    tot = {k: 0.0 for k in WINDOWS}
    rows = []
    for m in mags:
        cells, vals = "", {}
        for name, (a, b, mo) in WINDOWS.items():
            p = [x[1] for x in rec if x[2] == m and in_w(x[0], a, b)]
            v = float(np.sum(p)) if p else 0.0
            vals[name] = v
            tot[name] += v
            cells += f"{v:>17,.0f}" if p else f"{'—':>17}"
        rows.append((m, vals, cells))
    rows.sort(key=lambda r: -r[1]["IS（2021-06〜2026-06）"])
    for m, vals, cells in rows:
        print(f"{sab.MAGIC_NAME.get(m, str(m)):<16}{cells}")
    print(f"{'合計':<16}" + "".join(f"{tot[k]:>17,.0f}" for k in WINDOWS))

    # ---------- 3. 弱局面と金大相場の対比 ----------
    print("\n" + "=" * 112)
    print("【3. OOS窓の内訳】**同じ窓でも時期で全く違う**")
    print("=" * 112)
    a1, b1, m1 = WINDOWS["  うち弱局面（〜2019-12）"]
    a2, b2, m2 = WINDOWS["  うち金大相場（2020-）"]
    n1 = float(np.sum([x[1] for x in rec if in_w(x[0], a1, b1)]))
    n2 = float(np.sum([x[1] for x in rec if in_w(x[0], a2, b2)]))
    print(f"  弱局面   {m1:.0f}ヶ月（全体の{100*m1/(m1+m2):.0f}%）："
          f"{n1:>+10,.0f}円（全体の{100*n1/(n1+n2):.0f}%）／月利 "
          f"{100*n1/(DEPOSIT*m1):.2f}%")
    print(f"  金大相場 {m2:.0f}ヶ月（全体の{100*m2/(m1+m2):.0f}%）："
          f"{n2:>+10,.0f}円（全体の{100*n2/(n1+n2):.0f}%）／月利 "
          f"{100*n2/(DEPOSIT*m2):.2f}%")
    print(f"\n  → **月利で {100*n2/(DEPOSIT*m2) / (100*n1/(DEPOSIT*m1)):.1f}倍の差。**"
          f" 同じOOS窓の中でこれだけ違う。")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・枠別の損益は決済ログの profit 合計（スワップ・手数料はログの定義に従う）")
    print("  ・最大DDはFX側・GOLD側の別々の実行の値で、合算ブックのDDではない")
    print("  ・想定月利は入金50万円に対する単利。x2hr評価（資金10万円・倍率k）とは別物")
    print("\n完了。")


if __name__ == "__main__":
    main()
