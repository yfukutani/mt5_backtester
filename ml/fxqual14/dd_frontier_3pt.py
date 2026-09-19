# -*- coding: utf-8 -*-
"""3点そろった各系列で (a) 6% に必要な eqDD (b) DD を揃えた差 を出す。"""
import math

S = {
    "OOS": {"あり": [(34.57, 2.488), (62.07, 3.849), (73.62, 4.608)],
            "抜き": [(22.19, 1.920), (41.73, 3.170), (50.20, 3.611)]},
    "IS":  {"あり": [(40.23, 4.067), (68.16, 7.099), (85.24, 9.699)],
            "抜き": [(19.43, 2.419), (35.70, 4.506), (46.90, 6.412)]},
}


def seg_k(p0, p1):
    return math.log(p1[1] / p0[1]) / math.log(p1[0] / p0[0])


def interp(pts, x):
    for i in range(len(pts) - 1):
        if pts[i][0] <= x <= pts[i + 1][0]:
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            lin = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            k = seg_k(pts[i], pts[i + 1])
            return lin, y0 * (x / x0) ** k, True
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    k = seg_k(pts[-2], pts[-1])
    sl = (y1 - y0) / (x1 - x0)
    return y1 + sl * (x - x1), y1 * (x / x1) ** k, False


for win, d in S.items():
    print(f"=== {win} ===")
    for nm, pts in d.items():
        ks = [seg_k(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        top = pts[-1]
        ktop = ks[-1]
        need = top[0] * (6.0 / top[1]) ** (1 / ktop)
        print(f"  Carry {nm}: 区間k = " + " / ".join(f"{k:.3f}" for k in ks) +
              f"  → 6% に必要な eqDD **{need:.1f}%**（外挿 {need/top[0]:.2f}倍）")
    print("  --- DD を揃えた比較（Carry 抜きの実測点で揃える）---")
    for x, y in d["抜き"]:
        lin, pw, inside = interp(d["あり"], x)
        tag = "内挿" if inside else "★外挿"
        print(f"    eqDD {x:5.2f}%: あり {lin:5.3f}/{pw:5.3f}% [{tag}]  "
              f"抜き {y:5.3f}%（実測）  差 **{y-(lin+pw)/2:+.3f}pt**")
