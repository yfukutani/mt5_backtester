"""業者のロット上限を OANDA 相当（10ロット）にして測り直す（第12報）。

【なぜこれが最優先なのか】
第8報は「複利を止めているのは `SYMBOL_VOLUME_MAX`＝**銘柄の1注文上限**」と診断した。
そして `docs/oanda_broker_specs_20260915.md` が実機で測った値はこうだった。

    XM（これまでの全バックテスト）  FX 1注文あたり 50.0 ロット
    OANDA証券（本番）              FX 1注文あたり **10.0 ロット**   ← 1/5

**天井が 1/5 なら、これまで「良い」と出た構成は本番では成立しない。**
第9報の Y100（OOS窓中央値 5.60%）も、fxeff1 の E04（同 8.65%）も、
枠別の重み（第3報・第7報）も、すべて 50 ロットの天井の下で出た数字である。

【このラウンドで切り分けるもの／切り分けないもの】
EA に `BrokerMaxLot` を足し、**端末を替えずに上限だけ**を 10 にする。
分離できるのは **天井の効果だけ**である。

    切り分ける   1注文あたりロット上限（50 → 20 → 10）
    切り分けない フィード差・スプレッド差・スワップ差（OANDA端末で別途測るしかない）

2026-07の検証が「XM/OANDA の大差は tick化しても縮まらず**主因はフィード差**・
一律補正は不適切」と記録している。**本ラウンドは OANDA の答えではなく、
OANDA の答えに必要な2つの要素のうち1つ**である。

【最初に対照を回す】
`BrokerMaxLot=0` は端末の値をそのまま使う＝従来と同一挙動でなければならない。
O000 が Y100 を**1円まで再現すること**を先に確認する。再現しなければ以降は比較できない。

    Y100 実測: W1 6,725,965 / W2 1,348,701 / W3 1,097,587 / OOS 51,320,738
               OOS DD 64.4765% / 1,310取引

【土俵】
すべて X005 の重み・`FxRiskMask=7`・risk 1.0%・`RefCap=0`。
判定は OOS窓（W1/W2/W3）の中央値。cap100 は追証ラインで実運用できないので
cap90（実用域）も併せて測る。

【予想 — 外すと恥ずかしいので先に書く】
第8報の入金感度（上限50のもとで 50万 8.80% → 2,000万 4.81%）から、
**上限を 1/5 にするのは口座を5倍にするのと同じ向き**と外挿した。
外挿値は通期OOSで 7〜8.5%。**これは測定ではないので、外れたらこの外挿を捨てる。**

【留保】
- OOS窓は3本しかない。中央値は実質「真ん中の1本」である。
- cap も重みも W1〜W3 を見て選んでいる。**完全な holdout ではない。**
- `SYMBOL_VOLUME_LIMIT`（**同一銘柄の合計**建玉上限）は未計測である。
  これが 10 なら「1注文を分割して天井を超える」という逃げ道は無い。
  本ラウンドは分割しない＝**保守側**を測っている。
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
m3.CAP_LOG = True          # 上限に何回当たったかを枠別に出す（vmax_n / vmax_cut）
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

# X005 = 第7報の最良構成の重み。
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

CARRY, PBUJ, RSIEU = "CARRY", "PB_USDJPY", "RSI_EURUSD"


def oa(mult, cap, maxlot, off=(), **over):
    """X005 をベースに、業者上限 `maxlot` を掛ける（0=端末の値＝XMの50）。"""
    w = dict(W)
    w.update(over)
    p = cfg(7, 1.0, mult, cap, **w)
    p["BrokerMaxLot"] = maxlot
    for name in off:
        key = f"En_{name}"
        if key not in m3.BASE:
            raise KeyError(f"未知の枠スイッチ: {key}")
        p[key] = False
    return p


PROPOSALS = [
    # --- 対照: 上限を触らない。Y100 を1円まで再現しなければ以降は無効 ------
    ("O000", "Y100", "対照: BrokerMaxLot=0（端末の50のまま）。Y100 の再現確認",
     oa(3, 100, 0)),

    # --- 本題: 天井を OANDA の 10 にする --------------------------------
    ("O001", "O000", "Y100 ＋ 業者上限10（OANDA実機値）", oa(3, 100, 10)),
    ("O002", "O000", "Y100 ＋ 業者上限20（50と10の間・応答曲線の形を見る）",
     oa(3, 100, 20)),

    # --- 実用域（cap90）でも測る。cap100 は追証ラインで使えない ----------
    ("O003", "Y090", "cap90（実用域）＋ 業者上限10", oa(3, 90, 10)),

    # --- fxeff1 の最良構成が天井の下で生き残るか -------------------------
    #     E04（Carry＋PB UJ を止める）は OOS窓中央値 8.65%（上限50での最良）。
    ("O004", "E04", "E04（Carry＋PB UJ を止める）＋ 業者上限10",
     oa(3, 100, 10, off=(CARRY, PBUJ))),
    ("O005", "E09", "E09（E04＋倍率4）＋ 業者上限10",
     oa(4, 100, 10, off=(CARRY, PBUJ))),
    ("O006", "E09", "E09 ＋ 業者上限10 ＋ cap90（実用域の本命）",
     oa(4, 90, 10, off=(CARRY, PBUJ))),

    # --- 天井の下では倍率が効かないはず。効くなら天井が律速ではない ------
    #     上限に張り付いた枠は倍率を上げても増えない。張り付いていない枠だけが増える。
    #     **効かなければ「増レバで取り返す」は閉じる。**
    ("O007", "O004", "E04 ＋ 業者上限10 ＋ 倍率6（天井の下で倍率が効くか）",
     oa(6, 100, 10, off=(CARRY, PBUJ))),
]

# 対照 → 本題 → 実用域 の順。途中で止まっても判断に効く数字から埋まる。
ORDER = ["O000", "O001", "O004", "O003", "O006", "O005", "O002", "O007"]

# O000 が Y100 を再現しなければ止める（第10報の I000_CHECK と同じ作法）。
EXPECT = {"W1": (6725965.0, 579), "W2": (1348701.0, 529),
          "W3": (1097587.0, 508), "OOS": (51320738.0, 1310)}


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
        m3.log(f"FXVMAX1_START jobs={len(jobs)} 業者上限の掃引 leverage=1:25")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "O000" and window in EXPECT and row.get("status") == "OK":
                en, et = EXPECT[window]
                ok = (abs(float(row["net"]) - en) < 1.0
                      and int(row["trades"]) == et)
                m3.log(f"O000_CHECK {window} expected net={en} trades={et} "
                       f"got net={row['net']} trades={row['trades']} "
                       f"-> {'OK' if ok else 'MISMATCH'}")
                if not ok:
                    m3.log("FXVMAX1_ABORT BrokerMaxLot=0 が従来と一致しない。"
                           "EAの変更が既定挙動を壊している。以降は比較できない")
                    return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXVMAX1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
