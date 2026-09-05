"""掃引途中でも、比較可能な案だけで現状を把握する。"""
import csv
import io
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
WINDOWS = ("IS", "OOS")


def read_rows(path):
    # 追記の途中を完成行と誤認しないよう、取得時点の改行までに固定する。
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    data = data[:data.rfind(b"\n") + 1]
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    rows = []
    try:
        for row in reader:
            if None not in row and all(v is not None for v in row.values()):
                rows.append(row)
    except csv.Error:
        # 引用符内の改行で切れた末尾レコードも、次回の読取りに任せる。
        pass
    return rows


def ok_rows(rows, fields=("sca2_net", "sca2_n")):
    for row in rows:
        if row.get("status") != "OK" or row.get("window") not in WINDOWS:
            continue
        try:
            if not all(math.isfinite(float(row[k])) for k in fields):
                continue
            n = float(row["sca2_n"])
            if n < 0 or not n.is_integer():
                continue
        except (KeyError, ValueError, TypeError):
            continue
        yield row


def paired(rows, fields=("sca2_net", "sca2_n")):
    by_id = {}
    for row in ok_rows(rows, fields):
        # 再試行がある場合も、一案を重複して重く評価しないため最新OKを使う。
        by_id.setdefault(row["proposal_id"], {})[row["window"]] = row
    return {pid: w for pid, w in by_id.items() if all(win in w for win in WINDOWS)}


def main():
    rows = read_rows(ROOT / "results.csv")
    counts = {s: sum(r.get("status") == s for r in rows) for s in ("OK", "FAILED")}
    pairs = paired(rows)
    print(f"完了 run 数 {sum(counts.values())} / OK {counts['OK']} / FAILED {counts['FAILED']}")
    print(f"集計対象: 両窓OK・数値有効 {len(pairs)}案（再試行は各窓の最新OK）")
    print("第2枠 magic 20261003 / sca2_net（profit由来・円）")
    print("ファミリー          案数   IS 中央値 / 最大 / 最小       OOS 中央値 / 最大 / 最小")
    families = sorted({r['family'] for r in read_rows(ROOT / 'proposals.csv')})
    for family in families:
        group = [w for w in pairs.values() if w['IS']['family'] == family]
        cells = []
        for win in WINDOWS:
            values = [float(w[win]['sca2_net']) for w in group]
            cells.append(" / ".join(f"{v:,.0f}" for v in (median(values), max(values), min(values))) if values else "--")
        print(f"{family:<19} {len(group):>3}   {cells[0]:<30} {cells[1]}")
    positive = [(pid, w) for pid, w in pairs.items() if all(float(w[x]['sca2_net']) > 0 for x in WINDOWS)]
    positive.sort(key=lambda item: (-min(float(item[1][x]['sca2_net']) for x in WINDOWS), item[0]))
    print(f"両窓正 {len(positive)}案 / 小さい方の降順・上位15件: 案 / family / IS / OOS / 小さい方")
    for pid, w in positive[:15]:
        a, b = (float(w[x]['sca2_net']) for x in WINDOWS)
        print(f"{pid} {w['IS']['family']:<19} {a:>10,.0f} {b:>10,.0f} {min(a,b):>10,.0f}")
    # 参照案は比較集計と分け、片窓しかなくても進捗が確認できるようにする。
    print("参考 S2B014（前ラウンド S2046・13-15時）:")
    for win in WINDOWS:
        found = [r for r in rows if r.get('proposal_id') == 'S2B014' and r.get('window') == win]
        r = found[-1] if found else None
        if r is None:
            print(f"  {win}: 未完了")
        elif list(ok_rows([r])):
            print(f"  {win}: OK sca2_net={float(r['sca2_net']):,.0f} sca2_n={r['sca2_n']} run_id={r['run_id']}")
        else:
            print(f"  {win}: {r.get('status')}（有効なOK数値なし）")


if __name__ == "__main__":
    main()
