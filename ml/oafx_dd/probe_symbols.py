# -*- coding: utf-8 -*-
"""BT1/BT2端末で利用できる銘柄名を、本番OANDA端末と突き合わせる。

BT1でのバックテストが `symbol USDJPY not exist` で失敗した。端末自体は口座
900285086 で正常に認証され64銘柄を同期しているので、接続の問題ではなく
**銘柄名が違う**（サフィックス付き等）可能性が高い。

MT5のsymbols.rawはバイナリだが、銘柄名はASCIIで先頭に並ぶため抽出できる。
本番端末と比較して、必要ならconfigのsymbol指定とSym_*入力を合わせる。
"""
import re
import sys
from pathlib import Path

TERMS = {
    "本番OANDA": r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\EE0304F13905552AE0B5EAEFB04866EB",
    "BT1": r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\6142D304BFF2E6AB353977162D6F452C",
    "BT2": r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\06EBB62A36630B6356B2240C609DE508",
}
WANT = ["USDJPY", "GBPJPY", "EURUSD", "GBPUSD", "AUDJPY", "XAUUSD"]


def symbols_of(base: Path):
    """bases/*/symbols.raw から銘柄名を拾う。"""
    found = set()
    for raw in base.glob("bases/*/symbols.raw"):
        try:
            data = raw.read_bytes()
        except OSError:
            continue
        for m in re.finditer(rb"[A-Z][A-Z0-9._#+-]{3,15}", data):
            s = m.group().decode("ascii", "ignore")
            if 4 <= len(s) <= 16:
                found.add(s)
    return found


def main():
    tables = {}
    for name, path in TERMS.items():
        p = Path(path)
        if not p.is_dir():
            print("%-10s ディレクトリなし" % name)
            continue
        syms = symbols_of(p)
        tables[name] = syms
        print("%-10s 抽出銘柄数=%d" % (name, len(syms)))

    print("\n=== 主要銘柄の有無 ===")
    print("%-10s %s" % ("端末", "  ".join("%-9s" % w for w in WANT)))
    for name, syms in tables.items():
        marks = []
        for w in WANT:
            if w in syms:
                marks.append("%-9s" % "○")
            else:
                cand = sorted(s for s in syms if s.startswith(w))
                marks.append("%-9s" % (cand[0] if cand else "×"))
        print("%-10s %s" % (name, "  ".join(marks)))

    if "BT1" in tables and "本番OANDA" in tables:
        only_prod = sorted(tables["本番OANDA"] - tables["BT1"])[:15]
        only_bt1 = sorted(tables["BT1"] - tables["本番OANDA"])[:15]
        print("\n本番にありBT1に無い(先頭15): %s" % ", ".join(only_prod))
        print("BT1にあり本番に無い(先頭15): %s" % ", ".join(only_bt1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
