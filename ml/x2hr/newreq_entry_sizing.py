"""V069：新要件の評価器に**エントリー時ロット固定**を入れて決定表を測り直す。

【Codexが優先度0と指定した4項目のうち、実装可能なもの】
> V048の評価器を修正することが優先順位0です。入口時点でのロット固定、
> 丸め前ロットとの対応、含み損益・証拠金、暦時間、成功条件付き分位点を
> 整理しないと、V052以降の改善幅も解釈できません。

- 成功条件付き分位点 → **V054で無条件の累積確率に修正済み**
- **入口時点でのロット固定 → 本スクリプトで実装**
- 丸め前の基準ロット → 約定ログから復元不能（Codexへ設計相談中）
- 含み損益・証拠金 → dealログに情報が無い（Codexへ設計相談中）
- 暦時間 → 移動ブロックでの実装方法をCodexへ相談中

【何を直すか】
現行の評価器は**決済時点の資金比**でロットを決めている。
実際のEAは**エントリー時点で**ロットを決める。

`dynamic_k_lag.py` の lag（エントリーから決済までにブックで決済された件数）を使い、
**step s で決済される取引のロットを M[s − lag] から決める。**

V029では旧要件（資金3万円・連続k）でこの修正を行い、
「規約差は最大2.4ptで符号も一定しない」と結論した。
**新要件（資金10万円・最小ロット制約あり・移動ブロック）でも同じか確認する。**

【測定する条件】決定表の主要3点
1. 2倍・3ヶ月（現状維持）
2. 2倍・12ヶ月（期限延長案）
3. 1.3倍・3ヶ月（目標倍率引下げ案）

**k選択はV068のR2規則（最大−1pt以内のkの中央値）を使う。**
IS窓の結果も併記する。到達・破綻は無条件の割合。
"""
from __future__ import annotations

import bisect
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl

CAPITAL = 100000.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = tuple(600000 + 999 * i for i in range(5))
RUIN = 0.10
L = 20
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
FLAT_TOL = 0.01
MONTHS = cc.MONTHS
CASES = [("2倍・3ヶ月（現状維持）", 2.0, 3.0),
         ("2倍・12ヶ月（期限延長案）", 2.0, 12.0),
         ("2倍・18ヶ月（期限延長案・長）", 2.0, 18.0),
         ("2倍・24ヶ月", 2.0, 24.0),
         ("1.2倍・3ヶ月（倍率引下げ案・小）", 1.2, 3.0),
         ("1.3倍・3ヶ月（倍率引下げ案）", 1.3, 3.0),
         ("1.5倍・3ヶ月", 1.5, 3.0)]


def build(window):
    """窓の (profit, volume, lag) を決済順に返す。lagは dynamic_k_lag と同じ定義。"""
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["magic"]) == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"])))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol in rows:
            if entry == 0:
                opened[pid] = (t, vol)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((t, profit, o[1], o[0]))
    rec.sort()
    t_out = [x[0] for x in rec]
    lags = np.empty(len(rec), dtype=np.int32)
    for i, (_, _, _, ti) in enumerate(rec):
        lags[i] = max(0, i - bisect.bisect_left(t_out, ti))
    return (np.array([x[1] for x in rec], dtype=float),
            np.array([x[2] for x in rec], dtype=float),
            lags)


def gen(pr, vo, lg, H, n_paths, seed):
    rng = np.random.default_rng(seed)
    n = len(pr)
    nb = H // L + 2
    starts = rng.integers(0, n, size=(n_paths, nb))
    off = np.arange(L)
    idx = (starts[:, :, None] + off[None, None, :]) % n
    idx = idx.reshape(n_paths, -1)[:, :H]
    return pr[idx], vo[idx], lg[idx]


def run(pp, vv, ll, k, mult, entry_sizing):
    """entry_sizing=True でエントリー時ロット固定、False で決済時（現行）。"""
    n_paths, H = pp.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    lot_hist = np.zeros((n_paths, H), dtype=np.float32)
    rows = np.arange(n_paths)
    for step in range(H):
        if not alive.any():
            break
        x = eq / CAPITAL
        v = vv[:, step]
        cur = np.maximum(MIN_LOT, np.floor(v * k * x / STEP + 1e-9) * STEP)
        lot_hist[:, step] = cur / np.maximum(v, 1e-9)   # 倍率として保存
        if entry_sizing:
            src = np.maximum(step - ll[:, step], 0)
            m_use = lot_hist[rows, src]
        else:
            m_use = cur / np.maximum(v, 1e-9)
        eq = np.where(alive, eq + pp[:, step] * m_use, eq)
        hit = alive & (eq >= CAPITAL * mult)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state


