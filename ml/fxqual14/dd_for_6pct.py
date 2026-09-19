# -*- coding: utf-8 -*-
"""月利6% に到達するには equity DD がいくら必要か。

各系列は「同じブックを倍率だけ変えた2点」なので、`月利 = a x eqDD^k` を当てて
6% になる eqDD を逆算する。**2点フィットの外挿なので幅を持って読むこと。**
ただし**必要DD が 90% 台に出るなら、精度は問題にならない**（結論が変わらない）。
"""
import math

S = {
    "OOS": {"Carry あり": [(34.57, 2.488), (62.07, 3.849)],
            "Carry 抜き": [(22.19, 1.920), (41.73, 3.170)]},
    "IS":  {"Carry あり": [(40.23, 4.067), (68.16, 7.099)],
            "Carry 抜き": [(19.43, 2.419), (35.70, 4.506)]},
}
TARGET = 6.0

for win, d in S.items():
    print(f"=== {win} ===")
    for nm, pts in d.items():
        (x0, y0), (x1, y1) = pts
        k = math.log(y1 / y0) / math.log(x1 / x0)
        a = y0 / x0 ** k
        need = (TARGET / a) ** (1.0 / k)
        # 線形外挿でも出す（形に依存しないかの確認）
        sl = (y1 - y0) / (x1 - x0)
        need_lin = x1 + (TARGET - y1) / sl
        print(f"  {nm}: k={k:.3f}  実測レンジ eqDD {x0:.2f}〜{x1:.2f}% "
              f"（月利 {y0:.3f}〜{y1:.3f}%）")
        print(f"     月利6% に必要な eqDD = **{need:.1f}%**（冪） / "
              f"{need_lin:.1f}%（線形）  ← 実測レンジの {need/x1:.1f}倍の外挿")
    print()
print("参考: 残高が半分になる DD は 50%、8割減は 80%。")
print("     equity DD 90% 台は『含み損で口座がほぼ消える時期がある』という意味。")
