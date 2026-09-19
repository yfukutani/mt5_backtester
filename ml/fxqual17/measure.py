"""第29報 第17ラウンド `ml/fxqual17` — 「実行可能」と呼んできた構成は、本当に建玉を維持できたのか（12run）。

【このラウンドが答える問い】
第23報以降、`MarginCapPct=90` で成立することを「実行可能」と書いてきた。**不十分だった。**

- `MarginCapPct` は**発注の瞬間**に `使用証拠金 ≦ equity × cap%` を掛けるだけで、
  **建てた後の維持率を保証しない。**
- cap90 の建て直後の維持率は **約111%**。**OANDA のロスカットは維持率 100%**（XM は 20%）。
  **11% の逆行で切られる。**
- **そして本日の全 run は XM 端末**である。MT5 のテスターは端末の口座設定を使うので、
  **モデル化されていたのは XM の 20% であって OANDA の 100% ではない。**

つまり **「元本割れなし」は「XM の 20% に当たらなかった」という意味しかなかった。**

**並行セッションが受動的な計装を EA に入れた**（`cc86514`・`TrackMarginLevel()`）ので、
**最小維持率を初めて実測する。**

【何が言えて、何が言えないか】
維持率は端末のロスカット水準に依存しない量なので、**XM の run から
「OANDA なら切られたか・いつか」は正しく読める。**
**だが「OANDA での月利・DD」は読めない**——切られた時刻 T 以降の経路が別物になるので、
**T 以降の損益はすべて反実仮想として無効**である。

**実務的な使い方: 維持率が 100% を割った構成は、成績を論じる前に候補から落ちる。**

【⚠️ 全 run が同時に回帰試験である】
計装は受動的（読むだけ）なので、**再コンパイルしても損益は1円も変わってはいけない。**
下の期待値は `ml/fxqual14` の実測である。**1件でもずれたら計装が受動的でない**ので、
その場で止めて原因を書く。

【⚠️ `g_mlSamples == 0` を「安全」と読まない】
計装は `ACCOUNT_MARGIN <= 0` と `ACCOUNT_MARGIN_LEVEL <= 0` で黙って return する。
標本ゼロなら EA は `NOT_MEASURED` を書く。**「100% 割れ 0回」と「測れていない」は別物。**

【事前の予想】
- **倍率1（cap90）は 100% を割らない。** cap の cut が OOS で0件なので、
  そもそも証拠金をほとんど使っていない。
- **倍率2 は際どい。** 建て直後が 111% で、OOS の equity DD が 62%。
- **倍率3 は割ると予想する。** equity DD 73.6%（OOS）/ 85.2%（IS）で、
  cut が 2,191件＝cap に張り付いている時間が長い。
- **Carry 抜きは同じ倍率なら余裕があるはず**（Carry が証拠金を長期占有していた分）。
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
m3.CAP_LOG = True          # 計装の出力先。これが無いと1バイトも書かれない。

m3.WINDOWS = {
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}
WINS = ("OOS", "IS")

BASE = {
    "BrokerMaxLot": 0,
    "TagDealTriggers": True,
    "PairSkipAtStop": False, "PairEqualNotional": False,
    "PairMaxHoldBars": 0, "PairEntryZOv": 0.0,
    "RsiMechMask_UJ": 0, "RsiMechMask_EU": 0, "RsiMechMask_GU": 0,
    "PbDiagCounters": True,
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
    "ScaFilMask": 0, "ScaFilRangeMin": 0.0,
    "ScaFilHourFrom": -1, "ScaFilHourTo": -1, "ScaFilBuyOnly": False,
    "ScaBETriggerR": 0.0, "ScaBELockR": 0.0, "ScaBEMask": 0,
    "ScaRevOnlyMask": 0, "ScaRevDropMask": 0,
    "PbArmMaxBars_UJ": 0, "PbArmMaxBars_GJ": 0, "PairRequireZTurning": False,
    "ScaRR_UJ": 0.0, "ScaRR_GJ": 0.0,
    "ScaOvsATR_UJ": 0.0, "ScaOvsATR_GJ": 0.0,
    "RsiTpMask_UJ": 0, "RsiTpMult_UJ": 1.0,
    "RsiTpMask_EU": 0, "RsiTpMult_EU": 1.0,
    "RsiTpMask_GU": 0, "RsiTpMult_GU": 1.0,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

CAND = {
    "RsiMechMask_UJ": 124,
    "PbSlopeATR_UJ": 1.40,
    "ScaFilMask": 1, "ScaFilRangeMin": 0.0048,
}


def cfg(mult, carry=True):
    p = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0,
             GlobalLotMult=mult, RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0,
             RefCap_CARRY=0, MarginCapPct=90, **CAND)
    if not carry:
        p["En_CARRY"] = False
    return p


# (id, 元の id, 説明, params, 期待純益 {窓: 値})
PROPOSALS = [
    ("M001", "fxqual14/V000", "倍率1・cap90（= V000 / E002）", cfg(1),
     {"OOS": 1431459, "IS": 4966997}),
    ("M002", "fxqual14/V010", "倍率2・cap90（= V010 / E005）", cfg(2),
     {"OOS": 3491431, "IS": 30121151}),
    ("M003", "fxqual14/V012", "**倍率3・cap90（= V012）。本日の実測最良。割ると予想**", cfg(3),
     {"OOS": 5457672, "IS": 128659579}),
    ("M004", "fxqual14/V001", "倍率1・cap90・Carry 抜き（= V001）", cfg(1, False),
     {"OOS": 923423, "IS": 1598362}),
    ("M005", "fxqual14/V011", "倍率2・cap90・Carry 抜き（= V011）", cfg(2, False),
     {"OOS": 2282372, "IS": 6539921}),
    ("M006", "fxqual14/V013", "倍率3・cap90・Carry 抜き（= V013）", cfg(3, False),
     {"OOS": 3017380, "IS": 20310786}),
]

# 倍率3 から測る。いちばん割っている可能性が高く、判定に効くのが先に出る。
ORDER = ["M003", "M006", "M002", "M005", "M001", "M004"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda x: idx.get(x[0], 99))
    jobs = [(pid, base, desc, params, w, exp)
            for (pid, base, desc, params, exp) in props
            for w in WINS if (pid, w) not in done]
    if not jobs:
        print("完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXQUAL17_START jobs={len(jobs)} 建玉後の維持率を初めて実測する")
        for pid, base, desc, params, window, exp in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            # 全 run が回帰試験。計装は受動的なので1円も動いてはいけない。
            want = exp.get(window)
            got = row.get("net")
            if want is not None and got is not None:
                ok = (abs(float(got) - want) < 0.5)
                m3.log(f"REGRESSION {pid} {window} expected={want} got={got} "
                       f"-> {'EXACT' if ok else '🔴 MISMATCH（計装が受動的でない）'}")
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL17_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