def select_r2(hits):
    """V068のR2規則：最大−1pt以内のkの中央値。"""
    best = max(hits.values())
    flat = [k for k in K_GRID if hits[k] >= best - FLAT_TOL]
    return flat[len(flat) // 2]


def main():
    print("=" * 112)
    print("V069：新要件の評価器にエントリー時ロット固定を入れて測り直す")
    print("=" * 112)
    print(f"資金{CAPITAL:,.0f}円 / 破綻ライン{100*RUIN:.0f}% / 最小ロット制約あり / "
          f"移動ブロックL={L} / シード{len(SEEDS)}本")
    print("k選択はV068のR2規則（最大−1pt以内のkの中央値）")
    print("**現行（決済時）とエントリー時を同じパスで比較する**\n")

    data = {}
    for w in ("IS", "OOS"):
        pr, vo, lg = build(w)
        data[w] = (pr, vo, lg, len(pr) / MONTHS[w])
        print(f"  {w}窓: {len(pr)}取引 / 月{len(pr)/MONTHS[w]:.1f}件 / "
              f"lag中央値 {int(np.median(lg))} / lag=0率 {100*(lg==0).mean():.1f}%")
    print()

    for label, mult, dl in CASES:
        print("=" * 112)
        print(f"【{label}】")
        print("=" * 112)
        print(f"{'規約':>14}{'IS選択k':>9}{'IS到達':>9}{'IS破綻':>9}"
              f"│{'OOS到達':>9}{'OOS破綻':>9}{'OOS未決':>9}{'70%':>7}")
        res = {}
        for es, tag in ((False, "現行(決済時)"), (True, "エントリー時")):
            # --- IS選択 ---
            pr, vo, lg, rate = data["IS"]
            H = int(round(rate * dl))
            hits = {}
            ruins = {}
            for k in K_GRID:
                hh, rr = [], []
                for sd in SEEDS:
                    pp, vv, ll = gen(pr, vo, lg, H, N_PATHS, sd)
                    st_ = run(pp, vv, ll, k, mult, es)
                    hh.append(float((st_ == 1).mean()))
                    rr.append(float((st_ == 2).mean()))
                hits[k] = float(np.mean(hh))
                ruins[k] = float(np.mean(rr))
            k_sel = select_r2(hits)
            # --- OOS適用 ---
            pr_o, vo_o, lg_o, rate_o = data["OOS"]
            H_o = int(round(rate_o * dl))
            hh, rr = [], []
            for sd in SEEDS:
                pp, vv, ll = gen(pr_o, vo_o, lg_o, H_o, N_PATHS, sd + 7)
                st_ = run(pp, vv, ll, k_sel, mult, es)
                hh.append(float((st_ == 1).mean()))
                rr.append(float((st_ == 2).mean()))
            oh, orr = float(np.mean(hh)), float(np.mean(rr))
            res[tag] = (k_sel, hits[k_sel], ruins[k_sel], oh, orr)
            print(f"{tag:>14}{k_sel:>9}{100*hits[k_sel]:>8.1f}%{100*ruins[k_sel]:>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%{100*(1-oh-orr):>8.1f}%"
                  f"{'✅' if oh >= 0.70 else '❌':>7}")
        a = res["エントリー時"]
        b = res["現行(決済時)"]
        print(f"\n  規約差（エントリー時 − 決済時）: 到達 {100*(a[3]-b[3]):+.2f}pt / "
              f"破綻 {100*(a[4]-b[4]):+.2f}pt")
        if a[0] != b[0]:
            print(f"  ⚠️ 選ばれたkが違う（{b[0]} vs {a[0]}）ため、"
                  f"規約の差とkの差が混ざっている")
        print()

    print("=" * 112)
    print("【まだ直せていない項目（Codexへ設計相談中）】")
    print("=" * 112)
    print("  ・丸め前の基準ロット——約定ログから復元できない")
    print("  ・含み損益・証拠金——dealログに情報が無い")
    print("  ・暦時間——移動ブロックで暦を保つ設計が必要")
    print("\n完了。")


if __name__ == "__main__":
    main()
