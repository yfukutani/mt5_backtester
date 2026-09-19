"""倍率1/2/3 × Carry あり/抜き の6点から、フロンティアと必要DDを読む。

【3点そろって初めて言えること】
- 各系列の**局所指数の動き方**（曲率が上がるのか下がるのか）
- **DD を揃えた比較が2水準で再現するか**（1点だけなら偶然の可能性がある）
- 月利6% に必要な equity DD の見積もり（**外挿であることは変わらない**）

⚠️ **必要DD の逆算は外挿である。** 2点フィットは `V012` を 0.235pt 外した前科がある。
**ここでは「上端の局所指数」で外挿し、外挿倍率も併記する。**
"""
from __future__ import annotations

import math

SERIES = {
    "OOS": {
        "carry":   [(34.57, 2.488), (62.07, 3.849), (73.62, 4.608)],
        "nocarry": [(22.19, 1.920), (41.73, 3.170), (50.20, 3.611)],
    },
    "IS": {
        "carry":   [(40.23, 4.067), (68.16, 7.099), (85.24, 9.699)],
        "nocarry": [(19.43, 2.419), (35.70, 4.506), (46.90, 6.412)],
    },
}
TARGET = 6.0


def kseg(p, q):
    return math.log(q[1] / p[1]) / math.log(q[0] / p[0])


def interp(pts, x):
    """x を含む区間で線形・冪の両方を返す。内挿かどうかも返す。"""
    for p, q in zip(pts, pts[1:]):
        if p[0] <= x <= q[0]:
            lin = p[1] + (q[1] - p[1]) * (x - p[0]) / (q[0] - p[0])
            k = kseg(p, q)
            pw = p[1] * (x / p[0]) ** k
            return lin, pw, True
    p, q = pts[-2], pts[-1]
    lin = q[1] + (q[1] - p[1]) * (x - q[0]) / (q[0] - p[0])
    k = kseg(p, q)
    pw = q[1] * (x / q[0]) ** k
    return lin, pw, False


def main():
    for w in ("OOS", "IS"):
        c, n = SERIES[w]["carry"], SERIES[w]["nocarry"]
        print(f"\n=== {w} ===")
        print("局所指数 k（区間ごと）:")
        print(f"  Carry あり : {kseg(c[0],c[1]):.3f} -> {kseg(c[1],c[2]):.3f}"
              f"  ({'上がる＝収穫逓増に見える' if kseg(c[1],c[2])>kseg(c[0],c[1]) else '下がる＝逓減'})")
        print(f"  Carry 抜き : {kseg(n[0],n[1]):.3f} -> {kseg(n[1],n[2]):.3f}"
              f"  ({'上がる' if kseg(n[1],n[2])>kseg(n[0],n[1]) else '下がる＝逓減'})")

        print("equity DD を揃えた比較（Carry 抜きの実測点に合わせる）:")
        for dd, act in [(p[0], p[1]) for p in n]:
            lin, pw, inside = interp(c, dd)
            tag = "内挿" if inside else "⚠️外挿"
            ok = abs(lin - pw) < 0.05
            note = "" if ok else "  🔴 線形と冪が不一致。使わない"
            print(f"  eqDD {dd:5.2f}% ({tag}) : Carry あり {lin:.3f}/{pw:.3f}% "
                  f"vs 抜き {act:.3f}% -> {act-(lin+pw)/2:+.3f}pt{note}")

        print(f"月利 {TARGET}% に必要な equity DD（上端の局所指数で外挿）:")
        for nm, pts in (("Carry あり", c), ("Carry 抜き", n)):
            k = kseg(pts[-2], pts[-1])
            dd = pts[-1][0] * (TARGET / pts[-1][1]) ** (1.0 / k)
            print(f"  {nm}: k={k:.3f} -> **{dd:.0f}%**  "
                  f"（実測の上端 {pts[-1][0]:.1f}% から {dd/pts[-1][0]:.2f}倍の外挿）")


if __name__ == "__main__":
    main()
