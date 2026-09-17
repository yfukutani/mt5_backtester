"""`ml/fxqual2` の deals を、発火理由（注文コメント）で割る。

【先に回帰試験】
T000 の 純益・DD・取引数が fxqual1 の Q000 と一致するかを最初に出す。
**一致しないなら以下の内訳は読んではいけない**（タグ付けが売買を変えている）。

【出すもの】
1. RSI 3枠 × 機構（R=RSI反転 / B=BB回帰 / D=ダブルボトム、同時発火は "RB" 等）
   取引数・勝率・ΣR・平均R・純益を OOS/IS 別に。
   R倍率 = (決済価格 - 建値) / |建値 - SL|（売りは符号反転）。ロットに依存しない。
2. Pair の参入時 z の分布と、**参入時点で既に |z| >= stopZ(5.0) だった件数**（Codex #23）。
   その群の成績が他と違うかどうか。

【R倍率の注意】
`profit_jpy` 列は円口座では二重換算なので使わない（第14報で踏んだ）。純益は `profit` を使う。
"""
from __future__ import annotations

import collections
import csv
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
DEALS = ROOT / "run_deals"

RSI_MAGIC = {20260610: "RSI_UJ", 20260605: "RSI_EU", 20260774: "RSI_GU"}
PAIR_MAGIC = None          # 下で results から拾えないので、コメントで判別する
STOP_Z = 5.0
ENTRY_Z = 4.0


def rows_of(run_id):
    p = DEALS / f"{run_id}_deals.csv"
    if not p.exists():
        return []
    return list(csv.DictReader(open(p, encoding="utf-8")))


def positions(deals):
    """position_id で建て(entry=0)と決済(entry=1)を組にする。"""
    byp = collections.defaultdict(list)
    for d in deals:
        byp[d["position_id"]].append(d)
    out = []
    for pid, ds in byp.items():
        ds.sort(key=lambda r: int(r["time"]))
        op = [d for d in ds if d["entry"] == "0"]
        cl = [d for d in ds if d["entry"] == "1"]
        if not op or not cl:
            continue
        out.append((op[0], cl[-1], sum(float(d["profit"]) for d in ds)))
    return out


def r_multiple(o, c):
    try:
        ep, sl, xp = float(o["price"]), float(o["sl"]), float(c["price"])
    except (KeyError, ValueError):
        return None
    if sl <= 0:
        return None
    risk = abs(ep - sl)
    if risk <= 0:
        return None
    sign = 1.0 if o["type"] == "0" else -1.0    # 0=buy 1=sell
    return sign * (xp - ep) / risk


def regression_check(res2, res1):
    print("## 0. 回帰試験（タグ付けが売買を変えていないこと）\n")
    print("| 窓 | fxqual1 Q000 純益 | fxqual2 T000 純益 | 差 | Q000 取引 | T000 取引 | 判定 |")
    print("|---|---:|---:|---:|---:|---:|---|")
    ok = True
    for w in ("OOS", "IS"):
        a, b = res1.get(("Q000", w)), res2.get(("T000", w))
        if not a or not b:
            print(f"| {w} | — | — | — | — | — | 片方が未完了 |")
            ok = False
            continue
        dn = float(b["net"]) - float(a["net"])
        dt = int(float(b["trades"])) - int(float(a["trades"]))
        v = "一致" if abs(dn) < 1 and dt == 0 else "**不一致（内訳を読んではいけない）**"
        if "不一致" in v:
            ok = False
        print(f"| {w} | {float(a['net']):+,.0f} | {float(b['net']):+,.0f} | {dn:+,.0f} "
              f"| {int(float(a['trades']))} | {int(float(b['trades']))} | {v} |")
    print()
    return ok


