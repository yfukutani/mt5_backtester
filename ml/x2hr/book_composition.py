"""V041：新たな軸——**ブックの構成そのものを変える**（事前登録した4ブックを全て報告）。

【動機】
V040で、ブックの収益が**GOLD枠に集中**していることが分かった。
全期間10年でGOLD枠がブック純益の56%（593,322円 / 1,055,149円）を占め、
直近2年（2025-2026）ではFX枠11枠が合計 **−23,265円**（シャープ −0.034）なのに対し、
GOLD枠3枠は **+443,692円**（シャープ +0.286）。

到達確率の観点では、これは**相反する2つの効果**を生む。

- **有利**：期待値の薄い枠を外せばブックの m/s²（≒シャープの二乗）が上がり、
  同じ破綻ラインでより高い到達確率が得られる
- **不利**：枠を外すと取引頻度が下がり、期限内の試行回数Hが減る。
  **V030で、到達確率はkよりHに強く反応することが分かっている**
  （OOS・6ヶ月でHを±30%振ると23.0pt動く）

どちらが勝つかは測らないと分からない。

【V031の失敗を繰り返さないための設計】
V031（枠の取捨選択）は15枠の部分集合を貪欲探索し、IS前半で4取引しかない枠を選んで
しまい、IS前半+6.68pt → OOS−9.10pt と反転した。**探索自由度が大きすぎた。**

本検証は**探索をしない。** 銘柄クラスで決まる**構造的に意味のある4ブックを事前に固定し、
4つとも報告する。** 「一番良かったものを報告する」ことはしない。

| ブック | 内容 | 事前に予想される性質 |
|---|---|---|
| **全枠** | 現行15枠 | 基準 |
| **FXのみ** | GOLD・暗号を除く11枠 | 頻度は高いが直近は期待値マイナス |
| **GOLDのみ** | PB GOLD・SCA GOLD1・SCA GOLD2 | 期待値は高いが頻度が1/5以下 |
| **GOLD＋暗号** | 上記＋ETH・BTC | GOLDのみより少し頻度が上がる |

【手続き（V036と同一・OOSを見て選び直さない）】
ブックごとに、IS窓で60候補（定数k・A・B・C）を総当たりし3シード平均でp_hit最大を選ぶ。
そのkと方策をOOS窓へ適用する。**期限Hは各ブック自身のIS頻度から決める**
（運用開始時に利用可能な情報）。IS窓の結果も必ず併記する。

【⚠️ この測定の限界（事前に明記する）】
- **ブックの分け方（銘柄クラス）を決める際、私は既にV040でGOLDが強いことを見ている。**
  「GOLDのみ」を候補に入れた動機はそこにある。V038でCodexが指摘した
  「OOSから設計へのフィードバック」と同じ構造が、弱い形で存在する
- ただし**4ブックすべてを報告する**ことで、「良かったものを選ぶ」余地は消している
- 銘柄クラスという分け方は、データではなく**商品の性質**から決まるものであり、
  V031の貪欲探索（32,767通り）とは自由度が桁違いに小さい
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl
from sleeve_time_trend import SYMBOL_OF, CRYPTO

N_PATHS = 10000
SEEDS = (101, 202, 303)
TARGET = 0.85
MONTHS = cc.MONTHS
CONST_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
DEADLINES = (2.0, 6.0, 12.0, 18.0, 24.0)

BOOKS = {
    "全枠": lambda m: True,
    "FXのみ": lambda m: SYMBOL_OF.get(m) not in CRYPTO | {"GOLD"},
    "GOLDのみ": lambda m: SYMBOL_OF.get(m) == "GOLD",
    "GOLD＋暗号": lambda m: SYMBOL_OF.get(m) in CRYPTO | {"GOLD"},
}


def candidates(s_):
    out = [("const", (k,), dk.policy_constant(k)) for k in CONST_GRID]
    for k0 in CONST_GRID:
        for a in (0.5, 1.0, 2.0):
            out.append(("A", (k0, a), dk.policy_A(k0, a)))
    for k0 in CONST_GRID:
        out.append(("B", (k0,), dk.policy_B(k0)))
    for c in CONST_GRID:
        out.append(("C", (c,), dk.policy_C(c, s_)))
    return out


def load_window(window):
    """窓の (profit, lag, magic) を返す（dynamic_k_lag と同じ復元規則＋magic）。"""
    fx, gold = dkl.resolve_runs()
    import bisect
    out_p, out_l, out_m = [], [], []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        opened = {}
        rec = []
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), int(r["magic"])))
        rows.sort()
        for t, entry, pid, profit, magic in rows:
            if entry == 0:
                opened[pid] = (t, magic)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0:
                    continue
                rec.append((t, profit, o[0], o[1] if o[1] else magic))
        rec.sort()
        t_out = [x[0] for x in rec]
        for i, (to, p, ti, mg) in enumerate(rec):
            out_p.append((to, p, max(0, i - bisect.bisect_left(t_out, ti)), mg))
    out_p.sort()
    return (np.array([x[1] for x in out_p], dtype=float),
            np.array([x[2] for x in out_p], dtype=np.int32),
            np.array([x[3] for x in out_p], dtype=np.int64))


def subset(pr, lg, mg, pred):
    m = np.array([pred(int(x)) for x in mg])
    return pr[m], lg[m], int(m.sum())


def main():
    pr_is, lg_is, mg_is = load_window("IS")
    pr_o, lg_o, mg_o = load_window("OOS")

    print("=" * 118)
    print("V041：ブックの構成そのものを変える（事前登録した4ブックを全て報告）")
    print("=" * 118)
    print("手続き: IS窓で60候補を総当たり→3シード平均でp_hit最大を選択→OOS窓へ適用")
    print("        期限Hは各ブック自身のIS頻度から決める。OOSを見て選び直していない")
    print("⚠️ 4ブックすべてを報告する。良かったものだけを選ばない\n")

    print("【各ブックの基礎統計】")
    print(f"{'ブック':>12}{'IS取引':>8}{'IS平均円':>10}{'ISシャープ':>12}{'IS月頻度':>10}"
          f"│{'OOS取引':>9}{'OOS平均円':>11}{'OOSシャープ':>13}{'OOS月頻度':>11}")
    stats = {}
    for name, pred in BOOKS.items():
        p_i, l_i, n_i = subset(pr_is, lg_is, mg_is, pred)
        p_o, l_o, n_o = subset(pr_o, lg_o, mg_o, pred)
        si = p_i.std(ddof=1)
        so = p_o.std(ddof=1)
        stats[name] = (p_i, l_i, n_i, p_o, l_o, n_o)
        print(f"{name:>12}{n_i:>8}{p_i.mean():>10.1f}{p_i.mean()/si:>12.4f}"
              f"{n_i/MONTHS['IS']:>10.1f}│{n_o:>9}{p_o.mean():>11.1f}"
              f"{p_o.mean()/so:>13.4f}{n_o/MONTHS['OOS']:>11.1f}")

    for dl in DEADLINES:
        print("\n" + "=" * 118)
        print(f"【期限 {dl:g}ヶ月相当】")
        print("=" * 118)
        print(f"{'ブック':>12}{'H':>6}{'IS選択方策':>16}"
              f"{'IS到達':>9}{'IS破綻':>9}│{'OOS到達':>9}{'OOS破綻':>9}"
              f"{'OOS期限切れ':>12}{'R3':>7}")
        for name in BOOKS:
            p_i, l_i, n_i, p_o, l_o, n_o = stats[name]
            if n_i < 60 or n_o < 60:
                print(f"{name:>12}  取引数が足りない（IS{n_i} OOS{n_o}）")
                continue
            s_i = float(p_i.std(ddof=1)) / cc.CAPITAL
            H = max(5, int(round(n_i / MONTHS["IS"] * dl)))
            cands = candidates(s_i)
            fnmap = {(f, pp): fn for f, pp, fn in cands}
            # --- IS選択 ---
            best, bp = None, -1.0
            is_res = {}
            for fam, prm, fn in cands:
                hs, rs = [], []
                for sd in SEEDS:
                    pa, la = dkl.generate_paths_lag(p_i, l_i, H, N_PATHS,
                                                    seed=950000 + int(dl * 100) + sd)
                    r = dkl.run_policy_lag(pa, la, fn, entry_sizing=True)
                    hs.append(r["p_hit"]); rs.append(r["p_ruin"])
                mh = float(np.mean(hs))
                is_res[(fam, prm)] = (mh, float(np.mean(rs)))
                if mh > bp:
                    best, bp = (fam, prm), mh
            is_hit, is_ruin = is_res[best]
            # --- OOS適用 ---
            hs, rs, es = [], [], []
            for sd in SEEDS:
                pa, la = dkl.generate_paths_lag(p_o, l_o, H, N_PATHS,
                                                seed=960000 + int(dl * 100) + sd)
                r = dkl.run_policy_lag(pa, la, fnmap[best], entry_sizing=True)
                hs.append(r["p_hit"]); rs.append(r["p_ruin"]); es.append(r["p_exp"])
            oh, orr, oe = float(np.mean(hs)), float(np.mean(rs)), float(np.mean(es))
            lab = (f"定数k={best[1][0]}" if best[0] == "const"
                   else f"{best[0]}{best[1]}")
            print(f"{name:>12}{H:>6}{lab:>16}{100*is_hit:>8.1f}%{100*is_ruin:>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*oe:>11.1f}%"
                  f"{'✅' if oh >= TARGET else '❌':>7}")

    print("\n" + "=" * 118)
    print("【この測定の限界】")
    print("=" * 118)
    print("  ・ブックの分け方を決める際、既にV040でGOLDが強いことを見ている。")
    print("    『OOSから設計へのフィードバック』が弱い形で存在する（Codex・V038の指摘と同型）")
    print("  ・ただし4ブックすべてを報告するので『良かったものを選ぶ』余地は消している")
    print("  ・銘柄クラスという分け方は商品の性質から決まるもので、")
    print("    V031の貪欲探索（32,767通り）とは自由度が桁違いに小さい")
    print("\n完了。")


if __name__ == "__main__":
    main()
