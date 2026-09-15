"""24か月窓をそれぞれ新規50万円口座として MT5 で実測する（段階3・窓別）。

**レバレッジ 1:25 で回す**（`mt5bt` 修正後・`verify_leverage()` が毎run確認する）。

【なぜこれが要るか】
1:25 の実測（`ml/fxlev25/`）で、**V005（U011の重み＋cap80%）が
OOS 55か月で月利 8.58%・月利中央値 6.14%**を出した。目標6%を超えている。

だがこれは **55か月の経路1本＝標本1件**であり、重みは IS で決めている。
このプロジェクトは同じ形の数字を一度撤回している——
`docs/oanda_fx_cap_pathdep_20260915.md` は cap の利益増について
「**期間を切ると 4勝5敗**＝経路依存で、弱い局面に偏ったOOS窓だけ見ると勝って見えていた」
と結論した。**同じ物差しを、今度は 1:25 の実測で当て直す。**

さらに通期の数字には、通期ゆえの歪みがある——
V005 の口座は55か月で **50万円 → 4,638万円**まで育つ。
大きくなった口座の成績は「50万円の口座で月利6%」という問いに答えていない。

【やること】
各窓を `from_date`/`to_date` に指定して、**入金50万円から始まる独立した run** として回す。
再構成ではないので、ロットの丸めも証拠金の判定もEAと実機そのままになる。
`windows_stage3.py`（再構成）にあった集計の誤り——窓内で建てた玉の決済を窓外でも数える一方、
月利の分母は決済のある月だけ＝24か月窓のはずが20〜26か月になっていた——も、
実測なら最初から起きない。

【窓】24か月・進め幅12か月。OOS窓は 2016.11.09〜2021.06.20 なので、
**W1〜W3 だけが完全にOOSに収まる**。W4以降はIS（重みを決めた期間）を含むので
**重みを当てにいった期間であり、良く出て当然**である。表では分けて読むこと。
**12か月刻みなので窓は重なっており、9本は独立標本ではない。**

【判定】**中央値が6%を超え、かつ破綻する窓が無いこと。**
どちらか一方では「届いた」と書かない。

【限界】
- 窓の境界で建玉が切られる（窓頭は建玉なしから、窓尻は強制決済）。
  55か月の連続経路とは厳密には別物である。
- W9 はデータ終端の都合で19か月しかない。
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

# ⚠️ 2026-09-15 15:40 差し替え — **1:25 で回す。**
# ここに最初に書いた U011/U010/U012 の一覧は、レバレッジが 1:100 だった前提のもの。
# 1:25 の実測（`ml/fxlev25/`）で構図が変わったので、回す構成を入れ替えた。
#
#   V000 T043（倍率1）      OOS 1,213,378円 / 2.26%月 / DD 29.54% / 1,375取引
#   V001 T036・cap無し      OOS 2,982,564円 / 3.59%月 / DD 68.97% / 1,270取引
#   V002 T036 ＋ cap80%     OOS 9,474,415円 / 5.59%月 / DD 60.88% / 1,329取引
#   V004 U011の重み・cap無し OOS 4,475,250円 / 4.27%月 / DD 46.60% / 1,021取引
#   V005 U011の重み＋cap80%  OOS 45,876,091円 / **8.58%月** / DD 62.00% / 1,306取引
#                            月利中央値 6.14%・上位3か月除外 4.64%
#
# **1:25 では cap が最大のレバーになる。** cap無しだと必要証拠金に足りない注文が
# **丸ごと拒否される**（V004 では RSI EURUSD / GBPUSD が1件も約定しない）。
# cap はそれを「小さいロットで建てる」に変えるので、取引を失わずに済む。
#
# 【このラウンドで答えること】
# V005 の 8.58% は **55か月の経路1本**の値であり、重みは IS で決めている。
# `docs/oanda_fx_cap_pathdep_20260915.md` は cap の利益増について
# 「**期間を切ると 4勝5敗**＝経路依存」と結論して一度撤回している。
# **同じ物差しを 1:25 の実測で当て直す**——24か月窓をそれぞれ新規50万円口座として回す。
# 中央値が6%を超え、かつ**破綻する窓が無い**なら、初めて「届いた」と書ける。
# 4要素目は回す窓。X006（RSI 3枠だけ一律4倍）は切り分け用——
# X005 の重みベクトルのうち、実際に効いているのが「RSI枠を大きく張る」だけなら
# X006 ≒ X005 になる。1:100 の土俵では固定ロット枠（Pair・SCA）の重みは
# 全体の1%未満しか動かしておらず、A7 は増レバの言い換えだった疑いが濃い。
U011_W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
              PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

PROPOSALS = [
    ("X005", "T036", "本命: U011の重み ＋ cap80%。OOS通期で 8.58%月・中央値 6.14%。"
                     "窓に切っても持つか",
     cfg(7, 1.0, 3, 80, **U011_W), W24),
    ("X002", "T036", "T036 ＋ cap80%。重み無しで cap だけ。OOS通期 5.59%月。"
                     "X005 との差が『重み』の寄与",
     cfg(7, 1.0, 3, 80), W24),
    ("X001", "T036", "対照: T036・cap無し。OOS通期 3.59%月。"
                     "X002 との差が『cap』の寄与＝拒否された注文を取り戻した分",
     cfg(7, 1.0, 3, 0), W24),
    ("X006", "T036", "切り分け: RSI 3枠だけ一律4倍 ＋ cap80%。"
                     "X005 の効果が『配分』か『RSIの増レバ』かを決める",
     cfg(7, 1.0, 3, 80, RSI_USDJPY=4.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0), W24),
    ("X000", "T043", "基準: T043（倍率1）。OOS通期 2.26%月。証拠金に届かない構成",
     cfg(23, 1.0, 1, 0, 0.15), W24),
]

# 案ごとに全窓を回す（途中で止まってもその案の分布は完成する）。
ORDER = ["X005", "X002", "X001", "X006", "X000"]


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
