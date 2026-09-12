"""V046：**倍率kを下げることが物理的に可能か**を確認する（課題C12・Codex指摘）。

【問題】
V043・V044では「倍率k=0.25〜0.5なら破綻確率0.0%で到達率100%」という結果が出た。
しかし `MIX_EA.mq5` の `Clamp()` は次のとおりである。

```
double Clamp(string sym, double lot)
{
   double mn=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double st=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   if(st>0) lot=MathFloor(lot/st)*st;
   return MathMax(mn,MathMin(mx,lot));      // ← 最小ロット未満は切り上げられる
}
```

**すでに最小ロットで発注している枠にk=0.25を掛けても、実際のロットは変わらない。**
つまり**k<1は、その枠については実現しない。**

シミュレーション（`dynamic_k_lag.py` など）は損益を連続的にk倍しているため、
**この制約を一切考慮していない。**

【本スクリプトがすること】
dealログの `volume` の分布を調べ、

1. 最小ロット（0.01）で発注されている取引が全体の何%か
2. 枠別・銘柄別の内訳
3. 倍率kを掛けたときに**実際に適用される実効倍率**はいくつになるか

を出す。実効倍率が1.0から動かないなら、**V043・V044の低いkの結果は実現不可能**である。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl
from sleeve_ablation import MAGIC_NAME
from sleeve_time_trend import SYMBOL_OF

MIN_LOT = 0.01      # XM/OANDAとも FX・GOLD は 0.01 が最小（暗号は銘柄により異なる）
STEP = 0.01
K_GRID = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]


def load_volumes(window):
    """入口dealの (magic, volume) を返す。"""
    fx, gold = dkl.resolve_runs()
    out = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["entry"]) != 0:      # IN のみ
                continue
            m = int(r["magic"])
            if m == 0:
                continue
            out.append((m, float(r["volume"])))
    return out


def effective_k(vols, k):
    """kを掛けてClampした後の『実効倍率』＝ 実際のロット合計 ÷ 元のロット合計。"""
    orig = np.array([v for _, v in vols], dtype=float)
    scaled = orig * k
    stepped = np.floor(scaled / STEP + 1e-9) * STEP
    clamped = np.maximum(MIN_LOT, stepped)
    return float(clamped.sum() / orig.sum()), float((orig <= MIN_LOT + 1e-9).mean())


def main():
    print("=" * 104)
    print("V046：倍率kを下げることが物理的に可能か（課題C12）")
    print("=" * 104)
    print("MIX_EA.mq5 の Clamp() は最小ロット未満を **MathMax(mn, ...) で切り上げる**。")
    print("すでに最小ロットの枠にk<1を掛けても、実際のロットは変わらない。\n")

    for window in ("IS", "OOS"):
        vols = load_volumes(window)
        if not vols:
            continue
        arr = np.array([v for _, v in vols])
        print("=" * 104)
        print(f"【{window}窓】入口deal {len(vols)}件 / 総ロット {arr.sum():.2f}")
        print("=" * 104)
        at_min = float((arr <= MIN_LOT + 1e-9).mean())
        print(f"  最小ロット(0.01)で発注されている取引: {100*at_min:.1f}%")
        print(f"  ロットの分位: 中央値 {np.median(arr):.3f} / "
              f"75%点 {np.percentile(arr,75):.3f} / 90%点 {np.percentile(arr,90):.3f} / "
              f"最大 {arr.max():.3f}")

        print("\n  【枠別】")
        print(f"{'枠':>16}{'銘柄':>9}{'件数':>7}{'中央ロット':>11}"
              f"{'最小ロット率':>13}{'総ロット':>10}")
        by = defaultdict(list)
        for m, v in vols:
            by[m].append(v)
        for m in sorted(by, key=lambda x: -sum(by[x])):
            a = np.array(by[m])
            print(f"{MAGIC_NAME.get(m, str(m)):>16}{SYMBOL_OF.get(m, '?'):>9}"
                  f"{len(a):>7}{np.median(a):>11.3f}"
                  f"{100*float((a <= MIN_LOT+1e-9).mean()):>12.1f}%{a.sum():>10.2f}")

        print(f"\n  【倍率kを掛けたときの実効倍率】"
              f"（実際のロット合計 ÷ 元のロット合計）")
        print(f"{'指定k':>8}{'実効倍率':>11}{'乖離':>10}{'判定':>24}")
        for k in K_GRID:
            eff, _ = effective_k(vols, k)
            gap = eff / k
            if gap > 1.5:
                v = "❌ 指定kが実現しない"
            elif gap > 1.1:
                v = "⚠️ 一部の枠で切り上げ"
            else:
                v = "✅ ほぼ指定どおり"
            print(f"{k:>8}{eff:>11.3f}{gap:>9.2f}x{v:>24}")
        print()

    print("=" * 104)
    print("【読み方】")
    print("=" * 104)
    print("  ・実効倍率が指定kを大きく上回るなら、V043・V044の低いkの結果は実現不可能")
    print("  ・その場合、実務上とれる最小のkは『実効倍率が指定kに一致する下限』になる")
    print("  ・資金を増やせば同じkでもロットが最小を上回るので制約は緩む")
    print("    （本測定は初期資金30,000円・ロット固定の現行設定を前提にしている）")
    print("\n完了。")


if __name__ == "__main__":
    main()
