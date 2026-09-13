"""V066：頻度増を**現実的な質**で測り直す——追加枠はSCA-FX相当の質と仮定する。

【V059・V061の前提が甘かった】
V059・V061は「増えた取引機会も**既存ブックと同じ損益分布**に従う」と仮定していた。
既存ブックにはGOLD枠（1取引シャープ0.1369）が含まれており、**この仮定は楽観的すぎる。**

V065で判明したこと：

| SCA枠 | 銘柄 | 取引 | **1取引シャープ** | **t値** |
|---|---|---:|---:|---:|
| SCA USDJPY | USDJPY | 593 | **0.0416** | **1.01** |
| SCA GBPJPY | GBPJPY | 1,304 | **0.0407** | **1.47** |
| SCA GOLD1 | GOLD | 486 | 0.1369 | 3.02 |
| SCA GOLD2 | GOLD | 185 | 0.1061 | 1.44 |

**SCAをFX銘柄へ展開した場合の質は、GOLDではなくFXの実績（シャープ約0.041）で
見積もるべきである。** しかも **t値1.01・1.47 は10年かけても有意ではない。**

【本スクリプトの設計】
「SCA型を主要通貨ペアへ展開する」を、**実際のSCA-FX取引を再標本化して追加する**
形で表現する。

    合成ブック ＝ 既存の全取引 ＋ (f−1)倍ぶんの「SCA-FX相当」取引

追加分は **SCA USDJPY と SCA GBPJPY の実取引から復元抽出**する。
これなら「新銘柄でも既存のSCA-FXと同程度の質」という、
**楽観だが根拠のある仮定**になる（V059の「ブック平均と同じ」よりは保守的）。

**比較のため、V059と同じ「ブック平均と同じ質」の場合も併記する。**

【限界】
- 新銘柄のスプレッド・流動性・取引時間帯の違いを考慮していない
- 追加枠どうしの相関を無視している（実際は相関があり分散効果は小さくなる）
- 現在のSCA-FX 2銘柄は**選ばれた結果**である可能性がある（生存者バイアス）
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl
from sleeve_time_trend import SYMBOL_OF

CAPITAL = 100000.0
TARGET_P = 0.70
TARGET_M = 2.0
DEADLINE = 3.0
MIN_LOT = 0.01
STEP = 0.01
N_PATHS = 20000
SEEDS = (101, 202, 303)
RUIN = 0.10
L = 20
K_GRID = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0]
F_GRID = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
MONTHS = cc.MONTHS
SCA_FX = {20261000, 20261001}     # SCA USDJPY / SCA GBPJPY


def load(window):
    """窓の (profit, volume, magic) を決済順に返す。"""
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
                opened[pid] = (vol, m)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[0] <= 0:
                    continue
                rec.append((t, profit, o[0], o[1]))
    rec.sort()
    return (np.array([x[1] for x in rec], dtype=float),
            np.array([x[2] for x in rec], dtype=float),
            np.array([x[3] for x in rec], dtype=np.int64))


def gen_mixed(pr, vo, pr_add, vo_add, H, n_paths, L, seed, frac_add):
    """既存ブックと追加分を frac_add の割合で混ぜた移動ブロック・ブートストラップ。"""
    rng = np.random.default_rng(seed)
    n, na = len(pr), len(pr_add)
    nb = H // L + 2
    # ブロックごとに「既存」か「追加」かを選ぶ（ブロック内は同じ系列から取る）
    use_add = rng.random((n_paths, nb)) < frac_add
    starts = rng.integers(0, max(n, na), size=(n_paths, nb))
    off = np.arange(L)
    P = np.empty((n_paths, nb * L))
    V = np.empty((n_paths, nb * L))
    idx_b = (starts % n)[:, :, None] + off[None, None, :]
    idx_a = (starts % na)[:, :, None] + off[None, None, :]
    Pb = pr[idx_b % n].reshape(n_paths, -1)
    Vb = vo[idx_b % n].reshape(n_paths, -1)
    Pa = pr_add[idx_a % na].reshape(n_paths, -1)
    Va = vo_add[idx_a % na].reshape(n_paths, -1)
    mask = np.repeat(use_add, L, axis=1)
    P = np.where(mask, Pa, Pb)[:, :H]
    V = np.where(mask, Va, Vb)[:, :H]
    return P, V


def run(pp, vv, k):
    n_paths, H = pp.shape
    eq = np.full(n_paths, CAPITAL, dtype=float)
    alive = np.ones(n_paths, dtype=bool)
    state = np.zeros(n_paths, dtype=np.int8)
    for step in range(H):
        if not alive.any():
            break
        x = eq / CAPITAL
        v = vv[:, step]
        actual = np.maximum(MIN_LOT, np.floor(v * k * x / STEP + 1e-9) * STEP)
        eq = np.where(alive, eq + pp[:, step] * (actual / v), eq)
        hit = alive & (eq >= CAPITAL * TARGET_M)
        ruin = alive & (eq <= CAPITAL * RUIN)
        state[hit] = 1
        state[ruin] = 2
        alive = alive & ~(hit | ruin)
    return state


def main():
    print("=" * 112)
    print("V066：頻度増を**現実的な質**で測り直す（追加枠＝SCA-FX相当）")
    print("=" * 112)
    print("V059・V061は『増えた取引もブック平均と同じ質』と仮定していた。")
    print("ブック平均にはGOLD（シャープ0.1369）が含まれており楽観的すぎる。")
    print("**追加分をSCA-FX（USDJPY/GBPJPY・シャープ約0.041）の実取引から再標本化する。**\n")

    data = {}
    for w in ("IS", "OOS"):
        pr, vo, mg = load(w)
        sel = np.isin(mg, list(SCA_FX))
        rate = len(pr) / MONTHS[w]
        sh_all = float(pr.mean()) / float(pr.std(ddof=1))
        sh_add = (float(pr[sel].mean()) / float(pr[sel].std(ddof=1))
                  if sel.sum() > 2 else 0.0)
        data[w] = (pr, vo, pr[sel], vo[sel], rate)
        print(f"  {w}窓: 全体{len(pr)}取引（シャープ{sh_all:.4f}） / "
              f"SCA-FX {int(sel.sum())}取引（シャープ{sh_add:.4f}）"
              f" → 質は **{sh_add/sh_all if sh_all else 0:.0%}**")
    print()

    print(f"{'頻度':>6}{'追加分の質':>13}{'3ヶ月取引数':>12}"
          f"│{'IS選択k':>9}{'IS到達':>9}"
          f"│{'OOS到達':>9}{'OOS破綻':>9}{'R3(70%)':>9}")
    for f in F_GRID:
        for tag, use_sca in (("ブック平均(V059)", False), ("**SCA-FX相当**", True)):
            frac = 0.0 if f <= 1.0 else (f - 1.0) / f
            rec = {}
            for w in ("IS", "OOS"):
                pr, vo, pa, va, rate = data[w]
                H = int(round(rate * f * DEADLINE))
                r = {}
                for k in K_GRID:
                    hh, rr = [], []
                    for sd in SEEDS:
                        if use_sca and frac > 0:
                            pp, vv = gen_mixed(pr, vo, pa, va, H, N_PATHS, L,
                                               270000 + sd, frac)
                        else:
                            pp, vv = gen_mixed(pr, vo, pr, vo, H, N_PATHS, L,
                                               270000 + sd, 0.0)
                        st_ = run(pp, vv, k)
                        hh.append(float((st_ == 1).mean()))
                        rr.append(float((st_ == 2).mean()))
                    r[k] = (float(np.mean(hh)), float(np.mean(rr)))
                rec[w] = (r, H)
            k_sel = max(K_GRID, key=lambda k: rec["IS"][0][k][0])
            ih, _ = rec["IS"][0][k_sel]
            oh, orr = rec["OOS"][0][k_sel]
            print(f"{f:>5.0f}x{tag:>13}{rec['OOS'][1]:>12}"
                  f"│{k_sel:>9}{100*ih:>8.1f}%"
                  f"│{100*oh:>8.1f}%{100*orr:>8.1f}%"
                  f"{'✅' if oh >= TARGET_P else '❌':>9}")
        print()

    print("=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・新銘柄のスプレッド・流動性・取引時間帯の違いを考慮していない")
    print("  ・追加枠どうしの相関を無視している（実際は分散効果が小さくなる）")
    print("  ・現在のSCA-FX 2銘柄は選ばれた結果である可能性がある（生存者バイアス）")
    print("  ・SCA-FXのt値は1.01・1.47で、**10年かけても統計的に有意ではない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