def rsi_split(deals, label):
    print(f"\n### {label}\n")
    print("| 枠 | 発火機構 | 取引 | 勝率% | ΣR | 平均R | 中央R | 純益 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    agg = collections.defaultdict(list)
    for o, c, pnl in positions(deals):
        m = int(o["magic"])
        if m not in RSI_MAGIC:
            continue
        tag = (o.get("comment") or "").strip()
        mech = tag.split(":", 1)[1] if ":" in tag else "(タグ無し)"
        agg[(RSI_MAGIC[m], mech)].append((r_multiple(o, c), pnl))
    for key in sorted(agg):
        v = agg[key]
        rs = [r for r, _ in v if r is not None]
        pn = [p for _, p in v]
        wins = sum(1 for p in pn if p > 0)
        print(f"| {key[0]} | {key[1]} | {len(v)} | {100*wins/len(v):.1f} "
              f"| {sum(rs):+.1f} | {statistics.mean(rs):+.3f} "
              f"| {statistics.median(rs):+.3f} | {sum(pn):+,.0f} |"
              if rs else
              f"| {key[0]} | {key[1]} | {len(v)} | {100*wins/len(v):.1f} "
              f"| — | — | — | {sum(pn):+,.0f} |")


def pair_z(deals, label):
    print(f"\n### {label}\n")
    zs, breach, normal = [], [], []
    for o, c, pnl in positions(deals):
        tag = (o.get("comment") or "")
        m = re.search(r"z=(-?\d+\.\d+)", tag)
        if not m or "Pair" not in tag:
            continue
        z = float(m.group(1))
        zs.append(z)
        (breach if abs(z) >= STOP_Z else normal).append(pnl)
    if not zs:
        print("> Pair のタグ付き取引が無い。計装が効いていないか、Pair枠が建っていない。")
        return
    az = [abs(z) for z in zs]
    print(f"- Pair の脚（建玉）: **{len(zs)}件**（両脚あるので取引は約半分）")
    print(f"- 参入時 |z| の分布: 最小 {min(az):.2f} / 中央 {statistics.median(az):.2f} "
          f"/ 最大 {max(az):.2f}（entryZ={ENTRY_Z} / stopZ={STOP_Z}）")
    print(f"- **参入時点で既に |z| >= stopZ({STOP_Z}) だった脚: {len(breach)}件 "
          f"({100*len(breach)/len(zs):.1f}%)** ← Codex #23 が避けたい領域")
    if breach:
        print(f"  - その群の純益: {sum(breach):+,.0f}円（1件あたり {statistics.mean(breach):+,.0f}円）")
    if normal:
        print(f"  - それ以外の群の純益: {sum(normal):+,.0f}円"
              f"（1件あたり {statistics.mean(normal):+,.0f}円）")
    if breach and normal:
        if sum(breach) < 0 < sum(normal):
            print("  - → **その領域を避ける案（Codex #23）は測る価値がある。**")
        else:
            print("  - → 避けても改善にならない可能性が高い。数字で確認すること。")


def load_results(path):
    if not path.exists():
        return {}
    return {(r["proposal_id"], r["window"]): r
            for r in csv.DictReader(open(path, encoding="utf-8"))
            if r.get("status") == "OK"}


def main():
    res2 = load_results(ROOT / "results.csv")
    res1 = load_results(REPO / "ml" / "fxqual1" / "results.csv")
    if not res2:
        sys.exit("fxqual2 の results.csv がまだ無い。")

    print("# fxqual2 — 発火理由の内訳（第15報）\n")
    if not regression_check(res2, res1):
        print("> **回帰試験が通っていないので、以下は参考値である。**\n")

    print("## 1. RSI 3枠を発火機構で割る\n")
    print("> R=RSI反転 / B=ボリンジャー回帰 / D=ダブルボトム。"
          "同じ足で複数成立しうるので連結タグ（例 `RB`）が出る。"
          "**同時発火を別の群として扱う**——どちらか片方に按分すると"
          "「単独で勝つ機構」が見えなくなるため。\n")
    for w in ("OOS", "IS"):
        r = res2.get(("T000", w))
        if r:
            rsi_split(rows_of(r["run_id"]), f"{w}窓")

    print("\n## 2. Pair の参入時 z（Codex #23）\n")
    for w in ("OOS", "IS"):
        r = res2.get(("T000", w))
        if r:
            pair_z(rows_of(r["run_id"]), f"{w}窓")


if __name__ == "__main__":
    main()
