# -*- coding: utf-8 -*-
"""各案が C00（X005＋cap100・Carry そのまま）に対して意図した差しか持たないことの機械検査。"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_c", ROOT / "measure.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

m3 = c.m3
ref = dict(m3.BASE)
ref.update(c.carry())

print("# 各案の C00（X005＋cap100・Carry そのまま）からの差分")
print("")
print("| 案 | 差分 | 説明 |")
print("|---|---|---|")
ng = 0
for pid, base, desc, params in c.PROPOSALS:
    full = dict(m3.BASE)
    full.update(params)
    diff = [f"`{k}` {ref.get(k)}→{full.get(k)}"
            for k in sorted(set(full) | set(ref)) if ref.get(k) != full.get(k)]
    if not diff:
        if pid != "C00":
            ng += 1
        diff = ["（差分なし）"]
    print(f"| {pid} | {' / '.join(diff)} | {desc} |")

# RefCap_CARRY は BASE ではなく cfg() が入れるので、ref（＝C00の全パラメータ）で確認する。
# Carry* は第11報の新設で、案ごとに yaml へ載る。EA 側の実在はコンパイルで確認済み。
missing = [k for k in ("RefCap_CARRY", "Mult_CARRY", "En_CARRY") if k not in ref]
print("")
print(f"C00 に無い必須入力: {missing if missing else 'なし'}")
print(f"新設入力（C00に無いのが正しい）: {list(c.NEW_INPUTS)}")
print(f"C00 以外で差分なしの案: {ng} 件")
sys.exit(1 if (missing or ng) else 0)
