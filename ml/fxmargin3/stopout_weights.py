"""枠別の重みを入れた構成が、本当にロスカットされないかを上界で判定する（段階2）。

`docs/oanda_fx_sleeve_weights_20260915.md` §6 は、自分の弱点をこう挙げた。

> **実行可能性を確かめていない**（大）——新しい重みで `stopout_bound.py`
> （SLから含み損の上界→維持率）を**やり直していない**。
> 第2報がcap80%について出した「最悪維持率112%・ロスカット無し」は
> **この重みには適用できない。**

ここを塞ぐ。**月利がいくつであろうと、ロスカットされる構成は採れない。**

【判定の考え方（`ml/fxmargin2/stopout_bound.py` と同じ）】
建玉には SL が入っており、**SL より下へは（ギャップを除き）損は進まない**ので

    equity_worst = 確定equity − Σ_建玉(約定価格とSLの差 × ロット × 契約 × JPY換算)

は**その時点で起こりうる最悪値の下限**である。
OANDA証券MT5 は**維持率100%で追証・50%でロスカット**なので、
`equity_worst / 使用証拠金` がこの線を割らなければロスカットされない。

> [!tip] **この判定は非対称。使い方を間違えないこと。**
> 「**安全**」は**保証**（SLが機能する限りロスカットされない）。
> 「**★ロスカット**」は**警告にすぎない**——「全建玉が同時にSLまで逆行したら」の話。
> **保証の側だけを採否に使う。**

【`stopout_bound.py` との差】
1. **枠別の重み**を入れる。
2. **`SYMBOL_VOLUME_MAX`=50** を入れる（`weights.py` と同じ。入れないと最大ロット380の
   実行不可の解を「安全」と判定してしまう）。
3. 丸めを EA の `Clamp()` に合わせる——**capで削られた場合だけ**最小ロット未満を捨て、
   それ以外は最小ロットへ切り上げる。`stopout_bound.py` は常に捨てる書き方だった。
4. **IS / OOS の窓**で分けて出す。

【限界】
- 週明けギャップ・指標時の飛びは SL を越える。上界は「SLが機能した場合」の話。
- **SLを持たない建玉**（Carry など）は損失に下限が無い。件数と証拠金を別掲する。
- スワップ・手数料は含まない。**段階2。採用の最終判断は MT5 で行う。**
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ml" / "fxmargin2"))
_spec = importlib.util.spec_from_file_location(
    "sb", REPO / "ml" / "fxmargin2" / "stopout_bound.py")
SB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SB)
M = SB.M

_wspec = importlib.util.spec_from_file_location("w", Path(__file__).parent / "weights.py")
W = importlib.util.module_from_spec(_wspec)
_wspec.loader.exec_module(W)

STOPOUT = SB.STOPOUT_LEVEL
CALL = SB.MARGINCALL_LEVEL


def run(rows, comp, weights, cap, t0, t1):
    log_eq = sim_eq = float(M.DEPOSIT)
    used = 0.0
    pos = {}
    worst = float("inf")
    worst_at = None
    worst_detail = ""
    nosl_max = 0
    nosl_margin = 0.0
    below_call = below_stop = obs = 0
    max_lot = 0.0

    for r in rows:
        ts = int(r["time"])
        magic = int(r["magic"])
        pid = r["position_id"]
        if r["entry"] == "0":
            if not (t0 <= ts < t1):
                continue
            rate = M.jpy_rate(r)
            vol = float(r["volume"])
            if rate is None or rate <= 0 or vol <= 0:
                continue
            need = vol * M.CONTRACT * rate / M.LEVERAGE
            k = (sim_eq / log_eq) if (magic in comp and log_eq > 0) else 1.0
            k = max(0.0, k) * weights.get(magic, 1.0)
            cut = False
            if cap is not None and sim_eq > 0:
                avail = cap * sim_eq - used
                if need * k > avail:
                    k = max(0.0, avail / need) if need > 0 else 0.0
                    cut = True
            lot = W.clamp(vol * k, cut)
            if lot <= 0.0:
                pos[pid] = {"k": 0.0, "need": need, "vl": vol, "m": magic,
                            "risk": 0.0, "nosl": False}
                continue
            k = lot / vol
            max_lot = max(max_lot, lot)
            risk = SB.sl_loss_jpy(r, lot)
            pos[pid] = {"k": k, "need": need, "vl": vol, "m": magic,
                        "risk": risk if risk is not None else 0.0,
                        "nosl": risk is None}
            used += need * k
        else:
            p = pos.get(pid)
            profit = float(r["profit"])
            vol = float(r["volume"])
            log_eq += profit
            if p is None:
                continue                       # 窓外で建てた玉は sim に無い
            sim_eq += profit * p["k"]
            frac = min(1.0, vol / p["vl"]) if p["vl"] > 0 else 1.0
            used = max(0.0, used - p["need"] * p["k"] * frac)
            p["vl"] -= vol
            if p["vl"] <= 1e-9:
                pos.pop(pid, None)

        live = [p for p in pos.values() if p["k"] > 0]
        if used > 0 and live:
            risk_sum = sum(p["risk"] for p in live)
            nosl = [p for p in live if p["nosl"]]
            nosl_max = max(nosl_max, len(nosl))
            nosl_margin = max(nosl_margin, sum(p["need"] * p["k"] for p in nosl))
            level = (sim_eq - risk_sum) / used
            obs += 1
            if level < CALL:
                below_call += 1
            if level < STOPOUT:
                below_stop += 1
            if level < worst:
                worst = level
                worst_at = ts
                by = defaultdict(float)
                for p in live:
                    by[p["m"]] += p["risk"]
                worst_detail = " / ".join(
                    "%s %s" % (M.SLEEVE_NAME.get(m, m), format(round(v), ","))
                    for m, v in sorted(by.items(), key=lambda x: -x[1])[:3])

    return {"worst": worst if worst < float("inf") else 0.0,
            "when": (datetime.fromtimestamp(worst_at, timezone.utc).strftime("%Y-%m-%d")
                     if worst_at else "-"),
            "detail": worst_detail, "obs": obs, "below_call": below_call,
            "below_stop": below_stop, "nosl_max": nosl_max,
            "nosl_margin": nosl_margin, "net": sim_eq - M.DEPOSIT, "max_lot": max_lot}


OPT = {20260622: 0.3, 20260627: 1.0, 20260610: 2.0, 20260605: 4.0, 20260774: 4.0,
       20260629: 8.0, 20260650: 0.75, 20261000: 12.0, 20261001: 12.0}
CONS = {20260622: 0.5, 20260627: 1.0, 20260610: 2.0, 20260605: 4.0, 20260774: 4.0,
        20260629: 4.0, 20260650: 0.75, 20261000: 4.0, 20261001: 4.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="T036")
    ap.add_argument("--cap", type=float, default=0.80)
    args = ap.parse_args()
    rows = M.load(REPO, args.id, "full")
    params, desc = M.params_of(REPO, args.id)
    comp = M.compounding_magics(params)

    print("含み損の上界つき証拠金維持率（SLまで逆行した最悪ケース）")
    print("OANDA証券MT5: 維持率100%で追証・50%でロスカット。")
    print(f"■ {args.id}  cap={args.cap:.0%}   ロット上限 {W.MAX_LOT:.0f}\n")
    print("  %-20s %-4s %14s %10s %12s %11s %9s %9s"
          % ("重み", "窓", "純益", "最悪維持率", "その日", "追証割れ", "ロスカット", "最大lot"))
    for label, w in (("全重み1（基準）", {m: 1.0 for m in W.SLEEVES}),
                     ("IS最適重み", OPT), ("保守版（一律4倍まで）", CONS)):
        for win in ("IS", "OOS"):
            t0, t1, _ = W.WINDOWS[win]
            s = run(rows, comp, w, args.cap, t0, t1)
            verdict = "★ロスカット" if s["below_stop"] else (
                "追証" if s["below_call"] else "安全")
            print("  %-20s %-4s %14s %9.0f%% %12s %5d/%-5d %7d  %8.2f  %s"
                  % (label, win, format(round(s["net"]), ","), s["worst"] * 100,
                     s["when"], s["below_call"], s["obs"], s["below_stop"],
                     s["max_lot"], verdict))
        print()

    print("  最悪時点のリスク内訳（上位3枠）")
    for label, w in (("IS最適重み", OPT), ("保守版", CONS)):
        for win in ("IS", "OOS"):
            t0, t1, _ = W.WINDOWS[win]
            s = run(rows, comp, w, args.cap, t0, t1)
            print(f"    {label} {win}: {s['detail']}")
            print(f"      SL無し建玉 最大{s['nosl_max']}本 / 証拠金"
                  f"{round(s['nosl_margin']):,}円")

    print("\n注: 「安全」は『SLが機能する限りロスカットされない』の保証。")
    print("    「★ロスカット」は『全建玉が同時にSLまで逆行したら』の警告にすぎない。")
    print("    保証の側だけを採否に使う。段階2であり、採用の最終判断は MT5 で行う。")


if __name__ == "__main__":
    main()
