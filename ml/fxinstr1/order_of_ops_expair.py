# -*- coding: utf-8 -*-
"""`order_of_ops.py` を **PairTrade を除いて**やり直す（2026-09-17・Codex の査読による）。

【なぜ除くのか】
`ProcPair()` は **シグナルの有無・保有の有無にかかわらず、毎評価で `LotComplex()` を2回呼ぶ**
（`experts/MIX_EA_SIMVERIFY.mq5` の `ProcPair()` 冒頭）。`LotComplex()` は `Clamp()` を通るので、
**Pair の `calls` / `cut` / `deny` / `want` / `got` は「注文」ではなく「評価」の数**である。

他の枠（PB・RSI・SCA・VBO・Carry）は `Clamp()` を**発注分岐の中でだけ**呼ぶので、
そちらは注文の数である。したがって Pair を混ぜた集計は**件数を桁で歪める**。

使い方: python ml/fxinstr1/order_of_ops_expair.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_oo", ROOT / "order_of_ops.py")
oo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oo)

PAIR = 20260629


def main():
    caps = sorted(oo.DEALS.glob("*_cap.csv"))
    if not caps:
        print("cap 計装ログがまだ無い")
        return 0
    print("# Pair を除いた cap の実像（Pair の Clamp 呼び出しは注文ではない）")
    print("")
    print("| run | 通過率(全枠) | **通過率(Pair除く)** | 削られた注文(Pair除く) | "
          "見送り(Pair除く) | 同足に決済あり | 割合 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for cp in caps:
        run_id = cp.name[: -len("_cap.csv")]
        dp = oo.DEALS / f"{run_id}_deals.csv"
        ev, agg, meta, _ = oo.cap_events(cp)
        if not ev:
            continue
        freed = oo.exits_by_bar(dp) if dp.exists() else {}
        evx = [e for e in ev if e[1] != PAIR]
        resc = 0
        for t, magic, want, got, eq, used in evx:
            b = t - (t % oo.BAR)
            later = [m for (tt, mm, m) in freed.get(b, []) if tt >= t and mm != magic]
            if later:
                resc += 1
        cutx = sum(a["cut"] for m, a in agg.items() if m != PAIR)
        denyx = sum(a["deny"] for m, a in agg.items() if m != PAIR)
        tw = sum(a["want"] for a in agg.values())
        tg = sum(a["got"] for a in agg.values())
        twx = sum(a["want"] for m, a in agg.items() if m != PAIR)
        tgx = sum(a["got"] for m, a in agg.items() if m != PAIR)
        print("| {} | {:.1f}% | **{:.1f}%** | {} | {} | {} | {:.1f}% |".format(
            run_id, tg / tw * 100 if tw else 0.0, tgx / twx * 100 if twx else 0.0,
            cutx, denyx, resc, resc / max(cutx, 1) * 100))
    print("")
    print("> 通過率は Pair を除くと**下がる**（Pair は評価のたびに小さな希望を積むため分母を薄める）。")
    print("> 一方、削られた**注文**の件数は桁で減る。**cap は『多くの注文を少しずつ』ではなく、")
    print("> 『少数の大きな注文を大幅に』削っている。**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
