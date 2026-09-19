"""2つの run の deal ログを突き合わせて、「同じ取引なのに損益だけ違う」を検出する。

【なぜ要るか — 2026-09-19 に見つけた】
並行セッションが FULL 窓の対照を取ったところ、9月9日の `ml/fxrisk1` R001 と
**取引数は 2,969 で完全に同じなのに純益が 379,084 → 375,014（−4,070円）**になっていた。

突き合わせたら、**時刻・magic・方向・ロット・価格・SL は全 deal で完全一致**し、
**違うのは Carry AUDJPY の決済損益だけ**だった。しかもその差は**保有日数に比例**し、
13取引すべてで **−0.664 円/日/0.01ロット**で一定だった（延べ 6,129 ロット日 × −0.664 = −4,070）。

**MT5 のテスターは、履歴全体に「いまのスワップ値」を適用する。**
業者がスワップを更新すると、**同じ設定で走らせ直しても Carry の損益は変わる。**
EA の取引ログ書き出し（`DEAL_PROFIT + DEAL_SWAP + DEAL_COMMISSION`）は
この9日間で1行も変わっていないことを git で確認済みで、原因は EA 側ではない。

> [!important] **これは「EA 変更が不変でなかった」ではない。逆である。**
> 9日間で 553行入った EA 変更は、**8枠すべてで1円まで完全に不変**だった。
> 動いたのは業者のスワップ値だけである。

【使い方】
    python ml/fxqual9/swapdrift.py <旧の deal ログ> <新の deal ログ>
    python ml/fxqual9/swapdrift.py ml/fxrisk1 R001 FULL ml/fxqualcfm F000 FULL

【いつ使うか】
**対照 run が過去ラウンドと合わないとき、案を疑う前にこれを回す。**
差が Carry だけで、保有日数に比例していれば、それはスワップのドリフトであって
案の効果でも計測バグでもない。
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

MAGIC = {
    "20260622": "PB USDJPY", "20260627": "PB GBPJPY",
    "20260610": "RSI USDJPY", "20260605": "RSI EURUSD", "20260774": "RSI GBPUSD",
    "20260629": "Pair EU/GU", "20260650": "Carry AUDJPY",
    "20261000": "SCA USDJPY", "20261001": "SCA GBPJPY",
}


def find(root: str, pid: str, window: str) -> str:
    base = root if Path(root).is_absolute() else str(REPO / root)
    hits = sorted(glob.glob(f"{base}/run_deals/*_{window.lower()}_{pid}_*_deals.csv"))
    if not hits:
        raise SystemExit(f"deal ログが見つからない: {base} {pid} {window}")
    return hits[-1]


def load(path: str):
    rows = list(csv.DictReader(open(path, encoding="utf-8", errors="ignore")))
    pid_magic = {}
    for r in rows:
        if r["entry"] == "0":
            pid_magic[r["position_id"]] = r["magic"]
    return rows, pid_magic


def main() -> None:
    a = sys.argv[1:]
    if len(a) == 6:
        fa, fb = find(a[0], a[1], a[2]), find(a[3], a[4], a[5])
    elif len(a) == 2:
        fa, fb = a[0], a[1]
    else:
        raise SystemExit(__doc__)

    ra, pma = load(fa)
    rb, pmb = load(fb)
    print(f"旧: {fa}")
    print(f"新: {fb}\n")
    na = sum(float(r["profit"]) for r in ra)
    nb = sum(float(r["profit"]) for r in rb)
    print(f"行数 {len(ra)} / {len(rb)}    "
          f"純益 {na:,.0f} → {nb:,.0f}  ({nb - na:+,.0f})\n")
    if len(ra) != len(rb):
        print("**行数が違う。取引そのものが変わっている＝スワップのドリフトではない。**")
        return

    # 1) 数量・価格・時刻が動いているか
    cols = ("time", "magic", "entry", "type", "volume", "price", "sl")
    moved = {c: 0 for c in cols}
    for x, y in zip(ra, rb):
        for c in cols:
            if c in x and c in y and x[c] != y[c]:
                moved[c] += 1
    bad = {c: n for c, n in moved.items() if n}
    if bad:
        print("**取引の中身が動いている列があるので、スワップでは説明できない:**", bad, "\n")
    else:
        print("時刻・magic・方向・ロット・価格・SL は **全 deal で完全一致**。"
              "違うのは損益だけ。\n")

    # 2) 枠別の損益差
    per = {}
    for x, y in zip(ra, rb):
        mg = pma.get(x["position_id"], x["magic"])
        per[mg] = per.get(mg, 0.0) + float(y["profit"]) - float(x["profit"])
    print("| 枠 | 純益差 |")
    print("|---|---:|")
    for mg, d in sorted(per.items(), key=lambda kv: kv[1]):
        if abs(d) < 0.5:
            continue
        print(f"| {MAGIC.get(mg, mg)} | {d:+,.0f} |")
    zero = [MAGIC.get(m, m) for m, d in per.items() if abs(d) < 0.5]
    print(f"\n**差が 0 円の枠: {', '.join(zero) if zero else 'なし'}**\n")

    # 3) 差のあった枠について、保有日数あたりの差を出す
    for mg, d in sorted(per.items(), key=lambda kv: kv[1]):
        if abs(d) < 0.5:
            continue
        print(f"### {MAGIC.get(mg, mg)} — 保有日数あたりの差\n")
        print("| 建玉 | 決済 | 保有日数 | ロット | 旧 | 新 | 差 | **差/日/0.01** |")
        print("|---|---|---:|---:|---:|---:|---:|---:|")
        opened = {}
        tot = totd = 0.0
        for x, y in zip(ra, rb):
            pid = x["position_id"]
            if x["entry"] == "0":
                opened[pid] = (int(x["time"]), float(x["volume"]))
                continue
            if pma.get(pid) != mg or pid not in opened:
                continue
            t0, v = opened[pid]
            days = (int(x["time"]) - t0) / 86400.0
            dd = float(y["profit"]) - float(x["profit"])
            tot += dd
            totd += days * (v / 0.01)
            r = dd / days / (v / 0.01) if days and v else 0.0
            print("| {} | {} | {:.1f} | {} | {:,.0f} | {:,.0f} | {:+,.0f} | **{:.2f}** |".format(
                dt.datetime.fromtimestamp(t0, dt.UTC).strftime("%Y-%m-%d"),
                dt.datetime.fromtimestamp(int(x["time"]), dt.UTC).strftime("%Y-%m-%d"),
                days, x["volume"], float(x["profit"]), float(y["profit"]), dd, r))
        if totd:
            print(f"\n延べ保有日数（0.01ロット換算）**{totd:,.0f}**　"
                  f"差の合計 **{tot:+,.0f}**　"
                  f"→ **{tot / totd:.3f} 円/日/0.01ロット**")
            print("\n一定なら**スワップのドリフト**である（案の効果でも計測バグでもない）。\n")


if __name__ == "__main__":
    main()
