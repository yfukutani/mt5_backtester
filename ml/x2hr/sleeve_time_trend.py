"""V040：ブックの期待値の時間トレンドを、枠別に分解する。

【なぜ調べるのか】
V039の追試で、ブックの1取引あたり期待値が **2018年 −48.3円 → 2026年 1,281.3円** と
一貫して上昇していることが分かった。上昇の原因は次のどれか分離できていない。

1. **枠の開発・調整が近年のデータに対して行われてきた**（＝過学習）
2. **相場環境が実際に有利だった**（暗号資産・GOLDの上昇局面）
3. 両方

【切り分けの考え方】
- 原因1（過学習）なら、**全枠が一様に近年で良くなる**はず。パラメータは全枠とも
  近年データで調整されているため
- 原因2（相場環境）なら、**上昇は特定の銘柄・枠に集中する**はず。
  暗号資産（BTC/ETH）とGOLDは2021年以降に大きく上昇しており、その枠だけが伸びる
- また、**枠の稼働開始時期**も効く。近年に追加された枠は古い期間のデータを持たないため、
  ブック全体の平均を近年側へ押し上げる（＝**構成の変化**による見かけの上昇）

本スクリプトは枠別・年別の1取引あたり損益を出し、この3つを見分ける材料を作る。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl
from sleeve_ablation import MAGIC_NAME

SYMBOL_OF = {
    20260622: "USDJPY", 20260627: "GBPJPY", 20260628: "AUDJPY", 20260640: "GOLD",
    20260610: "USDJPY", 20260605: "EURUSD", 20260774: "GBPUSD", 20260650: "AUDJPY",
    20260680: "USDJPY", 20260710: "ETHUSD", 20261000: "USDJPY", 20261001: "GBPJPY",
    20261002: "GOLD", 20261003: "GOLD", 20260720: "BTCUSD", 20260629: "PAIR",
}
CRYPTO = {"ETHUSD", "BTCUSD"}


def load_full():
    fx, gold = dkl.resolve_runs()
    rows = []
    for src in (fx.get("FULL"), gold.get("FULL")):
        if src is None:
            continue
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            p = float(r["profit"])
            if m == 0 or p == 0.0:
                continue
            y = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).year
            rows.append((y, m, p))
    return rows


def main():
    rows = load_full()
    years = sorted({y for y, _, _ in rows})
    magics = sorted({m for _, m, _ in rows})

    print("=" * 118)
    print("V040：ブックの期待値の時間トレンドを枠別に分解する")
    print("=" * 118)

    by = defaultdict(list)
    for y, m, p in rows:
        by[(m, y)].append(p)

    print("\n【枠別・年別の1取引あたり平均損益（円）】")
    hdr = f"{'枠':>16}{'銘柄':>9}"
    for y in years:
        hdr += f"{y:>8}"
    print(hdr)
    for m in magics:
        line = f"{MAGIC_NAME.get(m, str(m)):>16}{SYMBOL_OF.get(m, '?'):>9}"
        for y in years:
            v = by.get((m, y))
            line += f"{np.mean(v):>8.0f}" if v else f"{'—':>8}"
        print(line)

    print("\n【枠別・年別の取引数】（稼働開始時期と構成の変化を見る）")
    hdr = f"{'枠':>16}{'銘柄':>9}"
    for y in years:
        hdr += f"{y:>8}"
    print(hdr)
    for m in magics:
        line = f"{MAGIC_NAME.get(m, str(m)):>16}{SYMBOL_OF.get(m, '?'):>9}"
        for y in years:
            v = by.get((m, y))
            line += f"{len(v):>8}" if v else f"{'—':>8}"
        print(line)

    # --- 分解1：暗号資産を除いたらトレンドは消えるか ---
    print("\n【分解1：暗号資産（BTC/ETH）を除いた場合】")
    print(f"{'年':>6}{'全枠 取引':>10}{'全枠 平均':>11}"
          f"{'暗号除く 取引':>14}{'暗号除く 平均':>14}{'暗号の寄与':>12}")
    for y in years:
        allp = [p for yy, m, p in rows if yy == y]
        nocr = [p for yy, m, p in rows if yy == y and SYMBOL_OF.get(m) not in CRYPTO]
        if not allp:
            continue
        a, b = float(np.mean(allp)), (float(np.mean(nocr)) if nocr else 0.0)
        print(f"{y:>6}{len(allp):>10}{a:>11.0f}{len(nocr):>14}{b:>14.0f}{a-b:>12.0f}")

    # --- 分解2：GOLDも除く ---
    print("\n【分解2：暗号資産＋GOLDを除いた場合（＝FX枠だけ）】")
    print(f"{'年':>6}{'FX枠 取引':>11}{'FX枠 平均':>11}{'FX枠 シャープ':>14}")
    for y in years:
        fxp = [p for yy, m, p in rows
               if yy == y and SYMBOL_OF.get(m) not in CRYPTO | {"GOLD"}]
        if len(fxp) < 2:
            continue
        a = np.array(fxp)
        sd = a.std(ddof=1)
        print(f"{y:>6}{len(fxp):>11}{a.mean():>11.0f}{(a.mean()/sd if sd else 0):>14.4f}")

    # --- 分解3：全期間稼働している枠だけに絞る ---
    print("\n【分解3：全期間（全年）稼働している枠だけ】（構成の変化を除く）")
    full_run = [m for m in magics if all(by.get((m, y)) for y in years)]
    print("  対象枠: " + (", ".join(MAGIC_NAME.get(m, str(m)) for m in full_run)
                        if full_run else "なし"))
    if full_run:
        print(f"{'年':>6}{'取引':>8}{'平均円':>10}{'シャープ':>11}")
        for y in years:
            v = [p for yy, m, p in rows if yy == y and m in full_run]
            if len(v) < 2:
                continue
            a = np.array(v)
            sd = a.std(ddof=1)
            print(f"{y:>6}{len(a):>8}{a.mean():>10.0f}{(a.mean()/sd if sd else 0):>11.4f}")

    print("\n" + "=" * 118)
    print("【読み方】")
    print("=" * 118)
    print("  ・暗号/GOLDを除いてもトレンドが残るなら、原因は相場環境だけではない")
    print("  ・全期間稼働の枠だけに絞ってもトレンドが残るなら、構成の変化でもない")
    print("  ・その場合に残る説明は『枠の調整が近年データに対して行われた』＝過学習")
    print("\n完了。")


if __name__ == "__main__":
    main()
