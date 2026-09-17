"""IS最適重みが「月利6%以上の窓の数」を増やすかを測る（段階2）。

`docs/oanda_fx_cap_pathdep_20260915.md` は、証拠金cap について
**「6%以上の窓の数を増やさない」**（24か月窓 4/9のまま・12か月窓 8/19のまま）と結論した。
capは分布の裾を削る操作で、真ん中を押し上げる力が弱いからである。

**枠別の重み（A3/A7）は違う軸である。**こちらは各枠の寄与そのものを変えるので、
分布の位置を動かしうる。同じ指標で測り、cap と同じ物差しで比べる。

重みは IS(2021-06〜2026-06) だけで決めたものを使い、窓はそこに含まれる期間も
含まれない期間もまたぐ。**したがってこれは OOS 測定ではなく安定性の診断である。**
"""
from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("w", Path(__file__).parent / "weights.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
mcs = W.mcs

OPT = {20260622: 0.3, 20260627: 1.0, 20260610: 2.0, 20260605: 4.0, 20260774: 4.0,
       20260629: 8.0, 20260650: 0.75, 20261000: 12.0, 20261001: 12.0}
CONS = {20260622: 0.5, 20260627: 1.0, 20260610: 2.0, 20260605: 4.0, 20260774: 4.0,
        20260629: 4.0, 20260650: 0.75, 20261000: 4.0, 20261001: 4.0}


def edges(rows, span, step):
    times = [int(r["time"]) for r in rows]
    first = datetime.fromtimestamp(min(times), timezone.utc)
    last = datetime.fromtimestamp(max(times), timezone.utc)
    out = []
    y, mo = first.year, first.month
    while True:
        a = datetime(y, mo, 1, tzinfo=timezone.utc)
        ny, nmo = y + (mo - 1 + span) // 12, (mo - 1 + span) % 12 + 1
        b = datetime(ny, nmo, 1, tzinfo=timezone.utc)
        if a >= last:
            break
        out.append((int(a.timestamp()), int(b.timestamp()), f"{a:%Y-%m}〜{b:%Y-%m}"))
        y, mo = y + (mo - 1 + step) // 12, (mo - 1 + step) % 12 + 1
        if b > last:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="T036")
    ap.add_argument("--cap", type=float, default=0.80)
    args = ap.parse_args()
    rows = mcs.load(REPO, args.id, "full")
    params, desc = mcs.params_of(REPO, args.id)
    comp = mcs.compounding_magics(params)

    cases = [("全重み1（基準）", {m: 1.0 for m in W.SLEEVES}),
             ("IS最適重み", OPT), ("保守版（一律4倍まで）", CONS)]

    print(f"■ {args.id}  cap={args.cap:.0%}   各窓を新規50万円口座として計算")
    print("  重みは IS だけで決めた。窓はISを含むので、これは OOS 測定ではなく安定性の診断。\n")
    for span, step in ((24, 12), (12, 6)):
        es = edges(rows, span, step)
        vals = {label: [W.simulate(rows, comp, w, args.cap, t0, t1)["geo"]
                        for t0, t1, _ in es] for label, w in cases}
        print(f"  --- {span}か月窓・進め幅{step}か月・{len(es)}本 ---")
        print("  %-22s %8s %8s %8s %8s %10s %10s"
              % ("", "中央値", "平均", "最悪", "最良", "6%以上", "マイナス"))
        for label, _ in cases:
            xs = sorted(vals[label])
            n = len(xs)
            med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
            print("  %-22s %7.2f%% %7.2f%% %7.2f%% %7.2f%% %6d/%-3d %6d/%-3d"
                  % (label, med, sum(xs) / n, xs[0], xs[-1],
                     sum(1 for x in xs if x >= 6.0), n,
                     sum(1 for x in xs if x < 0.0), n))

        # 【符号の数え上げ】capの「純益が増える」は、期間を切ったら 4勝5敗で消えた
        # （docs/oanda_fx_cap_pathdep_20260915.md）。**同じ物差しを重みにも当てる。**
        # 自分の新しい発見にだけ甘い基準を使わないための手続きである。
        base = vals[cases[0][0]]
        print(f"\n  期間ごとの符号（基準に対する月利の差・pt）")
        print("  %-18s %12s %12s" % ("期間", "IS最適重み", "保守版"))
        for i, (_, _, label) in enumerate(es):
            print("  %-18s %+11.2f %+11.2f"
                  % (label, vals["IS最適重み"][i] - base[i],
                     vals["保守版（一律4倍まで）"][i] - base[i]))
        # 重みは IS(2021-06-20〜) で決めたので、IS を含む窓は有利に出て当然である。
        # **窓全体が OOS に収まるものだけ**を分けて数え直す。ここが本当の判定になる。
        is_from = int(W.IS_FROM)
        oos_only = [i for i, (t0, t1, _) in enumerate(es) if t1 <= is_from]
        for name in ("IS最適重み", "保守版（一律4倍まで）"):
            w_ = sum(1 for i in range(len(base)) if vals[name][i] > base[i])
            wo = sum(1 for i in oos_only if vals[name][i] > base[i])
            print(f"  {name}: 全窓 勝ち {w_} / 負け {len(base)-w_}"
                  f"   ‖ **OOSに収まる窓だけ** 勝ち {wo} / 負け {len(oos_only)-wo}")

        # 目標指標（6%以上の窓）も、OOSに収まる窓だけで数え直す。
        if oos_only:
            print(f"\n  OOSに収まる窓だけ（{len(oos_only)}本）の分布")
            print("  %-22s %8s %8s %8s %10s" % ("", "中央値", "最悪", "最良", "6%以上"))
            for label, _ in cases:
                xs = sorted(vals[label][i] for i in oos_only)
                n = len(xs)
                med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
                print("  %-22s %7.2f%% %7.2f%% %7.2f%% %6d/%-3d"
                      % (label, med, xs[0], xs[-1],
                         sum(1 for x in xs if x >= 6.0), n))
        print()
    print("注: 段階2の簡易検証であり、採用の根拠にはしない。")
    print("    重みは IS で決めたので、IS を含む窓は有利に出る。符号の数えはその分を割り引く。")


if __name__ == "__main__":
    main()
