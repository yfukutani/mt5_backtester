"""V063：取引頻度を4〜5倍にする**現実的な道筋**を、既存ログから見積もる。

【なぜこれが本命か】
V059・V061で、70%到達に必要なのは**頻度4〜5倍**と分かった。
V056の枠組みでは、天井 ＝ Φ(1取引あたりシャープ × √(3ヶ月の取引数)) なので、
**頻度は天井を上げる2つの方法のうちの1つ**（もう1つは戦略の質）。

**「枠を75個作る」は非現実的に聞こえるが、実際に何が必要かを分解する。**

【分解の観点】
現在のブックは **15枠 / 8銘柄** で月33.5件。1枠あたり月2.2件。
頻度を上げる道筋は3つある。

1. **銘柄を増やす**——同じ戦略型を別の銘柄に適用する（最も素直）
2. **時間軸を増やす**——同じ戦略を短い足に適用する（頻度は上がるがコスト比が悪化）
3. **既定OFFの枠を有効化する**——すでに実装済みで止めているもの

本スクリプトは既存ログから、**枠ごと・戦略型ごとの取引頻度**を出し、
「あと何を追加すれば4〜5倍になるか」を具体的に見積もる。

【限界】
- 追加した枠が既存と同じ質（1取引あたりシャープ）を持つ保証はない
- 銘柄を増やすと相関が上がり、分散効果は頻度ほどには増えない
- スプレッド・スワップのコストは銘柄により大きく違う
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import sleeve_time_trend as st
from sleeve_ablation import MAGIC_NAME
from fx_degradation import FAMILY

MONTHS = cc.MONTHS


def main():
    rows = st.load_full()
    months_full = MONTHS["FULL"]

    print("=" * 104)
    print("V063：取引頻度を4〜5倍にする現実的な道筋（既存ログからの分解）")
    print("=" * 104)

    by_m = defaultdict(list)
    for y, m, p in rows:
        by_m[m].append(p)
    total = sum(len(v) for v in by_m.values())
    print(f"\n現在：{len(by_m)}枠 / {total}取引 / {months_full:.0f}ヶ月 "
          f"→ 月{total/months_full:.1f}件")
    print(f"目標：月{total/months_full*4:.0f}〜{total/months_full*5:.0f}件"
          f"（4〜5倍）\n")

    print("【枠別の取引頻度】")
    print(f"{'枠':>16}{'銘柄':>9}{'型':>7}{'取引':>7}{'月あたり':>10}"
          f"{'1取引ｼｬｰﾌﾟ':>12}")
    for m in sorted(by_m, key=lambda x: -len(by_m[x])):
        a = np.array(by_m[m])
        sd = a.std(ddof=1) if len(a) > 1 else 0.0
        print(f"{MAGIC_NAME.get(m, str(m)):>16}{st.SYMBOL_OF.get(m, '?'):>9}"
              f"{FAMILY.get(m, '?'):>7}{len(a):>7}{len(a)/months_full:>10.2f}"
              f"{(a.mean()/sd if sd else 0):>12.4f}")

    print("\n【戦略型ごとの集計】")
    print(f"{'型':>8}{'枠数':>7}{'取引':>8}{'月あたり':>10}{'1枠あたり月':>13}"
          f"{'1取引ｼｬｰﾌﾟ':>12}")
    fam = defaultdict(list)
    famn = defaultdict(set)
    for y, m, p in rows:
        fam[FAMILY.get(m, '?')].append(p)
        famn[FAMILY.get(m, '?')].add(m)
    for f in sorted(fam, key=lambda x: -len(fam[x])):
        a = np.array(fam[f])
        sd = a.std(ddof=1) if len(a) > 1 else 0.0
        print(f"{f:>8}{len(famn[f]):>7}{len(a):>8}{len(a)/months_full:>10.2f}"
              f"{len(a)/months_full/len(famn[f]):>13.2f}"
              f"{(a.mean()/sd if sd else 0):>12.4f}")

    print("\n【銘柄ごとの集計】")
    print(f"{'銘柄':>10}{'枠数':>7}{'取引':>8}{'月あたり':>10}{'1取引ｼｬｰﾌﾟ':>12}")
    sym = defaultdict(list)
    symn = defaultdict(set)
    for y, m, p in rows:
        s = st.SYMBOL_OF.get(m, '?')
        sym[s].append(p)
        symn[s].add(m)
    for s in sorted(sym, key=lambda x: -len(sym[x])):
        a = np.array(sym[s])
        sd = a.std(ddof=1) if len(a) > 1 else 0.0
        print(f"{s:>10}{len(symn[s]):>7}{len(a):>8}{len(a)/months_full:>10.2f}"
              f"{(a.mean()/sd if sd else 0):>12.4f}")

    # --- 4倍にするには何が必要か ---
    print("\n" + "=" * 104)
    print("【4〜5倍にするための必要量】")
    print("=" * 104)
    cur = total / months_full
    print(f"  現在 月{cur:.1f}件 → 目標 月{cur*4:.0f}件（4倍）/ 月{cur*5:.0f}件（5倍）")
    print(f"  追加で必要な頻度: 月{cur*3:.0f}件（4倍）/ 月{cur*4:.0f}件（5倍）\n")

    print("  **道筋A：同じ型を別の銘柄へ展開する**")
    sca = len(fam.get('SCA', [])) / months_full
    n_sca = len(famn.get('SCA', set()))
    print(f"    SCA型は{n_sca}枠で月{sca:.1f}件（1枠あたり月{sca/max(n_sca,1):.1f}件）"
          f"——**最も高頻度**")
    need4 = cur * 3 / (sca / max(n_sca, 1))
    print(f"    SCA型と同じ頻度の枠を **{need4:.0f}枠** 追加すれば4倍に届く")
    print(f"    現在SCAは USDJPY/GBPJPY/GOLD の3銘柄。"
          f"主要通貨ペア全体（20〜30銘柄）へ展開すれば桁は合う")

    print("\n  **道筋B：時間軸を下げる**")
    print("    同じロジックを1つ下の足に移すと取引数は概ね2〜4倍になるが、")
    print("    1取引あたりの値幅が小さくなるため**スプレッド比が悪化し質が落ちる**。")
    print("    V056の枠組みでは、シャープが √倍率 より大きく落ちれば天井は下がる。")

    print("\n  **道筋C：既定OFFの枠を有効化する**")
    print("    PB AUDJPY は既定OFF（`MIX_EA_UM.md`）。"
          f"寄与は月{len(by_m.get(20260628, []))/months_full:.2f}件で、桁が足りない")

    print("\n" + "=" * 104)
    print("【限界】")
    print("=" * 104)
    print("  ・追加した枠が既存と同じ1取引あたりシャープを持つ保証はない")
    print("  ・銘柄を増やすと相関が上がり、分散効果は頻度ほどには増えない")
    print("  ・スプレッド・スワップのコストは銘柄により大きく違う")
    print("  ・**この見積もりは必要量を示すだけで、実現可能性は示していない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
