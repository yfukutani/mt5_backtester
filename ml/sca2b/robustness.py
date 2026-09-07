"""全案に「最良の年を除いても黒字か」という検査をかける。

【なぜこの検査か】GOLDは 2026年（IS）と 2020年（OOS）に激しくトレンドしており、
GOLD枠の利益はどれもその年に偏る。既存枠でもそうなので偏り自体は失格理由にならないが、
**その年を除くと赤字**になる案は「GOLDが走った年にだけ効く」だけであり、
採用しても次に同じ地合いが来るまで機能しない。

比較の基準は既存枠。最良年を除いた実測は
  SCA第1  IS +81,175円 / OOS +16,257円   ← 除いても明確に黒字
  PB GOLD IS +115,448円 / OOS +12,988円  ← 同上
第2セッションにも同じ水準を求める。
"""
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
SCA2 = 20261003


def yearly(path, magic):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["magic"]) != magic:
            continue
        pid = int(r["position_id"])
        if r["entry"] == "0":
            ins[pid] = r
        else:
            outs[pid].append(r)
    y = defaultdict(float)
    n = 0
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        y[datetime.fromtimestamp(int(i["time"]), timezone.utc).year] += \
            sum(float(x["profit"]) for x in o)
        n += 1
    return y, n


def main():
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["status"] == "OK"]
    by_id = defaultdict(dict)
    for r in rows:
        by_id[r["proposal_id"]][r["window"]] = r

    out = []
    for pid, w in by_id.items():
        if "IS" not in w or "OOS" not in w:
            continue
        rec = {"proposal_id": pid, "description": w["IS"]["description"]}
        ok = True
        for win in ("IS", "OOS"):
            p = DEAL_DIR / f"{w[win]['run_id']}_deals.csv"
            if not p.exists():
                ok = False
                break
            y, n = yearly(p, SCA2)
            if not y:
                ok = False
                break
            tot = sum(y.values())
            best_year = max(y.items(), key=lambda kv: kv[1])
            ex = tot - best_year[1]
            rec[f"{win}_total"] = tot
            rec[f"{win}_n"] = n
            rec[f"{win}_best_year"] = best_year[0]
            rec[f"{win}_best_val"] = best_year[1]
            rec[f"{win}_ex_best"] = ex
            rec[f"{win}_years_pos"] = sum(1 for v in y.values() if v > 0)
            rec[f"{win}_years"] = len(y)
        if not ok:
            continue
        rec["worst_ex"] = min(rec["IS_ex_best"], rec["OOS_ex_best"])
        out.append(rec)

    out.sort(key=lambda r: -r["worst_ex"])
    passed = [r for r in out if r["IS_ex_best"] > 0 and r["OOS_ex_best"] > 0]

    print(f"評価 {len(out)} 案 / 最良年を除いても両窓黒字 {len(passed)} 案")
    print()
    print(f"{'案':<7}{'IS計':>10}{'IS最良年':>9}{'IS除外後':>10}{'IS年+/計':>9}"
          f"{'OOS計':>9}{'OOS最良年':>10}{'OOS除外後':>10}{'OOS年+/計':>10}  内容")
    for r in out[:18]:
        print(f"{r['proposal_id']:<7}{r['IS_total']:>10,.0f}{r['IS_best_year']:>9}"
              f"{r['IS_ex_best']:>10,.0f}{str(r['IS_years_pos'])+'/'+str(r['IS_years']):>9}"
              f"{r['OOS_total']:>9,.0f}{r['OOS_best_year']:>10}"
              f"{r['OOS_ex_best']:>10,.0f}"
              f"{str(r['OOS_years_pos'])+'/'+str(r['OOS_years']):>10}  {r['description'][:30]}")

    print()
    print("【比較】既存枠の最良年を除いた実測")
    print("  SCA第1   IS +81,175 / OOS +16,257")
    print("  PB GOLD  IS +115,448 / OOS +12,988")

    with open(ROOT / "robustness.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"\n-> {ROOT / 'robustness.csv'}")


if __name__ == "__main__":
    main()
