# -*- coding: utf-8 -*-
"""時間帯ゲート検証の最終判定。

採用条件:
  - IS/OOS両期間で符号が一致（片方だけの改善は過剰適合として却下）
  - 両期間で純利益・PFが向上しDDが悪化しない → 厳格改善
"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
A = REPO / "ml" / "gold_hour" / "assessment.csv"

rows = list(csv.DictReader(open(A, encoding="utf-8-sig")))


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


base = None
for r in rows:
    if "BASELINE" in (r.get("candidate_id", "") + r.get("label", "")).upper():
        base = r
        break
if base:
    print("基準 OFF: IS net=%s pf=%s dd=%s / OOS net=%s pf=%s dd=%s"
          % (base["is_net"], base["is_pf"], base["is_dd_pct"],
             base["oos_net"], base["oos_pf"], base["oos_dd_pct"]))

strict = [r for r in rows if str(r.get("strict_both", "")).lower() in ("true", "1", "yes")]
signok = [r for r in rows if str(r.get("sign_consistent", "")).lower() in ("true", "1", "yes")
          and r not in strict]

print("\n候補数: %d  / 符号一致: %d / 厳格改善: %d"
      % (len(rows), len(signok) + len(strict), len(strict)))


def show(title, items):
    print("\n===== %s : %d件 =====" % (title, len(items)))
    items = sorted(items, key=lambda r: (f(r["oos_delta_net"]) or -9e9), reverse=True)
    for r in items:
        xm = ""
        if f(r.get("xm5_net")) is not None:
            xm = " | XM5 net=%.0f pf=%.4f dd=%.4f%%" % (
                f(r["xm5_net"]), f(r["xm5_pf"]), f(r["xm5_dd_pct"]))
        print("%-22s IS[%+8.1f pf%+.4f dd%+.4f] OOS[%+7.1f pf%+.4f dd%+.4f]%s"
              % (r["label"][:22],
                 f(r["is_delta_net"]) or 0, f(r["is_delta_pf"]) or 0, f(r["is_delta_dd"]) or 0,
                 f(r["oos_delta_net"]) or 0, f(r["oos_delta_pf"]) or 0, f(r["oos_delta_dd"]) or 0,
                 xm))


show("厳格改善（IS/OOS両方で利益・PF向上、DD悪化なし）", strict)
show("符号一致するが厳格ではない", signok[:12])

# 水曜候補とユーザー指定(月/金)を明示的に拾う
print("\n===== 曜日別の主要候補 =====")
for key in ("WED", "MON", "FRI"):
    sel = [r for r in rows if key in r["label"].upper()]
    if not sel:
        continue
    sel = sorted(sel, key=lambda r: (f(r["oos_delta_net"]) or -9e9), reverse=True)[:4]
    print("\n[%s]" % key)
    for r in sel:
        print("  %-24s ISΔnet%+8.1f OOSΔnet%+7.1f 符号一致=%s 厳格=%s"
              % (r["label"][:24], f(r["is_delta_net"]) or 0, f(r["oos_delta_net"]) or 0,
                 r.get("sign_consistent"), r.get("strict_both")))
