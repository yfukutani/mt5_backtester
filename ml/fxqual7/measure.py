"""第17報ラウンド `ml/fxqual7` — SCA の退出側を初めて触る（建値ストップ）。

【なぜここか — この枠の退出は一度も測られていない】
第15報（R倍率の分解）で、**SCA 2枠は TP 到達が 3〜7% しかなく、
利益の大半は22時の強制決済から出ている**ことが分かっている。
つまり「一度伸びたがレンジに戻った」取引が、そのまま22時まで持ち越されている。

退出の軸で第1ラウンドが触ったのは**強制決済の時刻だけ**（Q005〜Q008・
18/20/22/23時を測って**現行22時が最良**）で、**保有中のストップ管理は一度も測っていない。**

SCA GBPJPY はブック最大の枠（OOS +42,219 / IS +73,773）である。
入口側（時間帯・レンジ幅・方向）は第1ラウンドと `ml/fxqual5` でほぼ掃いた。
**残っているのは退出側だけである。**

【実装（第17報で EA に追加・既定 0 で1度も触らない）】
`ScaManageBE()` を毎ティック呼ぶ。含み益が R の `ScaBETriggerR` 倍に達したら
SL を「建値 ＋ `ScaBELockR`×R」へ引き上げる（売りは対称）。

**R（初期SL距離）は TP から逆算する。** 建てた後に SL を動かすと初期値が失われるが、
TP は動かさないので `R = |TP − entry| / rr`（SCA FX は `rr=2.0`）が常に取れる。
**状態を持たないので、テスターでもライブでも同じ値になる。**

`ScaBELockR >= ScaBETriggerR` は OnInit で弾く（動かした瞬間に SL が現値を追い越し、
1度も約定できないので測定にならない）。

【事前の予想 — 期待していない】
**SCA は「22時まで持つ」ことで利益を出している戦略である。**
建値で切れば、いったん伸びてから戻り、また伸びて22時に利確される取引も切ってしまう。
**両窓でプラスになる確率は高くないと見る。**

測る価値があるのは、**この枠の退出側の軸が1つも測られていないから**であって、
月利が上がると思っているからではない。**効き幅の見積もりは月利 ±0.05pt。**
（SCA 2枠の合計は OOS +39,995円＝ブックの34%あるので、入口の刻みより大きくは動きうる。
  ただし**大きく動くのは下向きのほうが確率が高い**と予想する。）

【回帰試験】
Z000（全部0）は `ml/fxqual4` の W000（＝fxqual3 V000・fxqual1 Q000）と
**純益・DD・取引数が1円まで一致**しなければならない。
**このラウンドは EA を差し替えて再コンパイルする**ので、ここが合わなければ
以降の数字を前ラウンドと並べられない。合わなければそこで止める。
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
m3.CAP_LOG = True

m3.WINDOWS = {
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
    "IS":  ("2021.06.20", "2026.06.20", 60.0),
}
WINS = ("OOS", "IS")

PARAMS = {
    "GlobalLotMult": 1,
    "MarginCapPct": 0,
    "BrokerMaxLot": 0,
    "FxRiskMask": 0, "FxRiskPct": 0.5, "FxRiskRefCap": 0,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
    "TagDealTriggers": True,
    "PairSkipAtStop": False, "PairEqualNotional": False,
    "PairMaxHoldBars": 0, "PairEntryZOv": 0.0,
    "RsiMechMask_UJ": 0, "RsiMechMask_EU": 0, "RsiMechMask_GU": 0,
    "PbDiagCounters": True,
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
    "ScaFilMask": 0, "ScaFilRangeMin": 0.0,
    "ScaFilHourFrom": -1, "ScaFilHourTo": -1, "ScaFilBuyOnly": False,
    # 第17報の新入力。**全案で明示的に既定値を書く**（Codex の査読より）。
    "ScaBETriggerR": 0.0, "ScaBELockR": 0.0, "ScaBEMask": 0,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    PARAMS[f"Mult_{_k}"] = 1.0


def t(**over):
    p = dict(PARAMS)
    for k, v in over.items():
        p[k] = v
    return p


# ScaBEMask: bit0=SCA USDJPY(20261000) bit1=SCA GBPJPY(20261001)。0=SCA全枠。
UJ, GJ, BOTH = 1, 2, 3

PROPOSALS = [
    ("Z000", "fxqual4/W000",
     "対照: 建値ストップ全部0。W000/V000/Q000 と1円まで一致すること（再コンパイル後の回帰試験）",
     PARAMS),

    # --- 素の建値ストップ（トリガーを振る）------------------------------------
    ("Z001", "Z000", "SCA 2枠: 含み益 1.0R で SL を建値へ", t(ScaBETriggerR=1.0, ScaBEMask=BOTH)),
    ("Z002", "Z000", "SCA 2枠: 含み益 0.5R で SL を建値へ（早く守る）",
     t(ScaBETriggerR=0.5, ScaBEMask=BOTH)),
    ("Z003", "Z000", "SCA 2枠: 含み益 1.5R で SL を建値へ（遅く守る・TPの3/4）",
     t(ScaBETriggerR=1.5, ScaBEMask=BOTH)),

    # --- 建値より上に置く（利益を少し固定する）--------------------------------
    ("Z004", "Z001", "SCA 2枠: 1.0R で SL を 建値+0.5R へ", t(ScaBETriggerR=1.0, ScaBELockR=0.5, ScaBEMask=BOTH)),
    ("Z005", "Z003", "SCA 2枠: 1.5R で SL を 建値+1.0R へ", t(ScaBETriggerR=1.5, ScaBELockR=1.0, ScaBEMask=BOTH)),

    # --- 枠を分ける（2枠は設計が違う: buf 0.10/0.0・Boost 2.0/6.0）-----------
    ("Z006", "Z001", "SCA GBPJPY だけ 1.0R で建値へ（ブック最大の枠）", t(ScaBETriggerR=1.0, ScaBEMask=GJ)),
    ("Z007", "Z001", "SCA USDJPY だけ 1.0R で建値へ（OOS がマイナスの枠）", t(ScaBETriggerR=1.0, ScaBEMask=UJ)),
]

# 対照 → 素の建値3点（効くか効かないかが最速で分かる）→ 利益固定 → 枠分け。
ORDER = ["Z000", "Z001", "Z002", "Z003", "Z004", "Z005", "Z006", "Z007"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda x: idx.get(x[0], 99))
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params) in props
            for w in WINS if (pid, w) not in done]
    if not jobs:
        print("完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXQUAL7_START jobs={len(jobs)} SCA 建値ストップ7案＋対照")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "Z000" and row.get("status") != "OK":
                m3.log("FXQUAL7_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL7_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
