"""枠別の重み（`Mult_*`）を、risk%化と証拠金cap を入れた土俵で測り直す（段階2）。

【何に答えるか】
Claude案 **A3（枠ごとに riskPct を変える）**・**A7（枠別に倍率を変える）**、
Codex案 **#7（相関込みの静的な枠配分）**は、`ml/fxweight1/`（2026-09-08）で
MT5実測45案まで測ってある。**ただしそれは倍率1・risk%化前・cap前の土俵だった。**

その後この本は
  - RSI3枠を risk% 化し（`FxRiskMask`）
  - 倍率を3まで上げ（`GlobalLotMult`）
  - 証拠金cap でロットを削る（`MarginCapPct`）
という3つの変更を受けている。**枠の重みの最適点は、土俵が変われば動く。**
`docs/oanda_fx_cap_pathdep_20260915.md` が「6%以上の窓の数は cap では増えない」と
結論した以上、**分布そのものを動かす軸**を当たり直す価値がある。

【EAのロット計算を忠実に写すこと — ここを間違えると結論が変わる】
EA（`MIX_EA_SIMVERIFY.mq5`）は

    Clamp(sym, base * GlobalLotMult * lotMult * factor)

であり、**重みは Clamp の前に掛かる。**そして `Clamp()` は

    lot = floor(lot/step)*step
    if (capで削られた && lot < min) return 0      // capのときだけ捨てる
    return MathMax(min, MathMin(max, lot))        // それ以外は最小ロットへ切り上げ

> [!important] **重み < 1 は、ロットが既に最小値の枠には効かない。**
> 0.01 × 0.15 = 0.0015 は floor で 0 になり、`MathMax(min, ...)` で 0.01 に戻る。
> **固定ロット0.01の枠は、重みでは減らせない（増やすことはできる）。**
> これは実装の穴ではなくEAの仕様であり、シミュレーション側も同じ挙動にしてある。
> `Mult_SCA_GBPJPY=0.15` が効いたのは、SCA_GJ が risk%枠かつ Rev ブーストで
> ロットが 0.01 より大きかったからである。

【窓の使い分け — ここを崩すと何も分からない】
**重みは IS（2021-06-20〜2026-06-20）だけで決め、OOS（2016-11-09〜2021-06-20）で評価する。**
IS で決めて IS で評価すれば必ず良く見える。

【限界】
- **段階2の簡易検証。採用の最終判断は MT5 バックテストで行う。**
- equity は決済損益ベース＝**含み損を含まない**。実際の最大DDはこれより深い。
- 拒否された注文は deal ログに無い。重みを上げた側が実口座で通る保証はない
  （capの判定は入れてあるが、logged 側が既に壁に当たっていた可能性は消せない）。
- 枠の重みを変えても**シグナルの発生時刻は変わらない**前提。ロットだけの変更なので成立する。
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "mcs", REPO / "ml" / "fxmargin2" / "margin_cap_sim.py")
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)

DEPOSIT = mcs.DEPOSIT
CONTRACT = mcs.CONTRACT
LEVERAGE = mcs.LEVERAGE
STEP = mcs.LOT_STEP
MIN_LOT = mcs.MIN_LOT
NAME = mcs.SLEEVE_NAME
SLEEVES = [20260622, 20260627, 20260610, 20260605, 20260774,
           20260629, 20260650, 20261000, 20261001]

# 窓（measure.py と同じ定義）
IS_FROM = datetime(2021, 6, 20, tzinfo=timezone.utc).timestamp()
OOS_FROM = datetime(2016, 11, 9, tzinfo=timezone.utc).timestamp()
OOS_TO = IS_FROM
IS_TO = datetime(2026, 6, 20, tzinfo=timezone.utc).timestamp()
WINDOWS = {"IS": (IS_FROM, IS_TO, 60.0), "OOS": (OOS_FROM, OOS_TO, 55.0)}


# 銘柄のロット上限。EA の Clamp() は MathMin(mx, ...) でここを効かせている。
# fxmargin2 の T036 FULL（cap無制限）の logged run が**ちょうど 50.00 で頭打ち**に
# なっていることから、この銘柄・口座の SYMBOL_VOLUME_MAX は 50 である。
# これを入れずに重みを探索すると、最大ロット 380 のような実行不可の解に落ちる。
MAX_LOT = 50.0


def clamp(lot, cut):
    """EA の Clamp() と同じ丸め。cut=capで削られたか。"""
    lot = math.floor(lot / STEP) * STEP
    if cut and lot < MIN_LOT - 1e-12:
        return 0.0
    return max(MIN_LOT, min(MAX_LOT, lot))


def simulate(rows, comp_magics, weights, cap, t0, t1):
    """[t0,t1) に建てた取引だけで、入金50万円の口座を再構成する。"""
    log_eq = sim_eq = float(DEPOSIT)
    sim_peak = float(DEPOSIT)
    sim_min = float(DEPOSIT)
    dd = 0.0
    used = 0.0
    pos = {}
    monthly = defaultdict(float)
    by_sleeve = defaultdict(float)
    opened = dropped = 0
    worst_ratio = 0.0
    max_lot = 0.0

    for r in rows:
        ts = int(r["time"])
        pid = r["position_id"]
        if r["entry"] == "0":
            if not (t0 <= ts < t1):
                continue
            magic = int(r["magic"])
            rate = mcs.jpy_rate(r)
            vol = float(r["volume"])
            if rate is None or rate <= 0 or vol <= 0:
                continue
            opened += 1
            need_unit = vol * CONTRACT * rate / LEVERAGE
            w = weights.get(magic, 1.0)
            k = (sim_eq / log_eq) if (magic in comp_magics and log_eq > 0) else 1.0
            k = max(0.0, k) * w
            cut = False
            if cap is not None and sim_eq > 0:
                avail = cap * sim_eq - used
                if need_unit * k > avail:
                    k = max(0.0, avail / need_unit) if need_unit > 0 else 0.0
                    cut = True
            lot = clamp(vol * k, cut)
            if lot <= 0.0:
                dropped += 1
                pos[pid] = {"k": 0.0, "need_unit": need_unit, "vol_left": vol,
                            "magic": magic}
                continue
            k = lot / vol
            max_lot = max(max_lot, lot)
            pos[pid] = {"k": k, "need_unit": need_unit, "vol_left": vol, "magic": magic}
            used += need_unit * k
        else:
            profit = float(r["profit"])
            log_eq += profit
            p = pos.get(pid)
            if p is None:
                continue
            vol = float(r["volume"])
            ka = p["k"]
            sim_eq += profit * ka
            by_sleeve[p["magic"]] += profit * ka
            frac = min(1.0, vol / p["vol_left"]) if p["vol_left"] > 0 else 1.0
            used = max(0.0, used - p["need_unit"] * ka * frac)
            p["vol_left"] -= vol
            if p["vol_left"] <= 1e-9:
                pos.pop(pid, None)
            monthly[datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")] += profit * ka
            sim_min = min(sim_min, sim_eq)
            sim_peak = max(sim_peak, sim_eq)
            if sim_peak > 0:
                dd = max(dd, (sim_peak - sim_eq) / sim_peak)
        if sim_eq > 0:
            worst_ratio = max(worst_ratio, used / sim_eq)

    return {"net": sim_eq - DEPOSIT, "dd": dd, "min_eq": sim_min, "opened": opened,
            "dropped": dropped, "worst_ratio": worst_ratio, "max_lot": max_lot,
            "monthly": dict(monthly), "by_sleeve": dict(by_sleeve),
            "geo": geo(monthly)}


def geo(monthly):
    eq = float(DEPOSIT)
    rets = []
    for m in sorted(monthly):
        if eq <= 0:
            break
        rets.append(monthly[m] / eq)
        eq += monthly[m]
    if not rets:
        return 0.0
    acc = 1.0
    for x in rets:
        acc *= max(1e-9, 1.0 + x)
    return (acc ** (1.0 / len(rets)) - 1.0) * 100


GRID = [0.0, 0.15, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="T036")
    ap.add_argument("--cap", type=float, default=0.80)
    ap.add_argument("--passes", type=int, default=3)
    args = ap.parse_args()

    rows = mcs.load(REPO, args.id, "full")
    if not rows:
        raise SystemExit(f"deal ログが見つかりません: {args.id} full")
    params, desc = mcs.params_of(REPO, args.id)
    comp = mcs.compounding_magics(params)

    print(f"■ {args.id}  {desc}")
    print(f"  cap={args.cap:.0%}・重みは IS(60か月)だけで決め、OOS(55か月)で評価する")
    print("  equity は決済損益ベース＝含み損を含まない。段階2の簡易検証。\n")

    base_w = {m: 1.0 for m in SLEEVES}

    # --- 自己検証: 全重み1 は subperiod/margin_cap と一致しなければならない -------
    chk = simulate(rows, comp, base_w, args.cap, OOS_FROM, IS_TO)
    print(f"  自己検証（全重み1・FULL相当）: 純益 {round(chk['net']):,}  "
          f"最大DD {chk['dd']*100:.1f}%  最大ロット {chk['max_lot']:.2f}")
    print("  → docs/oanda_fx_margin_cap_20260915.md の cap80% FULL 105,720,252円 と"
          " 突き合わせること\n")

    def ev(w, win):
        t0, t1, _ = WINDOWS[win]
        return simulate(rows, comp, w, args.cap, t0, t1)

    # 【DD予算】重みを上げれば月利は上がる。制約を置かない探索は「もっと大きく」に
    # 収束するだけで、配分の話にならない（初回の試行は最大ロット380という
    # 実行不可の解に落ちた）。**基準構成と同じDDに収まる範囲でだけ**動かす。
    # これは Claude案 A8（DD予算からの逆算サイジング）・D8（DD主因枠の減量）の形である。
    base_is = ev(base_w, "IS")
    dd_budget = base_is["dd"]
    print(f"  IS 出発点（全重み1）: {base_is['geo']:.2f}%/月・最大DD {dd_budget*100:.1f}%")
    print(f"  DD予算: IS最大DD ≤ {dd_budget*100:.1f}%（基準と同じ）。"
          f"ロット上限 {MAX_LOT:.0f}（SYMBOL_VOLUME_MAX）\n")

    cur = dict(base_w)
    best = base_is["geo"]
    print("  座標降下（ISのみで決める・DD予算内）")
    for p in range(args.passes):
        moved = False
        for m in SLEEVES:
            keep, best_w = best, cur[m]
            for w in GRID:
                if w == cur[m]:
                    continue
                trial = dict(cur)
                trial[m] = w
                s = ev(trial, "IS")
                if s["dd"] > dd_budget + 1e-9:
                    continue                      # DD予算を超える案は採らない
                g = s["geo"]
                if g > keep + 1e-9:
                    keep, best_w = g, w
            if best_w != cur[m]:
                print(f"    pass{p+1} {NAME[m]:<10} {cur[m]:.2f} -> {best_w:.2f}"
                      f"   IS {best:.2f}% -> {keep:.2f}%")
                cur[m], best, moved = best_w, keep, True
        if not moved:
            print(f"    pass{p+1} 変化なし。収束")
            break

    print("\n  決まった重み（ISのみで決定）")
    for m in SLEEVES:
        mark = "" if abs(cur[m] - 1.0) < 1e-9 else "  <-- 変更"
        print(f"    {NAME[m]:<10} {cur[m]:.2f}{mark}")

    print("\n  評価（IS で決めた重みを OOS に当てる）")
    print("  %-22s %14s %9s %8s %9s %10s" %
          ("", "純益", "月利", "最大DD", "最低資産", "最大ロット"))
    for label, w in (("全重み1（基準）", base_w), ("IS最適重み", cur)):
        for win in ("IS", "OOS"):
            s = ev(w, win)
            print("  %-16s %-5s %14s %8.2f%% %7.1f%% %10s %9.2f"
                  % (label, win, format(round(s["net"]), ","), s["geo"],
                     s["dd"] * 100, format(round(s["min_eq"]), ","), s["max_lot"]))

    b_is, b_oos = ev(base_w, "IS"), ev(base_w, "OOS")
    c_is, c_oos = ev(cur, "IS"), ev(cur, "OOS")
    print(f"\n  IS  月利 {b_is['geo']:.2f}% -> {c_is['geo']:.2f}%"
          f"  （+{c_is['geo']-b_is['geo']:.2f}pt・IS で選んだのだから当然上がる）")
    print(f"  OOS 月利 {b_oos['geo']:.2f}% -> {c_oos['geo']:.2f}%"
          f"  （{c_oos['geo']-b_oos['geo']:+.2f}pt・**これが本当の判定**）")

    print("\n注: 段階2の簡易検証であり、採用の根拠にはしない。")
    print("    重み<1 はロットが最小値の枠には効かない（EAが最小ロットへ切り上げる）。")


if __name__ == "__main__":
    main()
