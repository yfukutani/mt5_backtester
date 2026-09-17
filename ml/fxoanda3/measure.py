"""OANDA で**生き残る** cap 水準はどこか（第15報）。

【なぜ測るのか】
第14報（`docs/oanda_stopout_level_20260917.md`）で分かったこと:

    XM    `position stop out triggered at **19.02%**`   維持率20%まで耐える
    OANDA `position stop out triggered at **99.77%**`   維持率100%で切られる

`MarginCapPct` は **発注時**に「使用証拠金 ≦ equity × cap%」を掛けるだけで、
**建てた後の維持率を保証しない。**

    cap90 で建てた直後の維持率 = 1 ÷ 0.90 ≒ **111%**  → OANDA は 11% 逆行で切る
    cap50 なら                  = 1 ÷ 0.50 =  **200%**
    cap33 なら                  = 1 ÷ 0.33 ≒  **300%**

XM で 6% を超えて見えた構成（E04/E09/E15）はどれも cap90〜100 で、
OANDA では **P001 が4か月でロスカットされてテストごと打ち切られた**。

**だから「どの cap なら窓を最後まで走り切れるか」を先に決める。**
成績の比較はそのあとである。走り切れない構成の純益もDDも読んではいけない。

【判定の順序 — ここが他ラウンドと違う】
1. **完走したか**（deals の最終時刻が窓の終端に届いているか）。届かないものは**失格**。
2. 完走したものだけで OOS窓の月利中央値を比べる。

`ml/fxoanda3/truncation_check.py` が 1 を機械的に判定する。

【土俵】
OANDA端末（BT1）・1:25・`every_tick`・入金50万円・`BrokerMaxLot=0`（端末の10がそのまま効く）。
枠は E04 相当（Carry と PB USDJPY を外す）に固定し、**cap だけを振る。**
Carry は OANDA では D1始値の成行が通らないので、どのみち外すのが前提になる。

【予想 — 外すと恥ずかしいので先に書く】
- cap70 でも維持率143%なので**落ちる**と予想する。
- cap50（維持率200%）で完走し始める。
- 完走する範囲の OOS窓中央値は **2〜3%** と予想する
  （XM の cap60 が 2.81% だったので、それにフィード差 −27% を掛けると 2% 前後）。
- **つまり目標6%には届かない。** 届いたらこの予想を捨てる。

【留保】
- cap を下げると使用証拠金が減るので、**天井（1注文10ロット）はますます効かなくなる。**
- OOS窓は3本しかない。
- テスターのスワップは現在値の一律適用。Carry を外しているので影響は小さい。
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

OANDA_HASH = "6142D304BFF2E6AB353977162D6F452C"
m3.EXE = r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"
m3.EA_EX5 = (Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal") / OANDA_HASH
             / "MQL5" / "Experts" / "MIX_EA_SIMVERIFY.ex5")
m3.ROOT = ROOT          # ロックは OANDA 側で独立（XM のパイプラインと並行して走る）

ROOT.mkdir(parents=True, exist_ok=True)
m3.RUN_DIR = ROOT / "runs"
m3.CONFIG_DIR = ROOT / "configs"
m3.DEAL_DIR = ROOT / "run_deals"
m3.OUT = ROOT / "results.csv"
m3.LOG = ROOT / "measure.log"
m3.CAP_LOG = True

WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09", 24.0),
    "W2": ("2017.11.09", "2019.11.09", 24.0),
    "W3": ("2018.11.09", "2020.11.09", 24.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
}
m3.WINDOWS = WINDOWS
WINS = ("W1", "W2", "W3", "OOS")

cfg = m3.cfg
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

CARRY, PBUJ = "CARRY", "PB_USDJPY"


def oa(mult, cap, off=(CARRY, PBUJ)):
    p = cfg(7, 1.0, mult, cap, **W)
    for name in off:
        key = f"En_{name}"
        if key not in m3.BASE:
            raise KeyError(f"未知の枠スイッチ: {key}")
        p[key] = False
    return p


PROPOSALS = [
    # --- cap を下げていく。維持率＝1/cap。-----------------------------------
    ("S050", "E04", "cap50（建てた直後の維持率 200%）", oa(3, 50)),
    ("S033", "E04", "cap33（維持率 303%・かなり保守的）", oa(3, 33)),
    ("S060", "E04", "cap60（維持率 167%）", oa(3, 60)),
    ("S070", "E04", "cap70（維持率 143%・落ちると予想）", oa(3, 70)),
    ("S025", "E04", "cap25（維持率 400%・ほぼ確実に完走するはず）", oa(3, 25)),
    # --- 完走する cap が見つかったら、倍率で取り返せるかを見る ---------------
    ("S050x4", "S050", "cap50 ＋ 倍率4", oa(4, 50)),
    ("S050x2", "S050", "cap50 ＋ 倍率2（落ちるなら倍率を下げる方向も見る）", oa(2, 50)),
]

# 真ん中から測る（二分探索の気分）。落ちる/落ちないの境界を早く挟む。
ORDER = ["S050", "S070", "S033", "S060", "S025", "S050x4", "S050x2"]


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
        m3.log(f"FXOANDA3_START jobs={len(jobs)} OANDA端末(BT1) cap掃引 "
               f"判定は「完走したか」が先")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXOANDA3_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
