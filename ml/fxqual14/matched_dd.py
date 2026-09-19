"""equity DD を揃えて「Carry あり / 抜き」を比べる。**比も傾きも使わない。**

【なぜ要るか — 今日2回まちがえた】
1. **`月利 ÷ DD` はレバレッジ不変量ではない。** 同じブックのまま倍率1→2 にすると
   OOS の比が 0.0720 → 0.0620（−13.8%）に落ちる。幾何月利は純益に対して凹なので、
   **DD の低い構成ほど比が高く出る。**
2. **傾き（ΔGeo / ΔeqDD）も同じ交絡を受ける。** 同じ系列の中で
   原点→倍率1 と 倍率1→倍率2 の傾きを比べると OOS で 26〜31% 落ちる。
   **低い DD 領域で測った傾きは自然に急になる。**
   Carry 抜きの区間（eqDD 22→42%）は Carry ありの区間（35→62%）より低いので、
   「Carry 抜きの傾きが +29%」の一部は曲率である。

⚠️ **OOS は凹（傾きが落ちる）だが IS は凸（傾きが増える）。窓で曲率の符号が違うので、
窓をまたいだ一般化はできない。** 冪指数は OOS 0.75 / IS 1.02〜1.06 で 1 をまたぐ。

【正しいやり方 — 同じ equity DD の点どうしで比べる】
`V011`（Carry 抜き・倍率2）の eqDD 41.73% は、**Carry あり系列の2点
（34.57% と 62.07%）の内側**にある。**だから内挿で比べられる。外挿ではない。**
線形と冪の2通りで補間して、**両者が一致することを確認してから使う**
（一致しなければ補間の形に依存しているので、その数字は使わない）。
"""
from __future__ import annotations

import math

# (eqDD%, 幾何月利%) — ml/fxqual14/results.csv と agent_results より
SERIES = {
    "OOS": {
        "carry":   [(0.0, 0.0), (34.57, 2.488), (62.07, 3.849)],   # V000 / V010
        "nocarry": [(0.0, 0.0), (22.19, 1.920), (41.73, 3.170)],   # V001 / V011
    },
    "IS": {
        "carry":   [(0.0, 0.0), (40.23, 4.067), (68.16, 7.099)],
        "nocarry": [(0.0, 0.0), (19.43, 2.419), (35.70, 4.506)],
    },
}


def lin(pts, x):
    """区間を選んで線形補間／端の区間で外挿。内挿かどうかも返す。"""
    p = [q for q in pts if q[0] > 0]
    (x0, y0), (x1, y1) = p[0], p[1]
    inside = x0 <= x <= x1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0), inside


def powfit(pts, x):
    """geo = a * DD^k の2点フィット（原点は使わない）。"""
    p = [q for q in pts if q[0] > 0]
    (x0, y0), (x1, y1) = p[0], p[1]
    k = math.log(y1 / y0) / math.log(x1 / x0)
    a = y0 / x0 ** k
    return a * x ** k, k


def main():
    for w in ("OOS", "IS"):
        print(f"\n=== {w} ===")
        c, n = SERIES[w]["carry"], SERIES[w]["nocarry"]

        # 曲率の点検（傾きが区間で動くか）
        s0 = c[1][1] / c[1][0]
        s1 = (c[2][1] - c[1][1]) / (c[2][0] - c[1][0])
        t0 = n[1][1] / n[1][0]
        t1 = (n[2][1] - n[1][1]) / (n[2][0] - n[1][0])
        print(f"傾きの変化  Carry あり {s0:.4f} -> {s1:.4f} ({100*(s1/s0-1):+.1f}%) / "
              f"Carry 抜き {t0:.4f} -> {t1:.4f} ({100*(t1/t0-1):+.1f}%)")
        print("  → 同じ系列の中でも傾きが動く。傾きどうしの比較は曲率に汚染される")

        for dd, label in ((n[2][0], "V011 の eqDD"), (n[1][0], "V001 の eqDD")):
            yl, inside = lin(c, dd)
            yp, k = powfit(c, dd)
            act = next(y for x, y in n if abs(x - dd) < 1e-9)
            tag = "内挿" if inside else "⚠️外挿"
            agree = "一致" if abs(yl - yp) < 0.05 else "🔴不一致（この数字は使わない）"
            print(f"eqDD {dd:5.2f}% ({label}・{tag}) : "
                  f"Carry あり 線形 {yl:.3f}% / 冪 {yp:.3f}%（k={k:.3f}・{agree}） "
                  f"vs Carry 抜き 実測 {act:.3f}% → 差 {act-(yl+yp)/2:+.3f}pt")


if __name__ == "__main__":
    main()
