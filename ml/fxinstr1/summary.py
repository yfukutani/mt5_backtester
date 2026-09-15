# -*- coding: utf-8 -*-
"""cap 計装ログを読む — capは実際にどれだけ削っていたのか。

`lot_got / lot_want` が「cap を通過した量の割合」である。
これが 1.00 に近ければ、**発注の順序や配分をどう賢くしても取り返す余地が無い**
（Codex #1/#2/#4/#7 はまとめて価値が無い）。

`deny` は cap が 0 にして**発注そのものを見送った**回数。
これが多ければ、見送られた注文を拾う案（#6 シグナル保持・#7 後追い補充）に意味が出る。

含み損込みDD（equity_dd_pct）と残高ベースDD（balance_dd_pct）も併記する。
報告してきたDDは**ずっと残高ベース**だったので、差がどれだけあるかをここで初めて見る。
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = {
    20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
    20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
    20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ",
}


def read_cap(path):
    sleeves, meta = [], {}
    for r in csv.reader(open(path, encoding="utf-8", errors="replace")):
        if not r or r[0] == "kind":
            continue
        if r[0] == "sleeve":
            sleeves.append({
                "magic": int(r[1]), "calls": int(r[2]), "cut": int(r[3]),
                "deny": int(r[4]), "want": float(r[5]), "got": float(r[6])})
        elif r[0] in ("equity_dd_pct", "balance_dd_pct"):
            try:
                meta[r[0]] = float(r[5])
            except (IndexError, ValueError):
                pass
    return sleeves, meta


def main():
    res = ROOT / "results.csv"
    runs = {}
    if res.exists():
        for r in csv.DictReader(open(res, encoding="utf-8")):
            if r.get("status") == "OK":
                runs[r["run_id"]] = (r["proposal_id"], r["window"], r["cap"])

    caps = sorted((ROOT / "run_deals").glob("*_cap.csv"))
    if not caps:
        print("cap 計装ログがまだ無い")
        return 0

    print("# cap 計装 — capは実際にどれだけ削っていたのか")
    for p in caps:
        run_id = p.name[:-len("_cap.csv")]
        pid, win, cap = runs.get(run_id, ("?", "?", "?"))
        sleeves, meta = read_cap(p)
        if not sleeves:
            continue
        tw = sum(s["want"] for s in sleeves)
        tg = sum(s["got"] for s in sleeves)
        tc = sum(s["calls"] for s in sleeves)
        tcut = sum(s["cut"] for s in sleeves)
        td = sum(s["deny"] for s in sleeves)
        print("")
        print("## {} / {} （cap={}）".format(pid, win, cap))
        edd = meta.get("equity_dd_pct")
        bdd = meta.get("balance_dd_pct")
        if edd is not None and bdd is not None:
            print("")
            print("**含み損込みDD {:.2f}% / 残高ベースDD {:.2f}%（差 {:+.2f}pt）**".format(
                edd, bdd, edd - bdd))
        print("")
        print("| 枠 | 発注判定 | cap が削った | **発注見送り** | 希望ロット | 通過ロット | **通過率** |")
        print("|---|---:|---:|---:|---:|---:|---:|")
        for s in sorted(sleeves, key=lambda s: s["want"] - s["got"], reverse=True):
            rate = s["got"] / s["want"] * 100 if s["want"] > 0 else 100.0
            print("| {} | {} | {} | {} | {:,.2f} | {:,.2f} | **{:.1f}%** |".format(
                NAME.get(s["magic"], s["magic"]), s["calls"], s["cut"], s["deny"],
                s["want"], s["got"], rate))
        print("| **合計** | {} | {} | **{}** | {:,.2f} | {:,.2f} | **{:.1f}%** |".format(
            tc, tcut, td, tw, tg, tg / tw * 100 if tw > 0 else 100.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
