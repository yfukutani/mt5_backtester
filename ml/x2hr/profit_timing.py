"""V098：**弱局面の利益はいつ出ていたか**（2026-09-13）。

【V097で分かったこと】
取引列の作り方を変えるだけで到達率が大きく変わる。

| 期限 | 実履歴 | 日ブロック入替 | 取引シャッフル | 正規化 |
|---|---:|---:|---:|---:|
| 6ヶ月 | **50.7%** | 65.1% | 70.1% | 82.3% |
| 12ヶ月 | **33.0%** | **70.4%** | 67.3% | 81.2% |

**12ヶ月は日ブロックを入れ替えるだけで +37.3pt 改善する。**

【ところが日次損益の分散比は1付近】

| 窓 | 2日 | 5日 | 10日 | 20日 | 60日 |
|---|---:|---:|---:|---:|---:|
| OOS 弱局面 | 1.05 | 1.00 | 0.95 | **0.87** | **0.96** |

**系列相関はない。** それなのに順序を変えると大きく変わる。

【したがって疑うべきは「非定常性」＝利益の出る時期が偏っていること】
日ブロック入替は、系列相関だけでなく**利益がいつ出るか**も変える。
利益が特定の時期に固まっていれば、**その時期を含まない起点は届かない。**

**これは実装の不備ではなく、相場そのものの性質である。**
サイジングをどう工夫しても、期限より長い不毛な期間があれば届かない。

本スクリプトは、弱局面の月次損益を並べて**利益がどこに固まっているか**を確認する。

【限界】
- 月次損益は k=1・最小ロット制約なしの素の値。実際の経路とは違う
- 弱局面は38ヶ月。月次38点しかない
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import target_policy_gap as tpg

QUIET_END = tpg.QUIET_END


def monthly(rec, a, b):
    out = {}
    for t, _, prof, _ in rec:
        d = datetime.fromtimestamp(t, tz=timezone.utc)
        if not (a <= d < b):
            continue
        key = (d.year, d.month)
        cur = out.setdefault(key, [0.0, 0])
        cur[0] += prof
        cur[1] += 1
    return out


def main():
    print("=" * 100)
    print("V098：弱局面の利益はいつ出ていたか")
    print("=" * 100)
    print("★ V097で、日ブロックを入れ替えるだけで12ヶ月到達が +37.3pt 改善した。")
    print("  しかし日次分散比は1付近＝**系列相関はない**。")
    print("  → 疑うべきは**非定常性（利益の出る時期の偏り）**。\n")

    data = {w: co.load_events(w)[0] for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    for name, rec, a, b in (("OOS 弱局面（〜2020-01）", data["OOS"], a_oos, QUIET_END),
                            ("IS窓", data["IS"], a_is, b_is)):
        m = monthly(rec, a, b)
        keys = sorted(m)
        vals = np.array([m[k][0] for k in keys])
        print("=" * 100)
        print(f"【{name}】{len(keys)}ヶ月・合計 {vals.sum():+,.0f}円（k=1・素の損益）")
        print("=" * 100)
        # 月次の並び
        line = ""
        for i, k in enumerate(keys):
            v = m[k][0]
            mark = "+" if v > 0 else ("-" if v < 0 else "0")
            line += mark
            if (i + 1) % 12 == 0:
                line += " "
        print(f"  月次の符号: {line}")
        pos = int((vals > 0).sum())
        print(f"  プラスの月 {pos}/{len(vals)} ({100*pos/len(vals):.0f}%)"
              f" / 月次中央 {np.median(vals):+,.0f}円"
              f" / 月次平均 {vals.mean():+,.0f}円")

        # 利益の集中度
        order = np.argsort(-vals)
        cum = np.cumsum(vals[order])
        total = vals.sum()
        if total > 0:
            for frac in (0.25, 0.5, 0.8):
                need = int(np.searchsorted(cum, total * frac) + 1)
                print(f"  純益の{100*frac:.0f}%は **上位{need}ヶ月"
                      f"（全体の{100*need/len(vals):.0f}%）** で稼いでいる")

        # 連続する不毛期間
        best_bad, cur, start_bad = 0, 0, None
        worst = None
        run_sum = 0.0
        for i, k in enumerate(keys):
            if m[k][0] <= 0:
                if cur == 0:
                    start_bad = k
                    run_sum = 0.0
                cur += 1
                run_sum += m[k][0]
                if cur > best_bad:
                    best_bad, worst = cur, (start_bad, k, run_sum)
            else:
                cur = 0
        if worst:
            print(f"  **最長の連続マイナス期間: {best_bad}ヶ月**"
                  f"（{worst[0][0]}-{worst[0][1]:02d} 〜 {worst[1][0]}-{worst[1][1]:02d}"
                  f"・合計 {worst[2]:+,.0f}円）")

        # 6ヶ月・12ヶ月の移動合計
        for w in (6, 12):
            if len(vals) < w:
                continue
            roll = np.array([vals[i:i + w].sum() for i in range(len(vals) - w + 1)])
            neg = int((roll <= 0).sum())
            print(f"  {w}ヶ月の移動合計: 中央 {np.median(roll):+,.0f}円 / "
                  f"最小 {roll.min():+,.0f}円 / "
                  f"**マイナスの窓 {neg}/{len(roll)} ({100*neg/len(roll):.0f}%)**")
        print()

    print("=" * 100)
    print("【意味】")
    print("=" * 100)
    print("  ・利益が特定の月に固まっているなら、**その月を含まない起点は届かない**")
    print("  ・これは実装の不備ではなく**相場そのものの性質**である")
    print("  ・サイジングをどう工夫しても、期限より長い不毛な期間があれば届かない")
    print("  ・**改善するには、時期の異なる収益源を足すしかない**")
    print("    （銘柄を増やす＝取引数を増やす、という結論と一致する）")

    print("\n" + "=" * 100)
    print("【限界】")
    print("=" * 100)
    print("  ・月次損益は k=1・最小ロット制約なしの素の値。実際の経路とは違う")
    print("  ・弱局面は38ヶ月。月次38点しかない")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
