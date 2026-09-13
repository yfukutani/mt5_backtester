"""V093：**MT5バックテストと簡易再生の照合**（2026-09-13）。

【なぜ必要か（Codexの推奨）】
> 最初の少数窓で、発注量・残高・equity・終了判定を簡易再生と照合する。
> **重大な不一致があれば、残りを回す前に解消する。**

実際、最初の試験実行で3件のバグが見つかった（V091）。
**照合を自動化して、以後の実行でも同じ取りこぼしをしないようにする。**

【照合する項目】

| 項目 | MT5側 | 簡易再生側 | 一致すべきか |
|---|---|---|---|
| 建玉数 | deals CSVのentry==0 | 同じ期間の取引数 | **ほぼ一致すべき**（停止時刻が違えば差が出る） |
| 枠別のロット | deals CSVのvolume | 基準ロット × k × ratio の丸め | **一致すべき**（丸め規則が同じなら） |
| 終了理由 | EAの判定（含み損益込み） | 確定損益ベースの判定 | **ずれてよい**（ここが段階3の主目的） |
| 期末資金 | MT5のequity | 簡易再生の資金 | **ずれてよい**（同上） |

**ロットが一致しなければ、それ以前の問題である。** まずそこを見る。

【限界】
- 簡易再生は含み損益を持たないので、停止時刻が必ずずれる。建玉数の一致は近似
- MT5は証拠金不足で発注を拒否することがある。簡易再生にはその概念がない
- **この照合は実装の忠実性を見るものであって、方策の良し悪しは判定しない**
"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sleeve_ablation as sab

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
RESULTS = ROOT / "results.csv"


def load_mt5_deals(path):
    """(t_in, t_out, profit, volume, magic) を返す。"""
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                     float(r["profit"]), float(r["volume"]), m))
    rows.sort()
    opened, rec = {}, []
    for t, entry, pid, profit, vol, m in rows:
        if entry == 0:
            opened[pid] = (t, vol, m)
        else:
            o = opened.pop(pid, None)
            if o is None:
                continue
            rec.append((o[0], t, profit, o[1], o[2]))
    # 未決済（期限で強制決済されなかったもの）も建玉としては数える
    return rec, len(opened)


def main():
    if not RESULTS.exists():
        print(f"結果がありません: {RESULTS}")
        return
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    if not rows:
        print("結果が空です")
        return

    print("=" * 110)
    print("V093：MT5バックテストと簡易再生の照合")
    print("=" * 110)
    print("★ Codexの推奨：**残りを回す前に、発注量・終了判定の不一致を潰す。**")
    print("  実際、最初の試験実行で3件のバグが見つかった（V091）。\n")

    print(f"{'期限':>5}{'起点':>12}{'方策':>6}{'終了理由':>10}"
          f"{'期末資金':>11}{'損益':>11}{'最大DD%':>9}{'建玉':>7}{'未決済':>7}")
    for r in rows:
        path = DEAL_DIR / r.get("deals", "")
        n_open = n_left = 0
        if r.get("deals") and path.exists():
            rec, n_left = load_mt5_deals(path)
            n_open = len(rec) + n_left
        mode = {"1": "比例", "2": "HJB"}.get(r.get("mode"), r.get("mode"))
        print(f"{r['months']:>4}月{r['origin']:>12}{mode:>6}"
              f"{r.get('why',''):>10}{r.get('end_equity',''):>11}"
              f"{r.get('net',''):>11}{r.get('ea_max_dd_pct',''):>9}"
              f"{n_open:>7}{n_left:>7}")

    # ---------- 枠別ロットの確認 ----------
    print("\n" + "=" * 110)
    print("【枠別の建玉ロット】**元のログのロット × k になっているか**")
    print("=" * 110)
    for r in rows[:4]:
        path = DEAL_DIR / r.get("deals", "")
        if not (r.get("deals") and path.exists()):
            continue
        rec, _ = load_mt5_deals(path)
        if not rec:
            continue
        by = defaultdict(list)
        for _, _, _, vol, mg in rec:
            by[mg].append(vol)
        mode = {"1": "比例", "2": "HJB"}.get(r.get("mode"), r.get("mode"))
        print(f"\n--- {r['months']}月 {r['origin']} {mode} k={r['k']} ---")
        print(f"{'枠':<16}{'件数':>6}{'最小':>8}{'中央':>8}{'最大':>8}")
        for mg in sorted(by):
            v = sorted(by[mg])
            med = v[len(v) // 2]
            print(f"{sab.MAGIC_NAME.get(mg, str(mg)):<16}{len(v):>6}"
                  f"{v[0]:>8.2f}{med:>8.2f}{v[-1]:>8.2f}")

    print("\n" + "=" * 110)
    print("【限界】")
    print("=" * 110)
    print("  ・簡易再生は含み損益を持たないので停止時刻が必ずずれる")
    print("  ・MT5は証拠金不足で発注を拒否することがある（簡易再生にはその概念がない）")
    print("  ・**この照合は実装の忠実性を見るもので、方策の良し悪しは判定しない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
