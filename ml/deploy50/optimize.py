# -*- coding: utf-8 -*-
"""総資金50万円の配分・倍率を、DD30%制約下で月利最大化する。

【DD制約の取り方】
IS期間のDDだけで倍率を決めるのは過剰適合。IS(60か月)と全期間(115か月)の
**悪い方**のDD円額を制約に使う。全期間はコロナ相場・暗号の暴落局面を含む。

【換算】基準ロット0.01固定・リスク建て枠もRefCap=100,000基準の固定サイズなので
損益もDDも入金額に依存しない円額として出る。よって配分Aに対し
  DD% = DD円 / A ,  月利% = 純利益円 / A / 月数
"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "deploy50"
TOTAL = 500000
DD_CAP = 30.0
IS_MONTHS, FULL_MONTHS = 60.0, 115.0


def load(path, keyfn):
    out = {}
    if not path.exists():
        return out
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if not r.get("net"):
            continue
        out[keyfn(r)] = {"net": float(r["net"]), "pf": float(r["pf"]),
                         "dd": float(r["dd_yen"]), "n": int(r["n"])}
    return out


is_rows = load(ROOT / "books.csv",
               lambda r: (r["book"], r.get("variant", "-"), int(r["mult"])))
full_rows = load(ROOT / "books_full.csv",
                 lambda r: (r["book"], r.get("variant", "-"), int(r["mult"])))

# 採用構成: OANDA=FX枠(構成なし), XM=HOLD64
BOOKS = [("OANDA_FX", "-"), ("XM_CFD", "HOLD64")]


def spec(book, variant, m):
    """IS/全期間の両方が揃っている倍率だけを候補にする。DDは悪い方を採る。"""
    i = is_rows.get((book, variant, m))
    f = full_rows.get((book, variant, m))
    if not i or not f:
        return None
    return {
        "dd": max(i["dd"], f["dd"]),
        "is_net": i["net"], "full_net": f["net"],
        "is_pf": i["pf"], "full_pf": f["pf"],
        "n": f["n"],
    }


print("=== 倍率別データ（DDはIS/全期間の悪い方）===")
cand = {}
for book, variant in BOOKS:
    for m in range(1, 6):
        s = spec(book, variant, m)
        if not s:
            continue
        cand[(book, variant, m)] = s
        need = s["dd"] / (DD_CAP / 100.0)
        print("%-9s %-7s x%d DD=%8.0f円 (必要資金 %8.0f円) "
              "IS月利/万=%6.2f%% 全月利/万=%6.2f%%"
              % (book, variant, m, s["dd"], need,
                 s["is_net"] / IS_MONTHS / need * 100,
                 s["full_net"] / FULL_MONTHS / need * 100))

# 配分探索: 1万円刻み
best = []
for a in range(0, TOTAL + 1, 10000):
    b = TOTAL - a
    for (bk1, v1, m1), s1 in list(cand.items()) + [(("OANDA_FX", "-", 0), None)]:
        if bk1 != "OANDA_FX":
            continue
        if s1 is None:
            if a != 0:
                continue
            o_is = o_full = 0.0
            o_dd = 0.0
        else:
            if a == 0 or s1["dd"] / a * 100 > DD_CAP:
                continue
            o_is, o_full, o_dd = s1["is_net"], s1["full_net"], s1["dd"] / a * 100
        for (bk2, v2, m2), s2 in list(cand.items()) + [(("XM_CFD", "HOLD64", 0), None)]:
            if bk2 != "XM_CFD":
                continue
            if s2 is None:
                if b != 0:
                    continue
                x_is = x_full = 0.0
                x_dd = 0.0
            else:
                if b == 0 or s2["dd"] / b * 100 > DD_CAP:
                    continue
                x_is, x_full, x_dd = s2["is_net"], s2["full_net"], s2["dd"] / b * 100
            if a == 0 and b == 0:
                continue
            is_m = (o_is + x_is) / IS_MONTHS / TOTAL * 100
            full_m = (o_full + x_full) / FULL_MONTHS / TOTAL * 100
            best.append({"oanda": a, "om": m1, "odd": o_dd,
                         "xm": b, "xmm": m2, "xdd": x_dd,
                         "is_m": is_m, "full_m": full_m,
                         "worst_m": min(is_m, full_m)})

best.sort(key=lambda r: -r["is_m"])
print("\n=== IS月利の高い順 上位10（各口座DD30%%以下）===")
print("OANDA配分  倍率  DD%%  |  XM配分  倍率  DD%%  |  IS月利  全期間月利")
for r in best[:10]:
    print("%8d円 x%d %5.1f%% | %8d円 x%d %5.1f%% | %6.2f%%  %6.2f%%"
          % (r["oanda"], r["om"], r["odd"], r["xm"], r["xmm"], r["xdd"],
             r["is_m"], r["full_m"]))

best.sort(key=lambda r: -r["worst_m"])
print("\n=== IS/全期間の悪い方が高い順 上位5（保守的な最適）===")
for r in best[:5]:
    print("%8d円 x%d %5.1f%% | %8d円 x%d %5.1f%% | IS %6.2f%%  全期間 %6.2f%%"
          % (r["oanda"], r["om"], r["odd"], r["xm"], r["xmm"], r["xdd"],
             r["is_m"], r["full_m"]))

div = [r for r in best if r["oanda"] > 0 and r["xm"] > 0]
div.sort(key=lambda r: -r["is_m"])
print("\n=== 2口座に分散する案のうちIS月利が高い順 上位5 ===")
for r in div[:5]:
    print("%8d円 x%d %5.1f%% | %8d円 x%d %5.1f%% | IS %6.2f%%  全期間 %6.2f%%"
          % (r["oanda"], r["om"], r["odd"], r["xm"], r["xmm"], r["xdd"],
             r["is_m"], r["full_m"]))
