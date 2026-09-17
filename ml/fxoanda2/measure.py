"""**OANDA端末・OANDAフィード**で上位候補を測り直す（第14報）。

【なぜこれが最後に残った最大の留保なのか】
2026-09-15 以降の数字はすべて **XM端末・XMフィード・XM銘柄仕様**である。
2026-09-17 の実測で留保は2つのうち1つに減った。

    ① 銘柄仕様（1注文10ロット）→ **解消**。判定窓では天井にそもそも当たらない
       （`docs/oanda_vol_limit_20260917.md`。O001 の W2/W3 は上限50の対照と1円まで同一）
    ② フィード差・スプレッド差・スワップ差 → **未解消。これが本ラウンド**

【既に1度測っている。その結果が重い】
`ml/fxoanda1`（2026-09-10・R001/R031/R035/R037 を同一EA・同一ビルドで両端末）は
**OOS で一貫して −24.6〜−28.8%** という差を出している。

    R001 本番現行  XM   119,537 → OANDA    86,828   **−27.4%**
    R031           XM   893,675 → OANDA   639,894   **−28.4%**
    R035           XM 1,415,411 → OANDA 1,007,556   **−28.8%**
    R037 当時最良  XM 2,071,976 → OANDA 1,562,929   **−24.6%**

**ブック全体では OANDA のほうが 1/4 ほど悪い。** ただし枠別には符号が入れ替わる
（R037 OOS: PB USDJPY **+46%** / RSI EURUSD は XM −1,325 が OANDA **+198,835** /
RSI USDJPY **−68%** / Carry は D1始値の成行が通らず 7取引 → **2取引**）。
**一律補正が不適切なのはこのため。ブック単位で測るしかない。**

> もしこの −25% が本ラウンドの候補にも効くなら、XM で中央値 6.65% だった E15 は
> **5.7% 前後に落ちて 6% を割る。** 本ラウンドは「届いたか」を決める測定である。

【OANDA端末で起きると分かっている問題】
- **Carry(AUDJPY) は D1 始値の成行が `[market closed]` で失敗する**（OANDA東京サーバー）。
  `MIX_EA_SIMVERIFY` に `SignalTimeframe` 相当は無いので、Carry はほぼ建たない。
  **本命（E04/E09/E15 系）はどれも Carry を止めている**ので本命には影響しない。
  影響を受けるのは対照（P003）だけで、**対照が悪く出るのは Carry のせいかもしれない**と
  読む必要がある。
- GOLD/ETH/BTC 枠は `En_*` で止まっているので銘柄名の差（GOLD vs XAUUSD）は出ない。
- FX 5銘柄は OANDA でもサフィックス無しのプレーン名で、そのまま解決する。

【土俵】
入金50万円・レバレッジ **1:25**・`every_tick`・`BrokerMaxLot=0`
（**端末の実値 10 がそのまま効く**。上書きしない）。
判定は OOS窓（W1/W2/W3・各24か月を新規50万円口座として開始）の月利中央値。

【他ラウンドと並行して走らせる】
端末が別インストール（`OANDA MetaTrader 5_BT1`）なので、XM側のラウンドと**同時に回せる**。
`kill()` は `EXE` の**インストールフォルダで絞って**落とすので、
片方のタイムアウトがもう片方のテスターを巻き添えにしない（確認済み）。
そのため **ロックも fxmargin3 と共有しない**（`m3.ROOT` をこのディレクトリに向ける）。

【留保】
- OOS窓は3本しかなく、**構成は XM の3本を見て選んでいる**ので OANDA 側も holdout ではない。
- テスターのスワップは「現在のスワップ率を全履歴に一律適用」する近似。
  Carry を含む構成の損益は数倍ブレることが実測されている。本命は Carry を止めている。
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

# --- ここだけが他ラウンドと違う: 端末を OANDA のバックテスト用インストールに向ける ---
OANDA_HASH = "6142D304BFF2E6AB353977162D6F452C"
m3.EXE = r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"
m3.EA_EX5 = (Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal") / OANDA_HASH
             / "MQL5" / "Experts" / "MIX_EA_SIMVERIFY.ex5")
# ロックを fxmargin3 と共有しない（XM側と並行して走らせるため）。
m3.ROOT = ROOT

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

CARRY, PBUJ, RSIEU = "CARRY", "PB_USDJPY", "RSI_EURUSD"


def oa(mult, cap, off=(), **over):
    """X005 をベースにする。`BrokerMaxLot` は触らない（端末の 10 がそのまま効く）。"""
    w = dict(W)
    w.update(over)
    p = cfg(7, 1.0, mult, cap, **w)
    for name in off:
        key = f"En_{name}"
        if key not in m3.BASE:
            raise KeyError(f"未知の枠スイッチ: {key}")
        p[key] = False
    return p


def prod():
    """本番現行（`RefCap_*=78,000`・倍率1・cap無し）。OANDA側の出発点。"""
    p = cfg(0, 1.0, 1, 0)
    p["RefCap_PB_USDJPY"] = 78000
    p["RefCap_PB_GBPJPY"] = 78000
    p["RefCap_CARRY"] = 78000
    return p


PROPOSALS = [
    # --- まず現行。OANDAフィードでの「いまここ」を同じ土俵で出す -------------
    ("P000", "本番現行", "本番現行（RefCap=78,000・倍率1・cap無し）を OANDAフィードで",
     prod()),

    # --- 本命: XM で中央値6%超だった2案を OANDAフィードの実用域(cap90)で -----
    ("P001", "E15", "E05（Carry＋PB UJ＋RSI EU を外す）＋ cap90。XMでは中央値 6.65%",
     oa(3, 90, off=(CARRY, PBUJ, RSIEU))),
    ("P002", "E09", "E04＋倍率4（Carry＋PB UJ を外す）＋ cap90。XMでは cap100 で 8.49%",
     oa(4, 90, off=(CARRY, PBUJ))),

    # --- 中間: Carry と PB UJ だけ外す（倍率3）------------------------------
    ("P004", "E04", "E04（Carry＋PB UJ を外す）＋ cap90", oa(3, 90, off=(CARRY, PBUJ))),

    # --- 対照: XM の Y090。Carry を含むので OANDA では建たない見込み ---------
    ("P003", "Y090", "対照: X005＋cap90（Carry を含む。OANDAでは Carry がほぼ建たない見込み）",
     oa(3, 90)),
]

# 現行 → 本命2つ → 中間 → 対照 の順。途中で止まっても判断に効く数字から埋まる。
ORDER = ["P000", "P001", "P002", "P004", "P003"]


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
        m3.log(f"FXOANDA2_START jobs={len(jobs)} OANDA端末(BT1)・OANDAフィード "
               f"leverage=1:25 BrokerMaxLot=端末値(10)")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXOANDA2_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
