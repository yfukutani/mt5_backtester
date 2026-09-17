# -*- coding: utf-8 -*-
"""ロット上限(50.00)は、判定に使っている24か月窓にも効いているか。

`volcheck.py` で、入金2000万の run は RSI 3枠の 95〜99% が
**業者のロット上限 50.00 に張り付いていた**ことが分かった。
つまり大口座の run は戦略ではなく「毎回50ロット」を測っていた。

では**判定に使っている W1〜W3（新規50万円・24か月）**はどうなのか。
W1 は最終資産 7.1M まで増えるので、後半は上限に触れうる。
**判定の土台が汚れていないかを確かめる。**
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN1 = ROOT.parent / "fxwin1" / "run_deals"
CAP25 = ROOT.parent / "fxcap25" / "run_deals"
VMAX = 50.0
MAGICS = {20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
          20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
          20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ"}


def entries(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["entry"]) != 0:
            continue
        m = int(r["magic"])
        if m in MAGICS:
            out.append((m, float(r["volume"]), int(r["time"])))
    return out


def report(label, path):
    es = entries(path)
    if not es:
        return
    hit = [e for e in es if abs(e[1] - VMAX) < 1e-9]
    pct = len(hit) / len(es) * 100
    # 上限に当たった最初の時刻（＝それ以降は戦略ではなく上限を測っている）
    first = min((e[2] for e in hit), default=None)
    from datetime import datetime, timezone
    fs = datetime.fromtimestamp(first, tz=timezone.utc).strftime("%Y-%m") if first else "—"
    per = {}
    for m in MAGICS:
        sub = [e for e in es if e[0] == m]
        if not sub:
            continue
        h = sum(1 for e in sub if abs(e[1] - VMAX) < 1e-9)
        per[m] = h / len(sub) * 100
    worst = sorted(per.items(), key=lambda kv: -kv[1])[:3]
    ws = " / ".join("{} {:.0f}%".format(MAGICS[m], v) for m, v in worst if v > 0) or "なし"
    print("| {} | {} | {} | **{:.1f}%** | {} | {} |".format(
        label, len(es), len(hit), pct, fs, ws))


def main():
    print("# ロット上限(50.00)は判定窓に効いているか")
    print("")
    print("| run | 発注数 | 上限に張り付いた数 | 割合 | 最初に当たった月 | 枠別の上位 |")
    print("|---|---:|---:|---:|---|---|")
    for w in ("w1", "w2", "w3", "w4", "w5", "w6", "w7", "w8", "w9"):
        hits = sorted(WIN1.glob(f"mc_{w}_X005_*_deals.csv"))
        if hits:
            report("X005 " + w.upper(), hits[0])
    for pid in ("Y100", "Y090", "Y060"):
        for w in ("w1", "w2", "w3", "oos"):
            hits = sorted(CAP25.glob(f"mc_{w}_{pid}_*_deals.csv"))
            if hits:
                report(f"{pid} {w.upper()}", hits[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
