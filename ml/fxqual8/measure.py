"""第18報ラウンド `ml/fxqual8` — SCA のリバーサル条件を「サイジング」から「入口」へ移して測る。

⚠️ `ml/fxqual7` は**別セッションのラウンド**（SCA の建値ストップ `ScaBETriggerR`/`ScaBELockR`）。
   このラウンドはその後ろにチェーンする。EA の入力は行が重ならず、両方入れて
   MetaEditor のコンパイルが 0 errors / 0 warnings であることを確認済み。

【このラウンドの根拠 — 測る前に取引ログから確定している数字】
`ml/fxqual4` の W000（対照）の約定ログを、リバーサル Boost が乗ったかどうかで割った:

| 枠 | 群 | 本数(OOS/IS) | OOS 純益 | IS 純益 | 平均R(OOS/IS) |
|---|---|---:|---:|---:|---:|
| SCA GBPJPY | plain(0.01) | 462 / 522 | **−15,585** | **+4,281** | −0.067 / +0.005 |
| SCA GBPJPY | Boost(0.06) | 159 / 162 | **+57,804** | **+69,492** | +0.129 / +0.065 |
| SCA USDJPY | plain(0.01) | 210 / 258 | +739 | +3,677 | +0.004 / +0.026 |
| SCA USDJPY | Boost(0.02) | 56 / 70 | −2,963 | +14,886 | −0.134 / +0.028 |

**SCA GBPJPY の枠純益（OOS +42,219 / IS +73,773）は、全部がリバーサル群から出ている。**
plain 群は OOS で赤字・IS でほぼゼロ、**1取引あたりの優位が両窓とも無い。**

リバーサル条件（`scaDrift` がブレイク方向と逆）は、これまで **Boost_Mult を 2→3→4→6 と
上げるサイジングの条件としてしか扱われていない**（`docs/codex500_round3_20260811.md` ほか）。
**入口フィルタとして使ったことは一度も無い。**

【なぜ予測がそのまま当たるはずか — 第17報の SCA 時間帯フィルタとの違い】
`scaDrift` はレンジ確定（9時）に1回だけ決まり、その日その方向で固定である。
したがってこのゲートは**日×方向の単位**で効き、**取引の入れ替わりが起きない。**
時間帯フィルタは「09時を止めると10-11時にずれる」ので切り直しと実測が一致しなかったが、
**こちらはずれようが無い。上の表がそのまま予測値になる。**
（`scaTradedL/S` は発注が成功したときにしか立たないので、ゲートで落としても
  その日その方向は最後まで沈黙する。他の枠・他の日に影響しない。）

【事前の予想 — 外れたときに後付けできないよう、測る前に書く】
- `RV01`（GJ リバーサルのみ）: **OOS +15,585 / IS −4,281**。
  OOS の効き幅は単利月利 **+0.057pt** で、このテーマで出た最大値（W001 の +0.027pt）の2倍。
  **だが IS が負なので採用しない。**「両窓で符号が揃うこと」がこのプロジェクトのゲートである。
- `RV02`（GJ リバーサルだけ落とす・反証対照）: **OOS −57,804 / IS −69,492**。
  **RV01 の Δ ＋ RV02 の Δ ＝ −(枠純益) が1円まで成立しなければ、切り直しが間違っている。**
  （OOS: +15,585 − 57,804 = −42,219 / IS: −4,281 − 69,492 = −73,773）
- `RV03`（UJ リバーサルのみ）: **OOS −739 / IS −3,677**。両窓マイナス＝棄却。
- `RV04`（2枠とも）: RV01＋RV03 の足し算（**OOS +14,846 / IS −7,958**）になるはず。
- `RV05`（UJ リバーサルだけ落とす）: **OOS +2,963 / IS −14,886**。
- `RV06/RV07`（`ScaFilRangeMin`）: **「結論だけ出てバックテストが無い案」の2件目。**
  `docs/oanda_fx_risk_sizing_20260915.md` §5b が「B1 は純益を18%減らす」と自己訂正済みで、
  `ScaFilRangeMin` は ml/ 配下の全 results.csv で一度も 0 以外になっていない。
  **減益を予想する。** 測るのは「結論だけで止まっている案を残さない」ためである。

**効き幅の見積もり: 最良でも月利 +0.057pt、しかも片窓。対照は OOS 0.428% であり、
目標6%には桁が2つ足りない。これは測る前に書いている。**
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

# fxqual1〜7 と同一の窓。ここを変えると前ラウンドと並べられない。
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
    # 第18報（このラウンド）で足した入力。0＝現行。
    "ScaRevOnlyMask": 0, "ScaRevDropMask": 0,
    # fxqual7（別セッション）が足した入力。0＝現行。明示して交絡を残さない。
    "ScaBETriggerR": 0.0, "ScaBELockR": 0.0,
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


UJ, GJ, BOTH = 1, 2, 3
RANGE_MIN = 0.00595   # X2_HIGH_RISK V105 の IS 閾値。この値でバックテストを取るのは初めて

PROPOSALS = [
    ("RV00", "fxqual4/W000",
     "対照: 第18報の新入力を全部0。W000/V000/X000 と1円まで一致すること", PARAMS),

    # --- 本題: リバーサル条件を「サイジング」ではなく「入口」として使う ----------
    ("RV01", "RV00",
     "SCA GBPJPY: リバーサル条件が成立した足でしか建てない（予測 OOS +15,585 / IS −4,281）",
     t(ScaRevOnlyMask=GJ)),
    ("RV02", "RV00",
     "SCA GBPJPY: 逆にリバーサル足だけ建てない（反証対照・予測 OOS −57,804 / IS −69,492）",
     t(ScaRevDropMask=GJ)),
    ("RV03", "RV00",
     "SCA USDJPY: リバーサル足のみ（予測 OOS −739 / IS −3,677 ＝両窓マイナス）",
     t(ScaRevOnlyMask=UJ)),
    ("RV04", "RV00",
     "SCA 2枠とも リバーサル足のみ（RV01＋RV03 の足し算になるはず）",
     t(ScaRevOnlyMask=BOTH)),
    ("RV05", "RV00",
     "SCA USDJPY: リバーサル足だけ建てない（反証対照・予測 OOS +2,963 / IS −14,886）",
     t(ScaRevDropMask=UJ)),

    # --- 「結論だけ出てバックテストが無い案」の2件目 ---------------------------
    ("RV06", "RV00",
     f"SCA 2枠: レンジ幅フィルタ ScaFilRangeMin={RANGE_MIN}（V105由来・初のMT5計測）",
     t(ScaFilMask=BOTH, ScaFilRangeMin=RANGE_MIN)),
    ("RV07", "RV00",
     f"SCA GBPJPY だけ ScaFilRangeMin={RANGE_MIN}（V105の実証元と同じ枠）",
     t(ScaFilMask=GJ, ScaFilRangeMin=RANGE_MIN)),
]

# 対照 → 本命とその反証対照 → 足し算の確認 → 期待の薄い順。
ORDER = ["RV00", "RV01", "RV02", "RV03", "RV05", "RV04", "RV07", "RV06"]


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
        m3.log(f"FXQUAL8_START jobs={len(jobs)} SCAのリバーサル部分集合を入口に移す")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "RV00" and row.get("status") != "OK":
                m3.log("FXQUAL8_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL8_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
