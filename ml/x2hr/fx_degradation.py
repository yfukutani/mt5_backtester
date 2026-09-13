"""V042：FX枠の直近劣化を枠別に切り分ける——**どの枠が、いつ壊れたか**。

【背景】
V040で、FX枠11枠のシャープが 2022-2023の0.1442 から 2024-2026の0.0362 へ急落し、
2025-2026の2年間では合計 **−23,265円**（シャープ −0.034）とマイナスになっていることが
分かった。**尺度不変の指標での低下なので、円建てスケールの話ではなく優位性そのものの劣化。**

**本番ポートフォリオ（MIX_EA）も同じ枠を使っているため、運用判断に直結する。**

【切り分けたいこと】
1. **全FX枠が一様に劣化したのか、特定の枠だけか**
2. 劣化した枠は**いつから**おかしくなったのか
3. 劣化は**銘柄**で説明できるのか（USDJPY/GBPJPY/EURUSD/GBPUSD/AUDJPY）、
   それとも**戦略の型**で説明できるのか（PB＝順張り / RSI＝逆張り / SCA＝日中 /
   VBO＝ブレイク / Carry＝スワップ / PairTrade＝裁定）

【限界】
期間を4つに区切るのは本記録での選択であり、事前登録した区切りではない。
枠によっては1期間あたり数取引しかなく、シャープの推定誤差は大きい。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sleeve_time_trend as st
from sleeve_ablation import MAGIC_NAME

PERIODS = [("2016-2018", 2016, 2018), ("2019-2021", 2019, 2021),
           ("2022-2023", 2022, 2023), ("2024-2026", 2024, 2026)]

# 戦略の型（magic → 型）
FAMILY = {
    20260622: "PB", 20260627: "PB", 20260628: "PB", 20260640: "PB",
    20260610: "RSI", 20260605: "RSI", 20260774: "RSI",
    20260650: "Carry", 20260680: "VBO",
    20261000: "SCA", 20261001: "SCA", 20261002: "SCA", 20261003: "SCA",
    20260710: "Crypto", 20260720: "Crypto", 20260629: "Pair",
}


def agg(rows, pred, a, b):
    v = [p for y, m, p in rows if a <= y <= b and pred(m)]
    if len(v) < 2:
        return None
    x = np.array(v)
    sd = x.std(ddof=1)
    return dict(n=len(x), mean=float(x.mean()), sd=float(sd),
                sharpe=float(x.mean() / sd) if sd else 0.0, total=float(x.sum()))


def table(title, keys, pred_of, rows, note=""):
    print(f"\n【{title}】{note}")
    head = f"{'':>16}"
    for lab, _, _ in PERIODS:
        head += f"{lab:>22}"
    print(head)
    sub = f"{'':>16}" + "".join(f"{'件':>6}{'平均円':>8}{'ｼｬｰﾌﾟ':>8}" for _ in PERIODS)
    print(sub)
    for k in keys:
        line = f"{str(k)[:16]:>16}"
        for _, a, b in PERIODS:
            r = agg(rows, pred_of(k), a, b)
            if r:
                line += f"{r['n']:>6}{r['mean']:>8.0f}{r['sharpe']:>8.3f}"
            else:
                line += f"{'—':>6}{'—':>8}{'—':>8}"
        print(line)


def main():
    rows = st.load_full()
    fx_magics = [m for m in sorted({m for _, m, _ in rows})
                 if st.SYMBOL_OF.get(m) not in st.CRYPTO | {"GOLD"}]

    print("=" * 118)
    print("V042：FX枠の直近劣化を枠別に切り分ける")
    print("=" * 118)

    # --- 枠別 ---
    table("FX枠 個別", fx_magics, lambda m: (lambda x, mm=m: x == mm), rows,
          note="（magic単位）")
    print("  ※ 枠名: " + ", ".join(f"{m}={MAGIC_NAME.get(m, '?')}" for m in fx_magics))

    # --- 銘柄別 ---
    fx_syms = sorted({st.SYMBOL_OF.get(m) for m in fx_magics} - {None})
    table("銘柄別（FX）", fx_syms,
          lambda s: (lambda m, ss=s: st.SYMBOL_OF.get(m) == ss), rows)

    # --- 戦略の型別（FXのみ） ---
    fams = sorted({FAMILY.get(m, "?") for m in fx_magics})
    table("戦略の型別（FXのみ）", fams,
          lambda f: (lambda m, ff=f: FAMILY.get(m) == ff
                     and st.SYMBOL_OF.get(m) not in st.CRYPTO | {"GOLD"}), rows)

    # --- 直近2年で誰が沈めたか ---
    print("\n" + "=" * 118)
    print("【直近2年（2025-2026）の寄与ランキング（FX枠）】")
    print("=" * 118)
    print(f"{'枠':>16}{'銘柄':>9}{'型':>7}{'取引':>7}{'平均円':>9}"
          f"{'ｼｬｰﾌﾟ':>8}{'合計円':>11}")
    contrib = []
    for m in fx_magics:
        r = agg(rows, (lambda x, mm=m: x == mm), 2025, 2026)
        if r:
            contrib.append((r["total"], m, r))
    for tot, m, r in sorted(contrib):
        print(f"{MAGIC_NAME.get(m, str(m)):>16}{st.SYMBOL_OF.get(m, '?'):>9}"
              f"{FAMILY.get(m, '?'):>7}{r['n']:>7}{r['mean']:>9.0f}"
              f"{r['sharpe']:>8.3f}{tot:>11.0f}")
    if contrib:
        s = sum(t for t, _, _ in contrib)
        neg = sum(t for t, _, _ in contrib if t < 0)
        print(f"{'合計':>16}{'':>9}{'':>7}{'':>7}{'':>9}{'':>8}{s:>11.0f}")
        print(f"  マイナス寄与の合計: {neg:,.0f}円 / "
              f"プラス寄与の合計: {s-neg:,.0f}円")

    print("\n" + "=" * 118)
    print("【読み方】")
    print("=" * 118)
    print("  ・全FX枠が一様に落ちているなら、相場環境（ボラ低下など）の可能性が高い")
    print("  ・特定の型（PB＝順張り など）だけが落ちているなら、その型が効かない局面")
    print("  ・特定の銘柄だけなら、その銘柄の性質変化")
    print("  ・1〜2枠が大きくマイナスを出しているだけなら、その枠の停止で解決しうる")
    print("\n完了。")


if __name__ == "__main__":
    main()
