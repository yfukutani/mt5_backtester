"""24か月窓をそれぞれ新規50万円口座として MT5 で実測する（段階3・窓別）。

【なぜこれが要るか】
U011（枠別の重み・保守版）は OOS 55か月で **月利 11.33%・純益 1億8,232万円**を出した。
だがこの数字は「50万円の口座で月利6%」という問いに答えていない——

- 口座は55か月で **50万円 → 1億8,282万円**。最初の14か月で48倍になる。
  幾何平均はこの立ち上がりが作っている。
- 口座が大きくなると**ロットが銘柄上限 `SYMBOL_VOLUME_MAX`=50 に張り付く**
  （新規建玉に占める割合が 2017年 15.1% → 2021年 34.3%）。
  **張り付いた時点でサイジング規則は働いておらず、成績を決めているのは上限値である。**

`ml/fxmargin3/windows_stage3.py` は同じ問いを deal ログの再構成で測り、
U011 の24か月窓の月利を **22.25 / 7.04 / 5.29 / 4.05%（中央値 6.17%）**と出した。
**しかしこの再構成には既知の系統誤差がある**——logged ロットが上限50で切られているため、
`logged × k` は本来のロットを下回り、**窓の月利は下振れして出る**。
向きは分かっても大きさが分からない。**実測でしか決着しない。**

【やること】
各窓を `from_date`/`to_date` に指定して、**入金50万円から始まる独立した run** として回す。
再構成ではないので、上限50の扱いもロットの丸めもEAと実機そのままになる。

【窓】24か月・進め幅12か月。OOS窓は 2016.11.09〜2021.06.20 なので、
**W1〜W3 だけが完全にOOSに収まる**。W4以降はIS（重みを決めた期間）を含むので
**重みを当てにいった期間であり、良く出て当然**である。表では分けて読むこと。

【限界】
- 窓の境界で建玉が切られる（窓頭は建玉なしから、窓尻は強制決済）。
  55か月の連続経路とは厳密には別物である。
- 窓は同じ1本の履歴を切ったものであり、独立標本ではない。符号の数え上げは目安。
"""
from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent

# fxmargin3 の run() をそのまま使う。測定機構を二重に持つと、
# 「窓を変えただけ」のはずの差に実装差が混ざる。
_spec = importlib.util.spec_from_file_location(
    "_m3", REPO / "ml" / "fxmargin3" / "measure.py")
m3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m3)

# 出力先だけ差し替える。**ロック（m3.ROOT/measure.lock）は差し替えない**——
# 端末は1台しか使えず、fxmargin3 と同時に走らせると互いのテスターを殺し合うため、
# ロックは共有していなければならない。
ROOT.mkdir(parents=True, exist_ok=True)
m3.RUN_DIR = ROOT / "runs"
m3.CONFIG_DIR = ROOT / "configs"
m3.DEAL_DIR = ROOT / "run_deals"
m3.OUT = ROOT / "results.csv"
m3.LOG = ROOT / "measure.log"

OOS_END = "2021.06.20"

# 24か月窓・進め幅12か月。ラベルの ✓ は「完全にOOSに収まる」窓。
# OOS は fxmargin3 と同一の55か月窓（U012 を U011 と直接並べるために要る）。
WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09", 24.0),   # ✓ OOS内
    "W2": ("2017.11.09", "2019.11.09", 24.0),   # ✓ OOS内
    "W3": ("2018.11.09", "2020.11.09", 24.0),   # ✓ OOS内
    "W4": ("2019.11.09", "2021.11.09", 24.0),   # OOS 7か月 + IS 5か月
    "W5": ("2020.11.09", "2022.11.09", 24.0),   # IS主体
    "W6": ("2021.11.09", "2023.11.09", 24.0),   # IS
    "W7": ("2022.11.09", "2024.11.09", 24.0),   # IS
    "W8": ("2023.11.09", "2025.11.09", 24.0),   # IS
    # W9 はデータ終端が 2026.06.20 なので19か月しかない。**それでも必ず回す**——
    # windows_stage3.py の再構成で、U011 はこの窓だけ **最大DD 103.0%・月利 −73.97%**
    # ＝**口座が飛んでいる**。9窓中1窓の破綻は、中央値が6%を超えていても採用を止める。
    # 再構成の誤差ではなく本当に飛ぶのかを、実測で確かめる必要がある。
    "W9": ("2024.11.09", "2026.06.20", 19.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),  # fxmargin3 と同一
}
m3.WINDOWS = WINDOWS
OOS_ONLY = ("W1", "W2", "W3")
W24 = ("W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9")

