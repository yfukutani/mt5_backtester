"""weights.py の座標降下が見つけた重みが「配分」なのか「ただの増レバ」なのかを切り分ける。

座標降下は9枠中6枠をグリッド上限3.0まで上げて止まった。
これは**配分を変えたのではなく、全体を大きくしただけ**かもしれない。
だとすれば `GlobalLotMult` を上げるのと区別がつかず、新しい発見ではない。

切り分けは単純である。**全枠を一律 s 倍したもの**と**座標降下の重み**を並べ、
- 一律倍率でも同じ OOS 月利が出るなら → 配分ではなく増レバ。新規性なし
- 座標降下のほうが明確に上なら → 配分に意味がある

同時に、**cap がどれだけ効いているか**（削られた・捨てられた注文の割合）と
**最大ロット**を出す。cap が大半の注文に効いている領域では、
段階2の比例近似はいちばん当てにならない。**そこで出た数字は採用の根拠にしない。**
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("w", Path(__file__).parent / "weights.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
mcs = W.mcs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="T036")
    ap.add_argument("--cap", type=float, default=0.80)
    args = ap.parse_args()

    rows = mcs.load(REPO, args.id, "full")
    params, desc = mcs.params_of(REPO, args.id)
    comp = mcs.compounding_magics(params)

    # weights.py の座標降下が IS で選んだ重み（DD予算・ロット上限50を入れた版）
    OPT = {20260622: 0.3, 20260627: 1.0, 20260610: 2.0, 20260605: 4.0,
           20260774: 4.0, 20260629: 8.0, 20260650: 0.75, 20261000: 12.0,
           20261001: 12.0}
    # 上限張り付きを外した保守版（固定・小口枠を一律4倍まで）
    CONS = {20260622: 0.5, 20260627: 1.0, 20260610: 2.0, 20260605: 4.0,
            20260774: 4.0, 20260629: 4.0, 20260650: 0.75, 20261000: 4.0,
            20261001: 4.0}

    cases = [("一律 1.0（基準）", {m: 1.0 for m in W.SLEEVES}),
             ("一律 1.5", {m: 1.5 for m in W.SLEEVES}),
             ("一律 2.0", {m: 2.0 for m in W.SLEEVES}),
             ("一律 2.5", {m: 2.5 for m in W.SLEEVES}),
             ("一律 3.0", {m: 3.0 for m in W.SLEEVES}),
             ("IS最適重み（座標降下）", OPT),
             ("保守版（一律4倍まで）", CONS)]

    print(f"■ {args.id}  {desc}   cap={args.cap:.0%}")
    print("  equity は決済損益ベース＝含み損を含まない。段階2の簡易検証。\n")
    print("  %-22s %-4s %14s %8s %8s %10s %9s %11s"
          % ("", "窓", "純益", "月利", "最大DD", "最低資産", "最大lot", "捨てた注文"))
    for label, w in cases:
        for win in ("IS", "OOS"):
            t0, t1, _ = W.WINDOWS[win]
            s = W.simulate(rows, comp, w, args.cap, t0, t1)
            print("  %-22s %-4s %14s %7.2f%% %7.1f%% %10s %9.2f %6d/%-5d"
                  % (label, win, format(round(s["net"]), ","), s["geo"],
                     s["dd"] * 100, format(round(s["min_eq"]), ","),
                     s["max_lot"], s["dropped"], s["opened"]))
        print()

    print("注: 「捨てた注文」は cap が空き証拠金を使い切り、最小ロットにも届かなかった発注。")
    print("    この割合が大きい領域では比例近似がいちばん当てにならない。")
    print("    段階2の簡易検証であり、採用の根拠にはしない。")


if __name__ == "__main__":
    main()
