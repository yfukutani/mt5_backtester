"""V081：**保有時間と損益の関係**（簡易検証・2026-09-13）。

【この検証の位置づけ】
`CLAUDE.md`「戦略検証の進め方」の**段階2（簡易検証）**。
ここで測るのは「効果が出そうか」だけであり、**採用の根拠にはしない。**

【対象の案】
- Claude C12：SCA 建玉後 N バー以内に進展がなければ退出（時間切れ）
- Codex 15：◎ 進展がない建玉の時間切れ退出
- Codex 14：◎ ブレイクの根拠が崩れた時点で退出

【なぜ出口の改善は入口フィルタより筋が良いか（V077の教訓）】
入口で割合 q だけ残すと期限シャープは `S_q·√(q·N)` になり、
`S_q/S > 1/√q` を超えないと損になる（半分捨てるなら質が41%良くならないと損）。
**出口の改善は取引数を減らさない。** 1取引シャープの改善がそのまま H の改善になる。

【この簡易検証でできること・できないこと】

できる：
- 保有時間の長短で、決済損益の**平均・分散・シャープ**がどう違うか
- 「長く持った建玉は悪い」なら、時間切れ退出に見込みがある

**できない：**
- 実際に途中で切った場合の損益は分からない（**その時点の価格を持っていない**）
- 決済ログには最終損益しかない。**含み益・含み損の経路は記録されていない**
- したがって**これは相関の観察であって、介入の効果ではない**
  （長く持つ建玉が悪いのは「悪くなったから長く持った」可能性がある）

**→ 見込みの有無を見るだけ。効果の測定はMT5バックテストでしかできない。**

【限界】
- 保有時間と損益の相関は因果ではない（上記のとおり）
- 枠ごとに設計が違うので、枠をまたいだ集計には意味が薄い。**枠別に出す**
- IS窓・OOS窓・弱局面の3つで出して、一貫しているかを見る
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

QUIET_END = datetime(2020, 1, 1, tzinfo=timezone.utc)
MIN_N = 40


def load(window):
    """(t_in, t_out, profit, volume, magic) を返す。"""
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            if m == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"]), m))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol, m in rows:
            if entry == 0:
                opened[pid] = (t, vol, m)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((o[0], t, profit, o[1], o[2]))
    rec.sort()
    return rec


def sharpe(p):
    a = np.asarray(p, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0
    return float(a.mean() / a.std(ddof=1))


def tval(p):
    a = np.asarray(p, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0
    return float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))


def main():
    print("=" * 112)
    print("V081：保有時間と損益の関係（簡易検証）")
    print("=" * 112)
    print("★ `CLAUDE.md` の段階2（簡易検証）。**採用の根拠にはしない。**")
    print("  対象：C12 / Codex15（進展がない建玉の時間切れ退出）、Codex14（根拠崩壊で退出）\n")
    print("> [!warning] **これは相関の観察であって、介入の効果ではない。**")
    print("> 決済ログには最終損益しかなく、途中で切った場合の損益は分からない。")
    print("> 『長く持った建玉が悪い』のは『悪くなったから長く持った』可能性がある。")
    print("> **効果の測定はMT5バックテストでしかできない。**\n")

    data = {}
    for w in ("IS", "OOS"):
        data[w] = load(w)
    data["OOS弱局面"] = [x for x in data["OOS"]
                       if datetime.fromtimestamp(x[0], tz=timezone.utc) < QUIET_END]

    # ---------- 1. 全体：保有時間の分位別 ----------
    print("=" * 112)
    print("【1. 保有時間の分位別（ブック全体）】")
    print("=" * 112)
    for w, rec in data.items():
        hold = np.array([(x[1] - x[0]) / 3600.0 for x in rec])
        prof = np.array([x[2] for x in rec])
        qs = np.quantile(hold, [0.2, 0.4, 0.6, 0.8])
        print(f"\n--- {w}（{len(rec)}建玉・1取引シャープ {sharpe(prof):.4f}）---")
        print(f"{'保有時間の層':<22}{'件数':>7}{'中央保有(h)':>12}"
              f"{'平均損益':>11}{'1取引S':>9}{'t値':>8}")
        edges = [-1] + list(qs) + [1e18]
        labels = ["最短20%", "20-40%", "40-60%", "60-80%", "最長20%"]
        for i, lab in enumerate(labels):
            sel = (hold > edges[i]) & (hold <= edges[i + 1])
            if sel.sum() < MIN_N:
                continue
            print(f"{lab:<22}{int(sel.sum()):>7}{np.median(hold[sel]):>12.1f}"
                  f"{prof[sel].mean():>11.2f}{sharpe(prof[sel]):>9.4f}"
                  f"{tval(prof[sel]):>8.2f}")

    # ---------- 2. 枠別：長短の差 ----------
    print("\n" + "=" * 112)
    print("【2. 枠別：保有時間 上位半分 vs 下位半分】**枠ごとに設計が違うので枠別に見る**")
    print("=" * 112)
    magics = sorted({x[4] for x in data["IS"]} | {x[4] for x in data["OOS"]})
    print(f"{'magic':>10}" + "".join(f"{w+' 短S':>11}{w+' 長S':>11}{'差':>9}"
                                     for w in ("IS", "OOS")))
    promising = []
    for mg in magics:
        cells, ok = "", True
        diffs = {}
        for w in ("IS", "OOS"):
            sub = [x for x in data[w] if x[4] == mg]
            if len(sub) < 2 * MIN_N:
                ok = False
                break
            hold = np.array([(x[1] - x[0]) for x in sub])
            prof = np.array([x[2] for x in sub])
            med = np.median(hold)
            s_short = sharpe(prof[hold <= med])
            s_long = sharpe(prof[hold > med])
            diffs[w] = s_short - s_long
            cells += f"{s_short:>11.4f}{s_long:>11.4f}{s_short-s_long:>9.4f}"
        if not ok:
            continue
        print(f"{mg:>10}{cells}")
        if diffs["IS"] > 0.02 and diffs["OOS"] > 0.02:
            promising.append((mg, diffs["IS"], diffs["OOS"]))

    print("\n  → **IS・OOSの両方で「短い建玉のほうが良い」枠**"
          "（時間切れ退出に見込みがある候補）：")
    if not promising:
        print("    **なし。** 時間切れ退出は、この観察からは見込みが立たない。")
    for mg, a, b in promising:
        print(f"    magic {mg}：IS +{a:.4f} / OOS +{b:.4f}")

    # ---------- 3. 損益の符号と保有時間 ----------
    print("\n" + "=" * 112)
    print("【3. 勝ち建玉と負け建玉の保有時間】**負けのほうが長いなら時間切れに意味がある**")
    print("=" * 112)
    print(f"{'窓':<12}{'勝ち件数':>9}{'勝ち中央(h)':>13}"
          f"{'負け件数':>9}{'負け中央(h)':>13}{'負け/勝ち':>11}")
    for w, rec in data.items():
        hold = np.array([(x[1] - x[0]) / 3600.0 for x in rec])
        prof = np.array([x[2] for x in rec])
        win, los = hold[prof > 0], hold[prof < 0]
        if len(win) < MIN_N or len(los) < MIN_N:
            continue
        mw, ml = float(np.median(win)), float(np.median(los))
        print(f"{w:<12}{len(win):>9}{mw:>13.1f}{len(los):>9}{ml:>13.1f}"
              f"{(ml/mw if mw > 0 else float('nan')):>11.2f}")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・保有時間と損益の相関は因果ではない（悪くなったから長く持った可能性）")
    print("  ・途中で切った場合の損益はログから復元できない")
    print("  ・**段階2の簡易検証である。採用するならMT5バックテストが必要**")
    print("\n完了。")


if __name__ == "__main__":
    main()
