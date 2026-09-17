"""SCA枠の「SL距離」と1取引の損益の関係を見る（段階2・採用の根拠にはしない）。

【なぜ見るか】
T003（SCA USDJPY を risk 0.5% 化）で、この枠の FULL 純益が
**+16,339円 → −5,881円**へ転落した。取引数は594で完全に同じ。
**サイジングを変えただけで黒字が赤字になった。**

risk% サイジングは `ロット = リスク額 ÷ (SL距離 × 契約サイズ)` なので、
**SL距離が短い取引ほど大きいロットになる。** SCAのSL距離はアジア時間のレンジ幅
そのものなので、これは「**レンジが狭い日ほど大きく賭ける**」ことを意味する。

X2_HIGH_RISK の V105 は SCA GBPJPY で、**レンジ幅が最小25%の取引は1取引あたりの
シャープがマイナス**（IS −0.0042 / 弱局面 −0.0112）、最大25%が最良（+0.1437 / +0.0738）
と測っていた。つまり **risk%化は、いちばん負ける取引にいちばん大きく賭ける。**

本スクリプトは、その関係が OANDA FX の SCA 2枠でも成り立つかを固定ロットの
基準run（T001）で確かめる。

【限界】
- 固定ロット0.01の損益を見ているので、1取引の損益＝1ロットあたりの損益に比例する。
- Revブースト（USDJPY ×2 / GBPJPY ×6）が効いた取引はロットが2倍・6倍になっている。
  ここでは分けずに合算する（ブースト込みの実績が知りたいため）。
- **段階2の簡易検証であり、採用の根拠にはしない。**
"""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCA = {20261000: "SCA USDJPY", 20261001: "SCA GBPJPY"}


def latest(pattern):
    """T001 は fxrisk2 の S001 から転記しているので、そちらも探す。"""
    for d, pat in ((ROOT / "run_deals", pattern),
                   (ROOT.parent / "fxrisk2" / "run_deals",
                    pattern.replace("ft_", "fs_").replace("T001", "S001"))):
        hits = sorted(d.glob(pat))
        if hits:
            return hits[-1]
    raise SystemExit(f"deal ログが見つかりません: {pattern}")


def main():
    path = latest("ft_full_T001_*_deals.csv")
    print(f"基準run: {path.name}（固定ロット0.01・FULL窓115か月）\n")

    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    # position_id で IN と OUT を突き合わせる
    entry = {}
    for r in rows:
        m = int(r["magic"])
        if m not in SCA:
            continue
        if r["entry"] == "0":
            price, sl = float(r["price"]), float(r["sl"])
            if sl > 0 and price > 0:
                entry[r["position_id"]] = abs(price - sl)
        else:
            dist = entry.pop(r["position_id"], None)
            if dist is None:
                continue
            SAMPLES[m].append((dist, float(r["profit"])))

    for magic, name in SCA.items():
        s = SAMPLES[magic]
        if not s:
            print(f"{name}: 突き合わせできた取引なし")
            continue
        s.sort()
        n = len(s)
        q = n // 4
        print(f"=== {name}（{n}取引）===")
        print("SL距離＝アジア時間のレンジ幅。risk%化すると距離が短いほどロットが大きくなる。")
        print(f"{'層':<12}{'件数':>6}{'SL距離の中央値':>16}{'合計損益':>12}"
              f"{'1取引平均':>11}{'勝率':>8}")
        buckets = [("最小25%", s[:q]), ("25-50%", s[q:2 * q]),
                   ("50-75%", s[2 * q:3 * q]), ("最大25%", s[3 * q:])]
        for label, b in buckets:
            if not b:
                continue
            tot = sum(p for _, p in b)
            win = sum(1 for _, p in b if p > 0) / len(b)
            print(f"{label:<12}{len(b):>6}{statistics.median(d for d, _ in b):>16.5f}"
                  f"{tot:>12,.0f}{tot / len(b):>11,.0f}{100 * win:>7.1f}%")
        # risk%化したときの重みづけを模擬する（ロット ∝ 1/SL距離）
        base = statistics.median(d for d, _ in s)
        weighted = sum(p * (base / d) for d, p in s)
        print(f"  固定ロットの合計損益            {sum(p for _, p in s):>12,.0f} 円")
        print(f"  ロット∝1/SL距離 に置き換えた合計 {weighted:>12,.0f} 円"
              "   ← risk%化の向きを模擬")
        print()

    print("注: 右の模擬値は丸め・証拠金・ブーストを無視した粗い近似であり、")
    print("    MT5バックテストの代わりにはならない。向きの確認だけに使う。")
    print("    段階2の簡易検証であり、採用の根拠にはしない。")


SAMPLES = defaultdict(list)

if __name__ == "__main__":
    main()