cfg = m3.cfg

# fxmargin3 と同じ入力をそのまま使う（parameter_json を写し違えないこと）。
# 4要素目は回す窓。既定は24か月窓8本。
#
# --- U012 を足した理由（重要）-------------------------------------------------
# U011 の枠別の純益を見ると、182,319,948円のうち
#   PB GJ 81,007,228 / RSI GU 44,832,524 / RSI UJ 25,282,351
# の3枠でほぼ全部である。**ところが PB GJ の重みは 1.0 で、T036 から変えていない。**
# T036 では PB GJ は 3,247,592円だった。**重みを触っていない枠が25倍になっている。**
# これは配分の効果ではなく、「RSI枠を大きくして equity が速く育ち、
# equity連動の PB GJ がその果実を受け取った」＝**複利の二次効果**である。
# 固定ロット枠（Pair 23,513 / SCA_GJ 507,522）は重み4倍にしてもほぼ寄与していない。
#
# だとすれば U011 の本体は「枠別の重み（A7）」ではなく「**RSI枠をもっと大きく張る**」
# という増レバである。**U012 はそれを切り分ける**——RSI 3枠だけを一律4倍にし、
# PB_UJ・Carry の抑制も固定枠の増量も**しない**。
# U012 ≒ U011 なら、A7 は発見ではなく、増レバの言い換えだったことになる。
PROPOSALS = [
    ("U011", "T036", "保守版の重み: PB_UJ 0.5 / RSI_UJ 2 / RSI_EU 4 / RSI_GU 4 / "
                     "Pair 4 / Carry 0.75 / SCA×2 4（fxmargin3 U011 と同一）",
     cfg(7, 1.0, 3, 80, PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0,
         RSI_GBPUSD=4.0, PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0),
     W24),
    ("U012", "T036", "切り分け: RSI 3枠だけを一律4倍。PB_UJ・Carryの抑制も固定枠の増量もしない。"
                     "U011 の効果が『配分』か『RSIの増レバ』かを決める",
     cfg(7, 1.0, 3, 80, RSI_USDJPY=4.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0),
     W24 + ("OOS",)),
    ("U010", "T036", "IS最適重み（過学習の対照）: PB_UJ 0.3 / Pair 8 / SCA×2 12",
     cfg(7, 1.0, 3, 80, PB_USDJPY=0.3, RSI_USDJPY=2.0, RSI_EURUSD=4.0,
         RSI_GBPUSD=4.0, PAIR=8.0, CARRY=0.75, SCA_USDJPY=12.0, SCA_GBPJPY=12.0),
     W24),
    ("U001", "T036", "重み無しの対照: mask=7 / risk1% / 倍率3（T036）",
     cfg(7, 1.0, 3, 80), W24),
    ("U000", "T043", "基準: mask=23 / 倍率1 / SCA_GJ 0.15（T043）",
     cfg(23, 1.0, 1, 0, 0.15), W24),
]

# 窓を先に回しきるのではなく、**案ごとに全窓**を回す。
# 途中で止まっても「その案の分布」は完成しているようにするため。
ORDER = ["U011", "U012", "U010", "U001", "U000"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda t: idx.get(t[0], 99))
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params, wins) in props
            for w in wins if (pid, w) not in done]
    if not jobs:
        print("全案・全窓が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXWIN1_START jobs={len(jobs)} done={len(done)}")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXWIN1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
