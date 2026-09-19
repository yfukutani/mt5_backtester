"""各 run の「建玉後の最小証拠金維持率」を集める（第17報・2026-09-20）。

【この数字が要る理由】
`MarginCapPct` は**発注の瞬間**に「使用証拠金 ≦ equity × cap%」を掛けるだけで、
**建てた後の維持率を保証しない。**

    cap50 → 建て直後の維持率 200%   （逆行余地 約50%）
    cap70 → 143%                    （約30%）
    cap90 → 111%                    （約11%）

**OANDA のロスカットは維持率 100%（XM は 20%）。**
したがって「元本割れなし」「完走した」は、**XM 端末で走らせた run については
「XM の 20% に当たらなかった」という意味しか持たない。**

🔴 **維持率そのものは端末のロスカット水準に依存しない量である。**
だから XM 端末で測った run でも、この値が 100% を割っていれば
**その構成は OANDA では死んでいる**と判定できる。ロスカットが実際に発火するかどうかだけが端末依存。

【なぜ既存のログでは足りなかったか】
`*_cap.csv` の `event` 行は**発注時**の equity と使用証拠金しか持たず、
しかも**発注時は cap の定義上どうしても `100/cap`% 以上**になる。
つまり **`event` 行からは最小維持率を復元できない。**
EA 側に毎ティックの計装（`TrackMarginLevel`）を足したのはこのためである。

【⚠️ 計装を入れた順序について】
**ガードより先に計装を入れた。** 先に `MinMarginLevelPct` のようなガードを入れると、
入れた時点で最小維持率が閾値で切り上がり、
**「元の構成がどれだけ危なかったか」が永久に分からなくなる。**

使い方:
    python ml/fxoanda4/margin_level.py                 # fxoanda4 の全 run
    python ml/fxoanda4/margin_level.py ml/fxqual15     # 他ラウンドにも使える
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

VERDICT = [
    (100.0, "🔴 OANDA なら死んでいる"),
    (150.0, "⚠️ 余裕がほとんど無い"),
    (200.0, "△ 狭い"),
    (10 ** 9, "○"),
]


def verdict(ml: float) -> str:
    for thr, text in VERDICT:
        if ml < thr:
            return text
    return "?"


def read_cap(path: Path) -> dict | None:
    """*_cap.csv から margin_level_min / margin_level_hist の2行を拾う。"""
    out: dict = {}
    try:
        rows = list(csv.reader(path.open(encoding="utf-8", errors="replace")))
    except OSError:
        return None
    for r in rows:
        if not r:
            continue
        if r[0] == "margin_level_min" and len(r) >= 7:
            # 🔴 標本が0の run は EA が "NOT_MEASURED" を書く。
            #    **「維持率 100% 割れ 0回」と読んではいけない。「測れていない」である。**
            try:
                out["ml_n"] = int(r[6])
            except ValueError:
                out["ml_n"] = 0
            if r[2] == "NOT_MEASURED" or out["ml_n"] == 0:
                out["not_measured"] = True
                continue
            try:
                out["ml_min"] = float(r[2])
                out["ml_t"] = int(r[3])
                out["ml_eq"] = float(r[4])
                out["ml_used"] = float(r[5])
            except ValueError:
                out["not_measured"] = True
        elif r[0] == "margin_level_hist" and len(r) >= 7:
            if "NOT_MEASURED" in r[2:6]:
                continue
            try:
                out["lt300"], out["lt200"] = int(r[2]), int(r[3])
                out["lt150"], out["lt100"] = int(r[4]), int(r[5])
            except ValueError:
                pass
        elif r[0] == "equity_dd_pct" and len(r) >= 7:
            try:
                out["eq_dd"] = float(r[5])
            except ValueError:
                pass
    return out or None


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    if not root.is_absolute():
        root = REPO / root
    deal_dir = root / "run_deals"
    caps = sorted(deal_dir.glob("*_cap.csv"))
    if not caps:
        print(f"{deal_dir} に *_cap.csv がありません（まだ走っていない可能性）")
        return

    print(f"# 建玉後の最小証拠金維持率 — {root.name}（{len(caps)} run）")
    print()
    print(f"{'run_id':46} {'最小維持率':>10} {'発生時刻':>12} "
          f"{'eq':>11} {'使用証拠金':>11} {'<100%':>7} {'判定'}")
    stale, unmeasured, cut = 0, 0, 0
    for c in caps:
        d = read_cap(c)
        run_id = c.name[:-len("_cap.csv")]
        if not d or ("ml_min" not in d and not d.get("not_measured")):
            stale += 1
            print(f"{run_id:46} {'—':>10}   計装の無い EA で走った run")
            continue
        if d.get("not_measured"):
            unmeasured += 1
            print(f"{run_id:46} {'NOT_MEASURED':>12}   "
                  f"標本0（維持率を1度も読めていない）")
            continue
        if d["ml_min"] < 100.0:
            cut += 1
        t = datetime.fromtimestamp(d["ml_t"], tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"{run_id:46} {d['ml_min']:9.1f}% {t:>12} "
              f"{d['ml_eq']:11,.0f} {d['ml_used']:11,.0f} "
              f"{d.get('lt100', 0):7,} {verdict(d['ml_min'])}")

    print()
    if stale:
        print(f"⚠️ {stale} run は `margin_level_min` 行を持っていない"
              f"＝**計装を入れる前の EA で走った run**。")
        print("   その run の「元本割れなし」は、**その端末のロスカット水準に"
              "当たらなかった**という意味しか持たない。")
    if unmeasured:
        print(f"🔴 {unmeasured} run は **NOT_MEASURED**（標本0）。")
        print("   **「100% 割れ 0回＝安全」と読んではいけない。「測れていない」である。**")
    if cut:
        print(f"🔴 {cut} run が **維持率 100% を割っている＝OANDA なら切られていた。**")
        print("   ⚠️ **XM 端末の run については、割った時刻 T 以降の損益・DD・月利は")
        print("      すべて反実仮想として無効である**（OANDA なら T で強制決済され、")
        print("      以降の経路が別物になる）。**成績を論じる前に候補から落とす。**")
        print("      成績を知りたければ OANDA 端末で測り直すしかない。")


if __name__ == "__main__":
    main()
