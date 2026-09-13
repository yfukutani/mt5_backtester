"""V075：方針A/Bを**現実的な質**の追加枠で測り直す。

【V074で分かったこと（楽観的な仮定）】
弱局面の実履歴で、取引機会を f 倍にすると——

| f | OOS 6月 | OOS 12月 | 12月破綻 | 方針A(65%) | 方針B(90%) |
|---:|---:|---:|---:|---|---|
| 1x | 36.0% | 41.9% | 40.7% | ❌ | ❌ |
| 2x | 43.0% | 64.3% | 0.4% | ❌ | ❌ |
| 3x | 47.7% | 83.3% | 0.0% | ❌ | ❌ |
| **4x** | 63.6% | **93.0%** | **0.0%** | ❌ | **✅** |
| 8x | 76.4% | 100.0% | 0.0% | ✅ | ✅ |

**方針B（12ヶ月90%）は頻度4倍で達成。破綻も0.0%。**
**方針A（6ヶ月65%）は8倍必要。**

**ただしV074は「追加枠がブック平均と同じ質を持つ」という楽観的な仮定である。**

【V066で確認済みの現実】
実際に展開できる枠（SCA型をFX銘柄へ）の質は、**ブック平均の42%**しかない。

| SCA枠 | 1取引シャープ | t値 |
|---|---:|---:|
| SCA USDJPY | 0.0416 | **1.01** |
| SCA GBPJPY | 0.0407 | **1.47** |
| SCA GOLD1 | 0.1369 | 3.02 |

**FX 2銘柄は10年かけても統計的に有意ではない。**

【本スクリプトの測定】
追加分を **SCA-FX（USDJPY/GBPJPY）の実取引から復元抽出**して同じ測定を行う。
**これが「実際に主要通貨ペアへ展開した場合」に最も近い見積もり。**

比較のため、**ブック平均から抽出した場合（V074の仮定）も併記する。**

【限界】
- 追加枠どうしの相関を無視（実際は相関があり**さらに不利**）
- 新銘柄のスプレッド・流動性・取引時間帯の違いを考慮していない
- 現在のSCA-FX 2銘柄は選ばれた結果である可能性（生存者バイアス）
- 弱局面の起点は86個。起点が重なるため独立ではない
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import dynamic_k_lag as dkl
import target_policy_gap as tpg

MULT = 2.0
QUIET_END = tpg.QUIET_END
K_GRID = tpg.K_GRID
F_GRID = [1, 2, 3, 4, 6, 8, 12, 16]
CHECK = [3, 6, 12]
SEEDS = (11, 22, 33)
SCA_FX = {20261000, 20261001}


def load_with_magic(window):
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


def expand_from(rec, pool, f, seed):
    """取引機会を f 倍にする。追加分は pool から復元抽出。"""
    if f <= 1:
        return [(a, b, c, d) for a, b, c, d, _ in rec]
    rng = np.random.default_rng(seed)
    base = [(a, b, c, d) for a, b, c, d, _ in rec]
    out = list(base)
    n, npool = len(rec), len(pool)
    for _ in range(f - 1):
        idx = rng.integers(0, npool, size=n)
        for i, j in enumerate(idx):
            ti, to = rec[i][0], rec[i][1]
            out.append((ti, to, pool[j][2], pool[j][3]))
    out.sort()
    return out


def main():
    print("=" * 112)
    print("V075：方針A/Bを現実的な質の追加枠で測り直す")
    print("=" * 112)
    print("★ 倍率2倍固定。方針A＝6ヶ月65%、方針B＝12ヶ月90%（破綻は限りなく低く）")
    print("評価は弱局面の実履歴（起点＋18暦月 ≤ 2020-01-01・86起点）\n")

    raw = {w: load_with_magic(w) for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]

    for w in ("IS", "OOS"):
        allp = np.array([x[2] for x in raw[w]])
        sca = np.array([x[2] for x in raw[w] if x[4] in SCA_FX])
        sa = float(allp.mean()) / float(allp.std(ddof=1))
        ss = float(sca.mean()) / float(sca.std(ddof=1))
        print(f"  {w}窓: 全体{len(allp)}取引（シャープ{sa:.4f}） / "
              f"SCA-FX {len(sca)}取引（シャープ{ss:.4f}）→ 質は **{ss/sa:.0%}**")
    print()

    for tag, use_sca in (("ブック平均（V074の仮定）", False),
                         ("**SCA-FX相当（現実的）**", True)):
        print("=" * 112)
        print(f"【追加枠の質：{tag}】")
        print("=" * 112)
        print(f"{'f':>4}│{'IS選択k':>9}{'IS 6月':>9}{'IS 12月':>9}"
              f"│{'OOS 3月':>9}{'OOS 6月':>9}{'OOS 12月':>10}{'12月破綻':>10}"
              f"│{'方針A':>7}{'方針B':>7}")
        hitA = hitB = None
        for f in F_GRID:
            pools = {w: ([x for x in raw[w] if x[4] in SCA_FX] if use_sca
                         else raw[w]) for w in ("IS", "OOS")}
            # kをIS窓で選ぶ（6ヶ月基準）
            best, bp = None, -1.0
            for k in K_GRID:
                vals = []
                for sd in SEEDS:
                    rc = expand_from(raw["IS"], pools["IS"], f, 3000 + sd)
                    o = tpg.evaluate_quiet(rc, k, [6], a_is, b_is)
                    vals.append(o[6][0])
                m = float(np.mean(vals))
                if m > bp:
                    best, bp = k, m
            k_sel = best
            res = {}
            for w, (st, cap) in (("IS", (a_is, b_is)), ("OOS", (a_oos, QUIET_END))):
                acc = {m: [] for m in CHECK}
                r12 = []
                for sd in SEEDS:
                    rc = expand_from(raw[w], pools[w], f, 4000 + sd)
                    o = tpg.evaluate_quiet(rc, k_sel, CHECK, st, cap)
                    for m in CHECK:
                        acc[m].append(o[m][0])
                    r12.append(o[12][1])
                res[w] = ({m: float(np.mean(acc[m])) for m in CHECK},
                          float(np.mean(r12)))
            okA = res["OOS"][0][6] >= 0.65
            okB = res["OOS"][0][12] >= 0.90
            if okA and hitA is None:
                hitA = f
            if okB and hitB is None:
                hitB = f
            print(f"{f:>3}x│{k_sel:>9}{100*res['IS'][0][6]:>8.1f}%"
                  f"{100*res['IS'][0][12]:>8.1f}%"
                  f"│{100*res['OOS'][0][3]:>8.1f}%{100*res['OOS'][0][6]:>8.1f}%"
                  f"{100*res['OOS'][0][12]:>9.1f}%{100*res['OOS'][1]:>9.1f}%"
                  f"│{'✅' if okA else '❌':>7}{'✅' if okB else '❌':>7}")
        print()
        print(f"  → 方針A（6ヶ月65%）に必要な頻度倍率: "
              f"{'達成せず' if hitA is None else f'{hitA}倍'}")
        print(f"  → 方針B（12ヶ月90%）に必要な頻度倍率: "
              f"{'達成せず' if hitB is None else f'{hitB}倍'}")
        print()

    print("=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・追加枠どうしの相関を無視（実際は相関がありさらに不利）")
    print("  ・新銘柄のスプレッド・流動性・取引時間帯の違いを考慮していない")
    print("  ・現在のSCA-FX 2銘柄は選ばれた結果である可能性（生存者バイアス）")
    print("  ・SCA-FXのt値は1.01・1.47で10年かけても統計的に有意ではない")
    print("  ・弱局面の起点は86個。起点が重なるため独立ではない")
    print("\n完了。")


if __name__ == "__main__":
    main()
