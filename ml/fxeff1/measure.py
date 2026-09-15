"""証拠金効率ラウンド — 証拠金を食う枠を外し、空いた分を倍率で使い切る。

【なぜこの軸が立つのか】
第8報（cap の応答曲線）で、cap は 60→100% で**単調増加**だった。
折り返しが無い＝**証拠金が律速している**ということである。
cap=100% は「使用証拠金が equity を超えない」上限で、それ以上は開けられない。
つまり **cap という蛇口はもう全開**で、ここから先は
「同じ証拠金で、より稼ぐ枠に使わせる」しか残っていない。

【どの枠を外すかは IS だけで決めた】
`ml/fxeff1/margin_efficiency.py`。1建玉が占有する証拠金を保有時間で積分した
**証拠金日（margin-yen-day）**あたりの純益を、枠ごとに出した。
判断は **IS窓（W7/W8/W9＝2022-11〜2026-06）**だけで行っている。

    IS効率（円/証拠金日）  SCA UJ +6.39 / PB GJ +4.44 / RSI UJ +3.78 / RSI GU +2.85
                          RSI EU +1.36 / SCA GJ +0.41 / Pair +0.34 /
                          PB UJ +0.01 / Carry -0.92

外す候補は IS で下位3枠のうち、**証拠金の占有が大きい**もの:

    Carry   IS効率 -0.92（最下位）・平均保有 185日・IS証拠金日の 6.5%
    PB UJ   IS効率 +0.01（ほぼゼロ）・IS証拠金日の 6.2%
    RSI EU  IS効率 +1.36（5位）だが **IS証拠金日の 43.6% を1枠で占める**
            （OOSでも 45.8%。ピーク時は W1/W2/W8 で使用証拠金の 90〜100%）

3枠あわせて **IS証拠金日の 56%** を占め、IS純益の **28%** しか生んでいない。
**外して空いた証拠金を `GlobalLotMult` で使い切る**、というのが本ラウンドの仮説である。

【評価は OOS窓（W1/W2/W3）で行う】
重みは IS で決め、外す枠も IS の効率で決めた。W1〜W3 は
**完全にOOSに収まる24か月窓**であり、各窓を新規50万円口座として開始する。

【留保 — 先に書いておく】
- OOS窓は3本しかない。中央値は実質「真ん中の1本」を見ているだけである。
- cap は既に W1〜W3 の成績を見て選んでいる（第8報）。
  したがって W1〜W3 は**完全な holdout ではない**。ここで出る数字は上振れ側に偏る。
- 枠を外すと**分散も減る**。月利が上がってもDDが悪化する可能性がある。
  DD は判定に使わないが、必ず併記する。
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
# ロックは fxmargin3 と共有（端末は1台しか使えない）。

WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09", 24.0),
    "W2": ("2017.11.09", "2019.11.09", 24.0),
    "W3": ("2018.11.09", "2020.11.09", 24.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
}
m3.WINDOWS = WINDOWS
WINS = ("W1", "W2", "W3", "OOS")

cfg = m3.cfg

# X005 = 第7報の最良構成の重み。ここを動かす案だけ個別に上書きする。
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)


def eff(mult, cap, off=(), **over):
    """X005 をベースに、枠を止めて（off）重みを上書き（over）する。

    `Mult_*=0` では枠は止まらない（Clamp が最小ロット 0.01 に切り上げるため）。
    枠を止めるには `En_*` を false にする必要がある。
    """
    w = dict(W)
    w.update(over)
    p = cfg(7, 1.0, mult, cap, **w)
    for name in off:
        key = f"En_{name}"
        if key not in m3.BASE:
            raise KeyError(f"未知の枠スイッチ: {key}")
        p[key] = False
    return p


CARRY, PBUJ, RSIEU = "CARRY", "PB_USDJPY", "RSI_EURUSD"

PROPOSALS = [
    # --- A群: 外す効果だけを見る（倍率3のまま・cap100） -------------------
    ("E01", "Y100", "Carry を止める（IS効率 最下位 -0.92・平均保有185日）",
     eff(3, 100, off=(CARRY,))),
    ("E02", "Y100", "PB USDJPY を止める（IS効率 +0.01＝ほぼゼロ）",
     eff(3, 100, off=(PBUJ,))),
    ("E03", "Y100", "RSI EURUSD を止める（IS証拠金日の43.6%を1枠で占める）",
     eff(3, 100, off=(RSIEU,))),
    ("E04", "Y100", "Carry ＋ PB USDJPY を止める",
     eff(3, 100, off=(CARRY, PBUJ))),
    ("E05", "Y100", "Carry ＋ PB USDJPY ＋ RSI EURUSD を止める（IS証拠金日の56%を解放）",
     eff(3, 100, off=(CARRY, PBUJ, RSIEU))),

    # --- B群: 空いた証拠金を倍率で使い切る -------------------------------
    ("E06", "E05", "E05 ＋ 倍率4", eff(4, 100, off=(CARRY, PBUJ, RSIEU))),
    ("E07", "E05", "E05 ＋ 倍率5", eff(5, 100, off=(CARRY, PBUJ, RSIEU))),
    ("E08", "E05", "E05 ＋ 倍率6", eff(6, 100, off=(CARRY, PBUJ, RSIEU))),
    ("E09", "E04", "E04 ＋ 倍率4", eff(4, 100, off=(CARRY, PBUJ))),
    ("E10", "E04", "E04 ＋ 倍率5", eff(5, 100, off=(CARRY, PBUJ))),

    # --- C群: 止めずに弱める（分散を残したまま証拠金を空ける） -----------
    ("E11", "Y100", "RSI EURUSD の重みを 4.0→1.0（止めずに絞る）",
     eff(3, 100, RSI_EURUSD=1.0)),
    ("E12", "Y100", "RSI EURUSD の重みを 4.0→2.0",
     eff(3, 100, RSI_EURUSD=2.0)),
    ("E13", "E11", "E11 ＋ 倍率5（絞った分を全体の倍率で戻す）",
     eff(5, 100, RSI_EURUSD=1.0)),

    # --- D群: 効率の高い枠に寄せる ---------------------------------------
    ("E14", "E05", "E05 ＋ RSI GBPUSD と SCA GBPJPY を 4→6（IS効率の上位へ寄せる）",
     eff(3, 100, off=(CARRY, PBUJ, RSIEU), RSI_GBPUSD=6.0, SCA_GBPJPY=6.0)),

    # --- E群: 実用域の cap=90 での確認 -----------------------------------
    # cap=100 は証拠金維持率100%＝OANDA証券の追証ラインそのもので実運用できない。
    # A〜D群で良かった構成を cap=90 でも測り、実用域で何が残るかを見る。
    ("E15", "E05", "E05 を cap90 で（実用域）", eff(3, 90, off=(CARRY, PBUJ, RSIEU))),
    ("E16", "E07", "E07（倍率5）を cap90 で（実用域）",
     eff(5, 90, off=(CARRY, PBUJ, RSIEU))),
]

# 効きの大きそうな順。途中で止まっても判断に効く数字から埋まる。
ORDER = ["E05", "E07", "E03", "E01", "E06", "E11", "E13", "E04",
         "E02", "E08", "E09", "E12", "E14", "E15", "E16", "E10"]


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
        m3.log(f"FXEFF1_START jobs={len(jobs)} done={len(done)} leverage=1:25")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXEFF1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
