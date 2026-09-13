"""V094：**段階3（MT5バックテスト）の集計**（2026-09-13）。

`CLAUDE.md`「報告に必ず含める数値」に従い、**損益・想定月利・最大DD**を出す。
最大DDは**2種類**出す。

| 指標 | 出どころ | 意味 |
|---|---|---|
| MT5の最大相対DD% | テスターのsummary | **残高ベース**（確定損益） |
| **EAの最大DD%** | `MIX_EA_X2HR` が毎ティック計算 | **含み損益込みのequityベース** |

**簡易検証（V088）で出せたのは前者に相当するものだけ。**
**後者こそが段階3をやる理由である。**

【この集計で答えること】
1. 比例方策とHJB期限意識で、到達数・損益・DDがどう違うか
2. **含み損込みのDDが、確定損益ベースよりどれだけ深いか**
3. 簡易検証（V086）の向きが保たれているか

【限界】
- 6ヶ月6本・12ヶ月3本しかない。**到達率の精密な推定はできない**
- 同じ弱局面を再度使っている。**新しいOOSではない**
- XM端末・XM銘柄。本番ブローカーが違えば結果も違う
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results.csv"
CAPITAL = 100000.0


def f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def main():
    if not RESULTS.exists():
        print(f"結果がありません: {RESULTS}")
        return
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    print("=" * 118)
    print("V094：段階3（MT5バックテスト）の集計")
    print("=" * 118)
    print("★ `CLAUDE.md`「採用の最終判断は必ずMT5バックテストで行う」の実施結果。")
    print("  資金10万円・目標2倍固定・破綻ライン10%・15枠フルブック・every_tick")
    print("  起点は**成績を見ずに固定**した弱局面の非重複窓。\n")

    # ---------- 個別 ----------
    print("=" * 118)
    print("【1. 実行ごとの結果】")
    print("=" * 118)
    print(f"{'期限':>5}{'起点':>12}{'方策':>7}{'終了':>10}{'期末資金':>11}"
          f"{'損益':>11}{'月利':>9}{'確定DD%':>9}{'**含み込みDD%**':>16}{'取引':>6}")
    for r in rows:
        mo = int(r["months"])
        eq = f(r.get("end_equity"))
        net = f(r.get("net"), 0.0)
        if eq is None:
            eq = CAPITAL + (net or 0.0)
        mret = (100.0 * ((max(eq, 1.0) / CAPITAL) ** (1.0 / mo) - 1.0)
                if eq and eq > 0 else -100.0)
        mode = {"1": "比例", "2": "HJB"}.get(r["mode"], r["mode"])
        print(f"{mo:>4}月{r['origin']:>12}{mode:>7}{r.get('why',''):>10}"
              f"{eq:>11,.0f}{net:>11,.0f}{mret:>8.2f}%"
              f"{f(r.get('dd_pct'), 0.0):>8.1f}%"
              f"{f(r.get('ea_max_dd_pct'), 0.0):>15.1f}%"
              f"{f(r.get('trades'), 0.0):>6.0f}")

    # ---------- まとめ ----------
    print("\n" + "=" * 118)
    print("【2. 方策ごとのまとめ】**損益・想定月利・最大DDを必ず併記（プロジェクトルール）**")
    print("=" * 118)
    print(f"{'期限':>5}{'方策':>7}{'本数':>6}{'到達':>7}{'破綻':>7}"
          f"│{'損益 中央':>11}{'損益 平均':>11}{'損益 最悪':>11}"
          f"│{'月利 中央':>10}{'月利 平均':>10}"
          f"│{'確定DD 中央':>12}{'**含み込みDD 中央**':>20}{'含み込みDD 最悪':>17}")
    for mo in sorted({int(r["months"]) for r in rows}):
        for mode in ("1", "2"):
            sel = [r for r in rows
                   if int(r["months"]) == mo and r["mode"] == str(mode)]
            if not sel:
                continue
            eqs, nets, mrets, dd1, dd2 = [], [], [], [], []
            reach = ruin = 0
            for r in sel:
                net = f(r.get("net"), 0.0) or 0.0
                eq = f(r.get("end_equity")) or (CAPITAL + net)
                eqs.append(eq)
                nets.append(net)
                mrets.append(100.0 * ((max(eq, 1.0) / CAPITAL) ** (1.0 / mo) - 1.0)
                             if eq > 0 else -100.0)
                dd1.append(f(r.get("dd_pct"), 0.0) or 0.0)
                dd2.append(f(r.get("ea_max_dd_pct"), 0.0) or 0.0)
                if r.get("why") == "REACH":
                    reach += 1
                if r.get("why") == "RUIN":
                    ruin += 1
            n = len(sel)
            lab = {"1": "比例", "2": "**HJB**"}[mode]
            print(f"{mo:>4}月{lab:>7}{n:>6}{100*reach/n:>6.0f}%{100*ruin/n:>6.0f}%"
                  f"│{np.median(nets):>11,.0f}{np.mean(nets):>11,.0f}"
                  f"{min(nets):>11,.0f}"
                  f"│{np.median(mrets):>9.2f}%{np.mean(mrets):>9.2f}%"
                  f"│{np.median(dd1):>11.1f}%{np.median(dd2):>19.1f}%"
                  f"{max(dd2):>16.1f}%")

    # ---------- 含み損の寄与 ----------
    print("\n" + "=" * 118)
    print("【3. 含み損の寄与】**簡易検証では見えなかった部分**")
    print("=" * 118)
    d1 = [f(r.get("dd_pct"), 0.0) or 0.0 for r in rows]
    d2 = [f(r.get("ea_max_dd_pct"), 0.0) or 0.0 for r in rows]
    gaps = [b - a for a, b in zip(d1, d2)]
    print(f"  確定損益ベースのDD 中央 {np.median(d1):.1f}% / 最悪 {max(d1):.1f}%")
    print(f"  **含み損込みのDD  中央 {np.median(d2):.1f}% / 最悪 {max(d2):.1f}%**")
    print(f"  **差 中央 {np.median(gaps):+.1f}pt / 最大 {max(gaps):+.1f}pt**")
    print("\n  → 簡易検証（V088）が出せたのは前者に相当するものだけ。")
    print("    **実際のDDはこれより深い**という但し書きが、数値で裏づけられたか確認する。")

    print("\n" + "=" * 118)
    print("【限界】")
    print("=" * 118)
    print("  ・6ヶ月6本・12ヶ月3本しかない。**到達率の精密な推定はできない**")
    print("  ・同じ弱局面を再度使っている。**新しいOOSではない**")
    print("  ・XM端末・XM銘柄。本番ブローカーが違えば結果も違う")
    print("  ・最小ロットの床により、リスクサイジング3枠は簡易検証とロットがずれる")
    print("\n完了。")


if __name__ == "__main__":
    main()
