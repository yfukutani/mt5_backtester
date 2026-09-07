"""上位案の中身を検査する — 第2セッションの利益が広く分布しているか。

【なぜ必要か】これまでのラウンドで、大きな数字を出した案が
「改善の6割が1件」「悪化建玉のほうが多い」という中身だったことが複数回あった
（docs/sca_gold_exit_20260904.md §4）。採否の前に必ず中身を見る。

第2セッションは枠を**追加**するので、既存枠と建玉集合を比べる意味はない。
代わりに次を見る:
  1. 第2セッション自身の損益分布（勝ち負けの件数・上位1件/3件の寄与）
  2. 年ごとの符号（特定の年だけで稼いでいないか）
  3. SCA第1が食われた分（共食い）
  4. 平均保有時間と決済時刻の分布（設計どおりに動いているか）
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
MAG = {20260640: "PB GOLD", 20261002: "SCA第1", 20261003: "SCA第2"}


def trades(path, magic):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["magic"]) != magic:
            continue
        pid = int(r["position_id"])
        if r["entry"] == "0":
            ins[pid] = r
        else:
            outs[pid].append(r)
    out = []
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        t_in = datetime.fromtimestamp(int(i["time"]), timezone.utc)
        t_out = datetime.fromtimestamp(max(int(x["time"]) for x in o), timezone.utc)
        out.append({
            "in": t_in, "out": t_out,
            "profit": sum(float(x["profit"]) for x in o),
            "hold_h": (t_out - t_in).total_seconds() / 3600.0,
            "vol": float(i["volume"]),
        })
    out.sort(key=lambda x: x["in"])
    return out


def report(run_id, label, base_sca1):
    path = DEAL_DIR / f"{run_id}_deals.csv"
    if not path.exists():
        print(f"{label}: dealログなし ({run_id})")
        return
    t2 = trades(path, 20261003)
    if not t2:
        print(f"{label}: 第2セッションの取引なし")
        return
    net = sum(x["profit"] for x in t2)
    wins = [x for x in t2 if x["profit"] > 0]
    losses = [x for x in t2 if x["profit"] <= 0]
    gains = sorted((x["profit"] for x in wins), reverse=True)

    per_year = defaultdict(float)
    for x in t2:
        per_year[x["in"].year] += x["profit"]
    y_pos = sum(1 for v in per_year.values() if v > 0)
    y_neg = sum(1 for v in per_year.values() if v < 0)

    hours = defaultdict(int)
    for x in t2:
        hours[x["out"].hour] += 1

    sca1 = sum(x["profit"] for x in trades(path, 20261002))
    canni = sca1 - base_sca1

    print(f"\n{'='*72}\n{label}\n{'='*72}")
    print(f"第2セッション: {len(t2)}取引  純益 {net:>10,.0f} 円  "
          f"勝ち {len(wins)} / 負け {len(losses)}  勝率 {100*len(wins)/len(t2):.1f}%")
    print(f"  上位1件の寄与 {100*gains[0]/net:>6.1f}%   "
          f"上位3件 {100*sum(gains[:3])/net:>6.1f}%   "
          f"上位5件 {100*sum(gains[:5])/net:>6.1f}%")
    print(f"  平均保有 {sum(x['hold_h'] for x in t2)/len(t2):.1f}h   "
          f"平均ロット {sum(x['vol'] for x in t2)/len(t2):.3f}")
    print(f"  年次: 黒字{y_pos}年 / 赤字{y_neg}年  "
          + " ".join(f"{y}:{v:+,.0f}" for y, v in sorted(per_year.items())))
    print(f"  決済時刻(UTC)の上位: "
          + ", ".join(f"{h}時 {c}件" for h, c in sorted(hours.items(), key=lambda kv: -kv[1])[:4]))
    print(f"SCA第1の共食い: {canni:>+10,.0f} 円  "
          f"→ 正味の寄与 {net + canni:>+10,.0f} 円")


if __name__ == "__main__":
    import json
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["status"] == "OK"]
    base_sca1 = {"IS": 182650.0, "OOS": 55851.0}
    targets = sys.argv[1:] or ["S2057", "S2020", "S2010"]
    for pid in targets:
        for w in ("IS", "OOS"):
            r = next((x for x in rows if x["proposal_id"] == pid and x["window"] == w), None)
            if r:
                report(r["run_id"], f"{pid} [{w}] {r['description']}", base_sca1[w])
