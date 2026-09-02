"""決済理由を分類し、利確タイミング側の余地を定量化する。

SCA GOLD は負けの大半がSL到達ではなく20:00強制決済であり、勝ちもTP(1.7R)に届かず
切られている。「守り」ではなく「利確位置」の問題がどれだけの規模かを測る。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

MAGIC_NAME = {20260640: "PB GOLD", 20261002: "SCA GOLD"}
RR = {20260640: 1.8, 20261002: 1.7}


def build(path):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        pid = int(r["position_id"])
        rec = {k: r[k] for k in r}
        (ins if r["entry"] == "0" else outs[pid]).__setitem__(pid, rec) \
            if r["entry"] == "0" else outs[pid].append(rec)
    trades = []
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        entry = float(i["price"]); sl = float(i["sl"])
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        is_buy = int(i["type"]) == 0
        vol = sum(float(x["volume"]) for x in o)
        exit_px = sum(float(x["price"]) * float(x["volume"]) for x in o) / vol
        realized = (exit_px - entry) if is_buy else (entry - exit_px)
        t_out = max(int(x["time"]) for x in o)
        trades.append({
            "magic": int(i["magic"]), "r": realized / risk,
            "profit": sum(float(x["profit_jpy"]) for x in o),
            "risk": risk, "entry_t": int(i["time"]), "exit_t": t_out,
            "exit_hour": datetime.fromtimestamp(t_out, timezone.utc).hour,
        })
    return trades


def classify(t):
    rr = RR.get(t["magic"], 1.7)
    if t["r"] <= -0.95:
        return "SL到達"
    if t["r"] >= rr - 0.05:
        return "TP到達"
    return "途中決済"


def main(path, label):
    trades = build(path)
    print(f"\n{'='*76}\n{label}\n{'='*76}")
    for magic in sorted({t["magic"] for t in trades}):
        g = [t for t in trades if t["magic"] == magic]
        print(f"\n--- {MAGIC_NAME.get(magic, magic)}  {len(g)}件 ---")
        print(f"{'決済理由':<10}{'件数':>6}{'損益合計(円)':>16}{'平均R':>9}{'平均保有h':>11}")
        buckets = defaultdict(list)
        for t in g:
            buckets[classify(t)].append(t)
        for k in ("TP到達", "SL到達", "途中決済"):
            b = buckets.get(k, [])
            if not b:
                continue
            hold = sum((t["exit_t"] - t["entry_t"]) / 3600 for t in b) / len(b)
            print(f"{k:<10}{len(b):>6}{sum(t['profit'] for t in b):>16,.0f}"
                  f"{sum(t['r'] for t in b)/len(b):>9.2f}{hold:>11.1f}")

        mid = buckets.get("途中決済", [])
        if mid:
            plus = [t for t in mid if t["r"] > 0]
            minus = [t for t in mid if t["r"] <= 0]
            print(f"\n  途中決済の内訳: 含み益あり {len(plus)}件 "
                  f"(平均 +{sum(t['r'] for t in plus)/max(1,len(plus)):.2f}R / "
                  f"{sum(t['profit'] for t in plus):+,.0f}円)  "
                  f"含み損 {len(minus)}件 "
                  f"(平均 {sum(t['r'] for t in minus)/max(1,len(minus)):.2f}R / "
                  f"{sum(t['profit'] for t in minus):+,.0f}円)")
            hours = defaultdict(int)
            for t in mid:
                hours[t["exit_hour"]] += 1
            top = sorted(hours.items(), key=lambda kv: -kv[1])[:4]
            print("  途中決済が集中する時刻(UTC): " +
                  ", ".join(f"{h}時 {c}件" for h, c in top))
            # TPまで伸ばせていたら、という上限値（実際には届かないが余地の規模を示す）
            rr = RR.get(magic, 1.7)
            gap = sum((rr - t["r"]) * abs(t["profit"] / t["r"]) for t in plus if t["r"] > 0.01)
            print(f"  参考: 含み益ありの途中決済がTP({rr}R)まで伸びた場合の上限差 "
                  f"約 {gap:+,.0f}円（到達率を無視した理論上限）")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
