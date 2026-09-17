"""段階3の各構成が、fxrisk3 の対応案と「意図した差」しか持たないことを機械的に確かめる。

手写しのパラメータで測ると、cap の効果だと思っていたものが実は別の入力の差だった、
という事故が起こる。ここで差分を明示し、意図した差以外が1つでもあれば落とす。
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("m", Path(__file__).parent / "measure.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 各案が base に対して持ってよい差（MarginCapPct は常に許す）
ALLOWED = {
    "U000": {}, "U001": {}, "U002": {}, "U003": {},
    "U006": {"GlobalLotMult": 3}, "U007": {"GlobalLotMult": 3},
    "U008": {}, "U004": {}, "U005": {},
    # 枠別の重み案は Mult_* だけが base と異なってよい（倍率・マスクは T036 のまま）
    "U010": {"Mult_PB_USDJPY": 0.3, "Mult_RSI_USDJPY": 2.0, "Mult_RSI_EURUSD": 4.0,
             "Mult_RSI_GBPUSD": 4.0, "Mult_PAIR": 8.0, "Mult_CARRY": 0.75,
             "Mult_SCA_USDJPY": 12.0, "Mult_SCA_GBPJPY": 12.0},
    "U011": {"Mult_PB_USDJPY": 0.5, "Mult_RSI_USDJPY": 2.0, "Mult_RSI_EURUSD": 4.0,
             "Mult_RSI_GBPUSD": 4.0, "Mult_PAIR": 4.0, "Mult_CARRY": 0.75,
             "Mult_SCA_USDJPY": 4.0, "Mult_SCA_GBPJPY": 4.0},
}

ref = {}
for r in csv.DictReader(open(REPO / "ml/fxrisk3/results.csv", encoding="utf-8")):
    ref.setdefault(r["proposal_id"], json.loads(r["parameter_json"]))

bad = 0
for pid, base, desc, p in m.PROPOSALS:
    q = dict(p)
    cap = q.pop("MarginCapPct")
    exp = dict(ref[base])
    diff = {k: (exp.get(k), q.get(k)) for k in set(exp) | set(q) if exp.get(k) != q.get(k)}
    allowed = ALLOWED[pid]
    unexpected = {k: v for k, v in diff.items() if allowed.get(k) != v[1]}
    mark = "OK " if not unexpected else "NG "
    if unexpected:
        bad += 1
    print(f"{mark}{pid} base={base} cap={cap} 意図した差={diff or 'なし'}")
    if unexpected:
        print(f"    !! 意図しない差: {unexpected}")

print()
print("NG件数:", bad)
raise SystemExit(1 if bad else 0)
