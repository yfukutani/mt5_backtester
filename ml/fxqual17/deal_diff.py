import csv, glob, os, datetime

A = glob.glob(r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual14\run_deals\mc_oos_V012_*_deals.csv")[0]
B = glob.glob(r"C:\Users\f\source\repos\mt5_backtester\ml\fxqual17\run_deals\mc_oos_M003_*_deals.csv")[0]
NAME = {"20260622": "pb_uj", "20260627": "pb_gj", "20260610": "rsi_uj",
        "20260605": "rsi_eu", "20260774": "rsi_gu", "20260629": "PAIR",
        "20260650": "carry", "20261000": "sca_uj", "20261001": "sca_gj"}


def opens(p):
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if r["entry"] == "0":
            out.append((int(r["time"]), r["magic"], r["volume"], r["price"]))
    out.sort()
    return out


a, b = opens(A), opens(B)
print(f"V012(旧バイナリ) 建玉 {len(a)} 件 / M003(計装入り) 建玉 {len(b)} 件")

# 最初に食い違う位置を探す
i = j = 0
diffs = []
while i < len(a) and j < len(b):
    if a[i] == b[j]:
        i += 1; j += 1
    elif a[i] < b[j]:
        diffs.append(("旧のみ", a[i])); i += 1
    else:
        diffs.append(("新のみ", b[j])); j += 1
diffs += [("旧のみ", x) for x in a[i:]] + [("新のみ", x) for x in b[j:]]

print(f"\n食い違い {len(diffs)} 件（最初の12件）:")
for tag, (t, mg, vol, px) in diffs[:12]:
    ts = datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M")
    print(f"  {tag}  {ts}  {NAME.get(mg, mg):8s} vol={vol:>8s} price={px}")

if diffs:
    t0 = diffs[0][1][0]
    ts = datetime.datetime.utcfromtimestamp(t0).strftime("%Y-%m-%d %H:%M")
    print(f"\n**最初の食い違い: {ts}**")
    n_before = sum(1 for x in a if x[0] < t0)
    print(f"  それ以前の建玉は {n_before} 件で完全一致している")
