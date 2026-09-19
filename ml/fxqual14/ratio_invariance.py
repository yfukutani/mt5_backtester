# -*- coding: utf-8 -*-
"""「月利 ÷ DD」はレバレッジ不変ではない。同じブックの倍率1/2 の実測2点で示す。"""
import math

# (ラベル, 幾何月利%, equity DD%, 純益, 月数)  すべて cap90・候補3件・全複利
PTS = {
    "OOS": [("倍率1（V000/E002）", 2.488, 34.57, 1431459, 55),
            ("倍率2（E005）",       3.849, 62.07, 3491431, 55),
            ("倍率1・Carry抜き（V001）", 1.920, 22.19, 923423, 55)],
    "IS":  [("倍率1（V000/E002）", 4.067, 40.23, 4966997, 60),
            ("倍率2（E005）",       7.099, 68.16, 30121151, 60),
            ("倍率1・Carry抜き（V001）", 2.419, 19.43, 1598362, 60)],
}

for win, rows in PTS.items():
    print(f"=== {win} ===")
    print("%-26s %8s %8s %10s %12s %12s" %
          ("", "月利%", "eqDD%", "月利÷DD", "純益÷DD", "対数成長÷DD"))
    for lab, geo, dd, net, m in rows:
        lg = math.log((500000 + net) / 500000) / m
        print("%-26s %8.3f %8.2f %10.4f %12s %12.6f" %
              (lab, geo, dd, geo / dd, format(int(net / dd), ","), lg / dd))
    base, lev = rows[0], rows[1]
    # 同じブックをレバレッジだけ上げた2点。指数 k: geo ∝ DD^k
    k = math.log(lev[1] / base[1]) / math.log(lev[2] / base[2])
    print(f"  同一ブックの倍率1→2 で 月利÷DD は {base[1]/base[2]:.4f} → {lev[1]/lev[2]:.4f}"
          f"（{(lev[1]/lev[2])/(base[1]/base[2])-1:+.1%}）")
    print(f"  → **月利÷DD はレバレッジだけで動く。不変量ではない。** 実測の指数 k = {k:.3f}"
          f"（geo ∝ DD^k）")
    cl = rows[2]
    tgt = lev[2]
    proj = cl[1] * (tgt / cl[2]) ** k
    print(f"  参考: Carry抜きを eqDD {tgt:.2f}% まで上げたときの外挿 = {proj:.3f}%/月"
          f"（対 実測の倍率2 {lev[1]:.3f}%）")
