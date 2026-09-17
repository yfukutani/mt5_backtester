"""判定の標本を 3本 → 7本 に増やす（第15報）。

【なぜこれが要るのか】
判定は「OOS窓の月利中央値」だが、**OOS窓は3本しかない**（W1/W2/W3）。
3本の中央値は**文字どおり真ん中の1本**であり、しかも W1 は必ず最上位に来るので、
**実質は W2 か W3 のどちらか1本が判定している**（第10報 §4b で確認）。

第2報・第7報で2度「窓に切ったら消えた」を経験しているのに、
**その窓自体が3本しかない**というのは同じ穴である。

【窓の作り方】
OOS期間（2016.11.09〜2021.06.20・55か月）に 24か月窓を **6か月刻み**で置く。

    V1  2016.11.09 - 2018.11.09   （= 既存 W1）
    V2  2017.05.09 - 2019.05.09   **新規**
    V3  2017.11.09 - 2019.11.09   （= 既存 W2）
    V4  2018.05.09 - 2020.05.09   **新規**
    V5  2018.11.09 - 2020.11.09   （= 既存 W3）
    V6  2019.05.09 - 2021.05.09   **新規**
    V7  2019.06.20 - 2021.06.20   **新規**（OOSの右端に寄せる）

各窓は**新規50万円口座として開始**する（建玉の持ち越しは無い）。

> [!warning] **7本は独立な7標本ではない。** 6か月刻みなので隣接窓は18か月を共有する。
> 増えるのは「真ん中がどこか」の解像度であって、統計的な自由度ではない。
> **中央値の信頼区間を主張するのには使えない。**

【土俵】
XM端末・1:25・`every_tick`・入金50万円・`BrokerMaxLot=0`。
天井は判定に効かないことが第12報で確認済みなので、ここでは上書きしない。
cap は**実用域の 90%**に統一する（cap100 は追証ラインで実運用できない）。

【測る構成】
第12報までで中央値が高かった3つと対照。すべて cap90 に揃えて比較する。

    Q000  対照: X005（9枠すべて）             ＝ Y090
    Q001  Carry＋PB UJ を外す・倍率3          ＝ E04 の cap90 版
    Q002  Carry＋PB UJ を外す・倍率4          ＝ E09 の cap90 版
    Q003  Carry＋PB UJ＋RSI EU を外す・倍率3  ＝ E15 と同じ構成

【予想 — 外すと恥ずかしいので先に書く】
新規4窓（V2/V4/V6/V7）は、**既存3窓より悪い**と予想する。
理由: 既存3窓を見て構成を選んでいるからで、選択に使っていない窓のほうが低く出るのが自然である。
**中央値は下がる方向**に動くと見る。どれくらい下がるかは分からない。
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
m3.CAP_LOG = False          # 本ラウンドは配分の中身ではなく分布を見る

WINDOWS = {
    "V1": ("2016.11.09", "2018.11.09", 24.0),
    "V2": ("2017.05.09", "2019.05.09", 24.0),
    "V3": ("2017.11.09", "2019.11.09", 24.0),
    "V4": ("2018.05.09", "2020.05.09", 24.0),
    "V5": ("2018.11.09", "2020.11.09", 24.0),
    "V6": ("2019.05.09", "2021.05.09", 24.0),
    "V7": ("2019.06.20", "2021.06.20", 24.0),
}
m3.WINDOWS = WINDOWS
# 新規窓を先に回す。既存3窓（V1/V3/V5）は別ラウンドで測った値と一致するはずで、
# 一致の確認より**新しい情報**のほうが先に要る。
WINS = ("V2", "V4", "V6", "V7", "V3", "V5", "V1")

cfg = m3.cfg
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

CARRY, PBUJ, RSIEU = "CARRY", "PB_USDJPY", "RSI_EURUSD"


def oa(mult, cap, off=()):
    p = cfg(7, 1.0, mult, cap, **W)
    for name in off:
        key = f"En_{name}"
        if key not in m3.BASE:
            raise KeyError(f"未知の枠スイッチ: {key}")
        p[key] = False
    return p


def prod():
    """本番現行（`RefCap_*=78,000`・倍率1・cap無し）。"""
    p = cfg(0, 1.0, 1, 0)
    p["RefCap_PB_USDJPY"] = 78000
    p["RefCap_PB_GBPJPY"] = 78000
    p["RefCap_CARRY"] = 78000
    return p


PROPOSALS = [
    ("Q001", "E04", "Carry＋PB UJ を外す・倍率3・cap90", oa(3, 90, (CARRY, PBUJ))),
    ("Q003", "E15", "Carry＋PB UJ＋RSI EU を外す・倍率3・cap90",
     oa(3, 90, (CARRY, PBUJ, RSIEU))),
    ("Q002", "E09", "Carry＋PB UJ を外す・倍率4・cap90", oa(4, 90, (CARRY, PBUJ))),
    ("Q000", "Y090", "対照: X005（9枠すべて）・倍率3・cap90", oa(3, 90)),
    # 本番現行。**OANDA側（ml/fxoanda2 の P000）と同じ窓で対になる**ので、
    # 「フィード差が窓ごとにどれだけか」を素の構成で測れる（倍率もcapも掛かっていない）。
    ("Q004", "本番現行", "本番現行（RefCap=78,000・倍率1・cap無し）", prod()),
]

ORDER = ["Q001", "Q003", "Q004", "Q002", "Q000"]


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
        m3.log(f"FXWIN2_START jobs={len(jobs)} 24か月窓7本（6か月刻み）leverage=1:25 cap=90")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXWIN2_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
