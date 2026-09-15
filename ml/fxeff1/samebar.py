# -*- coding: utf-8 -*-
"""Codex #1「退出を先、参入を後に」— 決済と発注が同じ足に同居する頻度（MT5不要）。

`OnTick()` は `S[]` の固定順に、各枠の管理と新規発注をまとめて処理する。
後順位の枠が同じバーで決済して空けた証拠金を、先順位の枠は使えない。
**構造としての取りこぼしは実在する。**

> [!warning] **これは上界ではない。**
> 最初「上界を測った」と書いたが誤りである。#1 が拾おうとしているのは
> **cap に見送られて deal ログに存在しない注文**であり、
> **存在しないものはここから数えられない。**
> ここで数えているのは「**実際に約定した**発注のうち、同じ足に別枠の決済が同居していたもの」——
> つまり**ロットをもっと大きくできたかもしれない注文**だけである。
>
> 見送られた注文まで含めた判定は、EA の cap 計装（`ml/fxinstr1/`）が
> **削られた注文を1件ずつ時刻つきで残す**ので、そちらで行う。
"""
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from margin_efficiency import NAME, positions  # noqa: E402

BASE = ROOT.parent / "fxwin1" / "run_deals"
CAP25 = ROOT.parent / "fxcap25" / "run_deals"
DEPOSIT = 500_000
BAR = 15 * 60          # 発注判定は M15 足で回る


def find(pattern, base):
    hits = sorted(base.glob(pattern))
    return hits[0] if hits else None


def analyse(path, label, cap_pct):
    pos = positions(path)
    if not pos:
        return
    # 証拠金の時系列（決済損益ベースの equity と、使用証拠金）
    ev = []
    for magic, margin, _h, profit, t_in, t_out in pos:
        ev.append((t_in, "in", margin, magic, 0.0))
        ev.append((t_out, "out", -margin, magic, profit))
    ev.sort(key=lambda e: e[0])

    # バーごとに「決済のあった枠」「発注のあった枠」を集める
    bars_out = defaultdict(set)
    bars_in = defaultdict(list)
    for t, kind, _dm, magic, _p in ev:
        b = t - (t % BAR)
        if kind == "out":
            bars_out[b].add(magic)
        else:
            bars_in[b].append((t, magic))

    # 使用証拠金/equity を時系列で追い、各発注時点の逼迫度を出す
    equity = float(DEPOSIT)
    used = 0.0
    util_at = {}
    for t, kind, dm, _magic, profit in ev:
        if kind == "in":
            util_at[(t, _magic)] = (used / equity * 100.0) if equity > 0 else 0.0
            used += dm
        else:
            used += dm
            equity += profit

    n_in = sum(len(v) for v in bars_in.values())
    same_bar = 0
    same_bar_tight = 0
    tight = 0
    for b, ins in bars_in.items():
        outs = bars_out.get(b, set())
        for t, magic in ins:
            u = util_at.get((t, magic), 0.0)
            is_tight = (cap_pct > 0 and u >= cap_pct * 0.8)
            if is_tight:
                tight += 1
            others = outs - {magic}
            if others:
                same_bar += 1
                if is_tight:
                    same_bar_tight += 1
    print("| {} | {} | {} ({:.1f}%) | {} ({:.1f}%) | **{} ({:.1f}%)** |".format(
        label, n_in,
        tight, tight / n_in * 100,
        same_bar, same_bar / n_in * 100,
        same_bar_tight, same_bar_tight / n_in * 100))


def main():
    print("# Codex #1 — 決済と発注が同じ足に同居する頻度（X005・1:25）")
    print("")
    print("「逼迫」＝発注時点の 使用証拠金/equity が cap の 80% 以上。")
    print("「同バー決済あり」＝同じ M15 足の中に**別の枠**の決済がある。")
    print("")
    print("**注意: これは #1 の上界ではない。** 見送られた注文は deal ログに存在しないので数えられない。")
    print("ここで数えているのは**約定した注文のうちロットを増やせたかもしれないもの**だけである。")
    print("")
    print("| run | 発注数 | 逼迫 | 同バー決済あり | **両方** |")
    print("|---|---:|---:|---:|---:|")
    for w in ("w1", "w2", "w3"):
        p = find(f"mc_{w}_X005_*_deals.csv", BASE)
        if p:
            analyse(p, "X005 " + w.upper() + " (cap80)", 80)
    for pid, cap in (("Y100", 100), ("Y090", 90), ("Y060", 60)):
        for w in ("w1", "w2", "w3", "oos"):
            p = find(f"mc_{w}_{pid}_*_deals.csv", CAP25)
            if p:
                analyse(p, f"{pid} {w.upper()} (cap{cap})", cap)
    print("")
    print("> 見送られた注文は deal ログに無いので、ここには現れない。")
    print("> 判定は cap 計装（削られた注文を1件ずつ時刻つきで残す）で行う。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
