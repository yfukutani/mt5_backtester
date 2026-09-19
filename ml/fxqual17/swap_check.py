"""先頭一致区間の profit 差を出す。

**時刻・枠・ロット・価格が一致していても、profit が違えばスワップ差**である
（EA の profit 列は DEAL_PROFIT + DEAL_SWAP + DEAL_COMMISSION）。
MT5 テスターは「いまのスワップ率」を全履歴に一律適用するので、
**走らせた日が違うと同じ設定でも損益が変わる**（第19報 oanda_fx_carry_swap_drift）。
"""
import csv, glob, os, datetime, collections

A = glob.glob(r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual14\run_deals\mc_oos_V012_*_deals.csv")[0]
B = glob.glob(r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual17\run_deals\mc_oos_M003_*_deals.csv")[0]
NAME = {"20260622": "pb_uj", "20260627": "pb_gj", "20260610": "rsi_uj",
        "20260605": "rsi_eu", "20260774": "rsi_gu", "20260629": "PAIR",
        "20260650": "carry", "20261000": "sca_uj", "20261001": "sca_gj"}
print("A(V012):", os.path.basename(A))
print("B(M003):", os.path.basename(B))
for p in (A, B):
    print("  更新時刻:", datetime.datetime.fromtimestamp(
        os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M"))


def rows(p):
    r = list(csv.DictReader(open(p, encoding="utf-8")))
    r.sort(key=lambda x: (int(x["time"]), x["entry"], x["position_id"]))
    return r


a, b = rows(A), rows(B)
# 「約定の同一性」は time/magic/entry/volume/price で見る。profit は比較対象。
def key(r):
    return (r["time"], r["magic"], r["entry"], r["volume"], r["price"])


n = min(len(a), len(b))
first_div = None
for i in range(n):
    if key(a[i]) != key(b[i]):
        first_div = i
        break
if first_div is None:
    first_div = n
print(f"\n約定が一致している先頭区間: {first_div} 行（全 {len(a)} / {len(b)} 行）")

da = sum(float(x["profit"]) for x in a[:first_div])
db = sum(float(x["profit"]) for x in b[:first_div])
print(f"  その区間の profit 合計:  旧 {da:,.2f} / 新 {db:,.2f} / **差 {db-da:+,.2f}**")

diff = [(i, a[i], b[i]) for i in range(first_div)
        if abs(float(a[i]["profit"]) - float(b[i]["profit"])) > 0.004]
print(f"  profit だけが違う行: **{len(diff)} 件**")
by = collections.Counter()
for i, x, y in diff:
    by[NAME.get(x["magic"], x["magic"])] += 1
for k, v in by.most_common():
    print(f"    {k}: {v} 件")
for i, x, y in diff[:8]:
    ts = datetime.datetime.fromtimestamp(int(x["time"]), datetime.timezone.utc)
    print(f"    行{i:4d} {ts:%Y-%m-%d} {NAME.get(x['magic'],x['magic']):8s} "
          f"{float(x['profit']):>12,.2f} → {float(y['profit']):>12,.2f}")
if not diff:
    print("  → **スワップ差は無い。MISMATCH は計装だけが原因。**")
