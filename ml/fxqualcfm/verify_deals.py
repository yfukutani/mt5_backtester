"""R001 FULL と F000 FULL の deal ログを1対1で突き合わせ、差が Carry だけかを自分で確かめる。

並行セッションの主張:
  「時刻・magic・方向・ロット・価格・SL は全 deal で一致。違うのは損益だけ。
   動いたのは Carry AUDJPY の −4,070 円だけで、他の8枠はちょうど ±0。」

枠別 CSV（results.csv）で見ると **Carry が +49,163・Pair が −45** と出るので、
そのままでは主張と食い違う。**第16報の配賦修正（窓末の建玉を position_id から
建玉時 magic へ引き直す）が入っているかどうかが、2つのラウンドで違う**からである。
deal ログで直接比べれば、その交絡は入らない。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


def load(path: Path):
    return list(csv.DictReader(path.open(encoding="utf-8", errors="ignore")))


def key(r):
    return (r["time"], r["magic"], r["entry"], r["type"], r["volume"], r["price"])


def main():
    a_path, b_path = Path(sys.argv[1]), Path(sys.argv[2])
    a, b = load(a_path), load(b_path)
    print(f"A: {a_path.name}  {len(a)} deals")
    print(f"B: {b_path.name}  {len(b)} deals")
    if len(a) != len(b):
        print("⚠️ deal 数が違う。1対1で並べられない")
        return

    diff_by_magic = defaultdict(float)
    n_mismatch_key = 0
    n_diff_profit = 0
    for ra, rb in zip(a, b):
        if key(ra) != key(rb):
            n_mismatch_key += 1
            if n_mismatch_key <= 3:
                print("  key 不一致:", key(ra), "vs", key(rb))
            continue
        d = float(rb["profit"]) - float(ra["profit"])
        if d != 0.0:
            n_diff_profit += 1
            diff_by_magic[ra["magic"]] += d

    print(f"key 不一致: {n_mismatch_key} 件（0 なら約定は完全に同じ）")
    print(f"損益が違う deal: {n_diff_profit} 件")
    print("\n差の内訳（magic 別・円）:")
    for m, d in sorted(diff_by_magic.items(), key=lambda x: -abs(x[1])):
        print(f"  magic {m:>10}  {d:>12,.2f}")
    print(f"  {'合計':>16}  {sum(diff_by_magic.values()):>12,.2f}")


if __name__ == "__main__":
    main()
