# -*- coding: utf-8 -*-
"""各案が Y100（X005＋cap100）に対して意図した差しか持たないことを機械検査する。

手で書いた dict は必ずどこかで写し間違える。差分を目で読める形にして、
「説明文に書いていない差」が混ざっていないことを確認する。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_eff", ROOT / "measure.py")
eff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eff)

m3 = eff.m3
REF = eff.eff(3, 100)          # Y100 = X005 の重み ＋ cap100・倍率3・枠は全部入り

print("# 各案の Y100(X005＋cap100・倍率3) からの差分")
print("")
print("| 案 | 差分 | 説明 |")
print("|---|---|---|")
ng = 0
for pid, base, desc, params in eff.PROPOSALS:
    full = dict(m3.BASE)
    full.update(params)
    ref_full = dict(m3.BASE)
    ref_full.update(REF)
    diff = []
    for k in sorted(set(full) | set(ref_full)):
        a, b = ref_full.get(k), full.get(k)
        if a != b:
            diff.append(f"`{k}` {a}→{b}")
    if not diff:
        diff = ["（差分なし）"]
        ng += 1
    print(f"| {pid} | {' / '.join(diff)} | {desc} |")

# En_* が本当に BASE に存在するか（存在しないキーを足すと EA 側で無視される）
missing = [k for k in ("En_CARRY", "En_PB_USDJPY", "En_RSI_EURUSD") if k not in m3.BASE]
print("")
print(f"BASE に無い枠スイッチ: {missing if missing else 'なし'}")
print(f"差分なしの案: {ng} 件")
sys.exit(1 if (missing or ng) else 0)
