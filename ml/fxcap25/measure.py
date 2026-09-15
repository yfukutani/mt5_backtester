"""cap（`MarginCapPct`）の応答曲線を 1:25 で引く。台地の上端が分かっていない。

【なぜこれが残っているか】
`docs/oanda_fx_windows_lev25_20260915.md` で、OOS窓の中央値を最も動かした単一レバーが
**cap だった**（X001 2.25% → X002 3.48%、**+1.23pt**。しかも元本割れ窓が1本→0本）。

ところが 1:25 で測った cap は **75% と 80% の2点しかない**。

    cap75 → 通期OOS 5.09%（DD 56.44% / 1,318取引）
    cap80 → 通期OOS 5.59%（DD 60.88% / 1,329取引）

**ゆるいほうが良い方向に動いている。** 1:100 の段階2は「70〜85%が台地」としていたが、
あれは 1:100 の（＝証拠金が効いていない）土俵の話なので、1:25 には持ち越せない。
**台地の上端がどこか、そもそも上端があるのかが分かっていない。**

cap=100% は「使用証拠金が equity を超えない範囲まで縮める」。
それ以上は意味が無い（100%超はロスカット域）ので、**上限は 100 で頭打ちになるはず**。
その手前で折り返すなら、折り返し点が最適 cap である。

【測る窓】
判定に使えるのは **完全にOOSに収まる W1〜W3**（重みは IS で決めているため）。
通期OOS(55か月)も並べるが、あれは**立ち上がりの1窓が作る**数字なので判定には使わない。

【限界】
- OOS窓は3本しかない。中央値は実質「真ん中の1本」である。
- ここで cap を OOS窓の成績で選べば、**その3本はもう holdout ではなくなる。**
  応答曲線の形（単調か・折り返すか）を見るのが目的であって、
  「最良の cap を1つ選ぶ」ことではない。**選んだ時点で選択バイアスが入る。**
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "_m3", REPO / "ml" / "fxmargin3" / "measure.py")
m3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m3)

ROOT.mkdir(parents=True, exist_ok=True)
m3.RUN_DIR = ROOT / "runs"
m3.CONFIG_DIR = ROOT / "configs"
m3.DEAL_DIR = ROOT / "run_deals"
m3.OUT = ROOT / "results.csv"
m3.LOG = ROOT / "measure.log"
# ロックは fxmargin3 と共有のまま（端末は1台）。

WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09", 24.0),
    "W2": ("2017.11.09", "2019.11.09", 24.0),
    "W3": ("2018.11.09", "2020.11.09", 24.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
}
m3.WINDOWS = WINDOWS
WINS = ("W1", "W2", "W3", "OOS")

cfg = m3.cfg
# X005 と同じ重み。cap だけを動かす。
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

# 既測: cap80 = X005（OOS窓中央値 4.82% / 通期 8.58%）。ここでは 80 を測り直さない。
PROPOSALS = [
    ("Y100", "X005", "重み＋cap100%（使用証拠金がequityを超えない上限）", cfg(7, 1.0, 3, 100, **W)),
    ("Y090", "X005", "重み＋cap90%", cfg(7, 1.0, 3, 90, **W)),
    ("Y095", "X005", "重み＋cap95%", cfg(7, 1.0, 3, 95, **W)),
    ("Y085", "X005", "重み＋cap85%", cfg(7, 1.0, 3, 85, **W)),
    ("Y070", "X005", "重み＋cap70%（下側。折り返しの有無を見る）", cfg(7, 1.0, 3, 70, **W)),
    ("Y060", "X005", "重み＋cap60%（下側）", cfg(7, 1.0, 3, 60, **W)),
]

# 上端から測る。単調に伸びるなら cap100 が最良で、そこで頭打ちのはず。
# 先に両端を押さえておけば、途中で止まっても形が分かる。
ORDER = ["Y100", "Y060", "Y090", "Y070", "Y095", "Y085"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda t: idx.get(t[0], 99))
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params) in props
            for w in WINS if (pid, w) not in done]
    if not jobs:
        print("全案・全窓が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXCAP25_START jobs={len(jobs)} done={len(done)} leverage=1:25")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXCAP25_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
