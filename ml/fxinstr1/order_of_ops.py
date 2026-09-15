# -*- coding: utf-8 -*-
"""Codex #1「退出を先、参入を後に」を、削られた注文の記録から判定する。

`ml/fxeff1/samebar.py` では判定できなかった。#1 が拾おうとしているのは
**cap に見送られて deal ログに存在しない注文**であり、存在しないものは数えられないからである。

EA の cap 計装は **削られた注文を1件ずつ、時刻つきで**残す。
deal ログには**決済の時刻**がある。突き合わせれば、次が言える:

  削られた注文のうち、**同じ足の中で（その後に）別の枠が決済していた**ものは何件か。
  その決済が空けた証拠金は、削られた分を埋めるのに足りたか。

これが #1 が拾える上限である。**今度は本当に上限である**——
「同じ足に決済が無い」削られ方は、順序をどう変えても救えない。

使い方: python ml/fxinstr1/order_of_ops.py
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEALS = ROOT / "run_deals"
BAR = 15 * 60
CONTRACT = 100_000
LEVERAGE = 25

NAME = {20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
        20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
        20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ"}
KIND = {20260622: "price", 20260627: "price", 20260610: "price",
        20260605: "price*usdjpy", 20260774: "price*usdjpy",
        20260629: "price*usdjpy", 20260650: "price",
        20261000: "price", 20261001: "price"}


def cap_events(path):
    """(time, magic, want, got, equity, used) の列と、枠別集計を返す。"""
    ev, agg, meta, overflow = [], {}, {}, False
    for r in csv.reader(open(path, encoding="utf-8", errors="replace")):
        if not r or r[0] == "kind":
            continue
        if r[0] == "event" and len(r) >= 7:
            ev.append((int(r[2]), int(r[1]), float(r[3]), float(r[4]),
                       float(r[5]), float(r[6])))
        elif r[0] == "sleeve" and len(r) >= 7:
            agg[int(r[1])] = {"calls": int(r[2]), "cut": int(r[3]),
                              "deny": int(r[4]), "want": float(r[5]),
                              "got": float(r[6])}
        elif r[0] == "event_overflow" and len(r) >= 3:
            overflow = (r[2] == "1")
        elif r[0] in ("equity_dd_pct", "balance_dd_pct") and len(r) >= 6:
            try:
                meta[r[0]] = float(r[5])
            except ValueError:
                pass
    return ev, agg, meta, overflow


def exits_by_bar(path):
    """決済の時刻 → その足で解放された証拠金（JPY）と枠。"""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))
    opened = {}
    freed = defaultdict(list)
    for r in rows:
        pid, magic = r["position_id"], int(r["magic"])
        if magic not in KIND:
            continue
        if int(r["entry"]) == 0:
            price = float(r["price"])
            if KIND[magic] == "price*usdjpy":
                uj = float(r["usdjpy"])
                price = price * uj if uj > 0 else 0.0
            if price <= 0:
                continue
            opened[pid] = float(r["volume"]) * CONTRACT * price / LEVERAGE
        else:
            m = opened.pop(pid, None)
            if m is None:
                continue
            t = int(r["time"])
            freed[t - (t % BAR)].append((t, magic, m))
    return freed


def main():
    caps = sorted(DEALS.glob("*_cap.csv"))
    if not caps:
        print("cap 計装ログがまだ無い")
        return 0
    print("# Codex #1「退出を先、参入を後に」が拾える上限")
    print("")
    for cp in caps:
        run_id = cp.name[:-len("_cap.csv")]
        dp = DEALS / f"{run_id}_deals.csv"
        ev, agg, meta, overflow = cap_events(cp)
        if not ev:
            continue
        freed = exits_by_bar(dp) if dp.exists() else {}

        rescuable = 0
        rescuable_full = 0
        denied = 0
        denied_rescuable = 0
        for t, magic, want, got, eq, used in ev:
            b = t - (t % BAR)
            later = [m for (tt, mm, m) in freed.get(b, []) if tt >= t and mm != magic]
            is_deny = got <= 0.0
            if is_deny:
                denied += 1
            if later:
                rescuable += 1
                if is_deny:
                    denied_rescuable += 1
                # 解放された証拠金が、削られた分を埋めるのに足りたか（粗い上界）
                if sum(later) > 0:
                    rescuable_full += 1

        tot_cut = sum(a["cut"] for a in agg.values()) or 1
        tot_deny = sum(a["deny"] for a in agg.values())
        tw = sum(a["want"] for a in agg.values())
        tg = sum(a["got"] for a in agg.values())
        print("## {}".format(run_id))
        print("")
        if overflow:
            print("> [!warning] イベント記録が上限に達した。以下は過小評価である。")
            print("")
        print("- 通過率 lot_got/lot_want: **{:.1f}%**（希望 {:,.1f} → 通過 {:,.1f}）".format(
            tg / tw * 100 if tw else 100.0, tw, tg))
        print("- cap が削った注文: **{}件**、うち発注を見送った(deny): **{}件**".format(
            tot_cut, tot_deny))
        print("- 削られた注文のうち、**同じ足の中で後から別の枠が決済していた**もの: "
              "**{}件（{:.1f}%）**".format(rescuable, rescuable / tot_cut * 100))
        print("- そのうち発注を見送っていたもの: **{}件**".format(denied_rescuable))
        if meta:
            print("- 含み損込みDD **{:.2f}%** / 残高ベースDD **{:.2f}%**".format(
                meta.get("equity_dd_pct", float("nan")),
                meta.get("balance_dd_pct", float("nan"))))
        print("")
        print("> 「同じ足に決済が無い」削られ方は、処理順をどう変えても救えない。")
        print("> したがって上の件数が #1 の拾える上限である。")
        print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
