"""測定結果を集計し、採用候補を判定する。

results.csv は追記型で、リトライにより同じ (proposal_id, window) が複数行になりうる。
最後の成功行を採用する。
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results.csv"
PROPOSALS = ROOT / "proposals.csv"


def load():
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    latest = {}
    for r in rows:
        key = (r["proposal_id"], r["window"])
        if r.get("status") == "OK":
            latest[key] = r          # 後勝ち＝最後の成功測定
    return rows, latest


def main():
    if not RESULTS.exists():
        raise SystemExit("results.csv がまだ無い")
    props = {p["proposal_id"]: p for p in csv.DictReader(open(PROPOSALS, encoding="utf-8"))}
    rows, latest = load()

    print(f"総run数 {len(rows)}  成功 {len(latest)}  提案 {len(props)}")
    print()
    print("=== 判定の内訳（IS） ===")
    is_rows = {k[0]: v for k, v in latest.items() if k[1] == "IS"}
    for d, c in Counter(r["decision"] for r in is_rows.values()).most_common():
        print(f"  {c:>5}  {d}")

    oos_rows = {k[0]: v for k, v in latest.items() if k[1] == "OOS"}
    if oos_rows:
        print()
        print("=== 判定の内訳（OOS） ===")
        for d, c in Counter(r["decision"] for r in oos_rows.values()).most_common():
            print(f"  {c:>5}  {d}")

    print()
    print("=== ファミリー別のIS通過率 ===")
    fam = defaultdict(lambda: [0, 0])
    for pid, r in is_rows.items():
        fam[r["family"]][0] += 1
        if r["decision"].startswith("IS_SURVIVOR"):
            fam[r["family"]][1] += 1
    print(f"{'ファミリー':<26}{'測定':>6}{'IS通過':>8}{'率':>8}")
    for f in sorted(fam):
        n, s = fam[f]
        print(f"{f:<26}{n:>6}{s:>8}{100*s/max(1,n):>7.1f}%")

    adopt = {pid: r for pid, r in oos_rows.items() if r["decision"].startswith("ADOPT")}
    print()
    print(f"=== 採用候補（両窓通過）: {len(adopt)} 件 ===")
    if not adopt:
        print("  なし")
    for pid in sorted(adopt, key=lambda p: -float(oos_rows[p]["net_ratio"] or 0)):
        o = oos_rows[pid]
        i = is_rows.get(pid, {})
        p = props.get(pid, {})
        print(f"\n  {pid}  {p.get('family','')}  {p.get('description','')}")
        print(f"    IS  net {float(i.get('net',0)):>12,.0f} ({100*(float(i.get('net_ratio',1))-1):+6.2f}%)"
              f"  PF {float(i.get('pf',0)):.4f}  DD {float(i.get('dd_pct',0)):.4f}%"
              f" ({float(i.get('dd_delta',0)):+.4f}pt)  取引 {i.get('trades','')}")
        print(f"    OOS net {float(o['net']):>12,.0f} ({100*(float(o['net_ratio'])-1):+6.2f}%)"
              f"  PF {float(o['pf']):.4f}  DD {float(o['dd_pct']):.4f}%"
              f" ({float(o['dd_delta']):+.4f}pt)  取引 {o['trades']}")
        print(f"    params {p.get('parameter_json','')}")

    print()
    print("=== IS通過だがOOS未確認 / 落ちたもの 上位10（IS純益順） ===")
    surv = [(pid, r) for pid, r in is_rows.items() if r["decision"].startswith("IS_SURVIVOR")]
    surv.sort(key=lambda kv: -float(kv[1]["net_ratio"] or 0))
    for pid, r in surv[:10]:
        o = oos_rows.get(pid)
        od = o["decision"] if o else "OOS未測定"
        print(f"  {pid} {r['family']:<24} IS {100*(float(r['net_ratio'])-1):+6.2f}% "
              f"DD {float(r['dd_delta']):+.3f}pt -> {od}")

    failed = [r for r in rows if r.get("status") == "FAILED"]
    if failed:
        print()
        print(f"=== 失敗run {len(failed)} 件 ===")
        for g, c in Counter(r["gate_code"] for r in failed).most_common():
            print(f"  {c:>5}  {g}")
        unrecovered = {(r["proposal_id"], r["window"]) for r in failed} - set(latest)
        print(f"  最後まで未回収: {len(unrecovered)} 件")


if __name__ == "__main__":
    main()
