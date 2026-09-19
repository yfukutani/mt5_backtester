"""第21報 `ml/fxqualjfl` — 「取引を捨てる」のではなく「ロットだけ抑える」を測る。

【この軸が新しい理由】
既存の `ScaFilRangeMin` は **狭いレンジの取引そのものを捨てる**。
本ラウンドの `LotFloorMask` / `LotFloorRatio` は **取引を全部残したまま、
ロット計算に渡す SL距離だけを下限で丸める**。発注時刻も採否も SL価格も変えない。

`risk%` では `lot = リスク額 ÷ SL距離` なので、**分母が小さい取引ほど重い。**
- SCA の分母＝アジア時間のレンジ幅（|entry-sl|/entry は 0.0017〜0.0247 と 12〜15倍ばらつく）
- PB の分母＝2×ATR（同 0.0025〜0.0119 と 3〜5倍）
- RSI 3枠は固定pips、Pair と Carry は SL を置かない → **この軸は存在しない**

**固定ロット構成では完全に no-op である。** だから「固定ロットでの効き幅」では
価値を測れない。これは第20報の中心的発見（同じ EA 変更が複利では 6.3〜155倍）の
直接の帰結で、Codex も独立に同じ形を最優先に挙げた
（`docs/codex_oafx_round11_20260919.md`）。

【対照との関係】
`ml/fxqual10` / `ml/fxqualfloor` の `ScaFilRangeMin` と**同じ枠・同じ分母**を扱うが、
処方が違う。両者を並べれば「**round10 の +150,369 は、悪い取引を捨てたから出たのか、
重みを下げたから出たのか**」が分かる。これは採用形の選択に直接効く
（捨てる案は OOS で取引を 266→49 まで削る＝枠がほぼ消える。重みを下げる案は全部残す）。

【事前の予想】
- **J001〜J003（SCA USDJPY）: プラス。** 残高比の往復損益 R で割ると、
  最狭分位が**3窓すべてで単独最悪**（OOS −7.3% / IS −4.5% / FULL −11.1%）で、
  かつ平均ロットが最広分位の 4.3倍ある。重みを落とす方向は素直に効くはず。
  ただし **round10 の「捨てる」案ほどは効かない**と予想する。捨てる案は損失そのものを
  ゼロにするが、こちらは縮めるだけである。
- **J004（SCA GBPJPY）: マイナスと予想する。** 同じ R で割ると、この枠は
  **最狭分位が3窓すべてで最良**（OOS +42.4% / IS +4.9% / FULL +50.5%）で、
  平均ロットも最大。**フロアはこの枠の一番良い部分を削る。**
  Codex は「GBPJPY こそ複利で測る価値がある（狭い分母が損失を増幅している仮説は強い）」
  と書いたが、**実測の分位は逆を示している。** ここは意見が割れているので測る。
  なお `docs/rejected_strategies.md` §10 の B1（レンジ幅 上位25/50%のみ）は
  GBPJPY で OOS −84.4% と棄却済みで、これも「狭い側が良い」と整合する。
- **J005/J006（PB 2枠）: 小さい、符号は不明。** R の分位では PB の最広分位が
  IS/FULL でマイナス（−8.0% / −4.7%）で、**最狭側が悪いという証拠が無い。**
  つまり PB のサイジングの歪みは、今のところ**損ではなく得の方向に働いている。**
  Codex はここを最優先に挙げたが、**私は見込みが低いと見る。**
  測るのは「PB でも同型の歪みがあるか」を1回で閉じるためである。

【窓】OOS / IS。FULL は採否が決まってから。
【基準】F003（全複利・倍率1 ＋ 採用候補2件）＝ `fxqual10/G000`・`fxqualfloor/H000` と同一。
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
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}
WINS = ("OOS", "IS")

BASE = {
    "MarginCapPct": 0,
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
    # 本ラウンドで追加した入力。0 は完全な no-op（対照でも明示的に書いて残す）
    "LotFloorMask": 0, "LotFloorRatio": 0.0,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

R036 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
            RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0)
CAND = {"RsiMechMask_UJ": 124, "PbSlopeATR_UJ": 1.40}
F003 = dict(R036, **CAND)

# LotFloorMask: bit0=PB_UJ bit1=PB_GJ bit2=SCA_UJ bit3=SCA_GJ
M_PB_BOTH, M_SCA_UJ, M_SCA_GJ = 3, 4, 8


def t(base, **over):
    p = dict(base)
    for k, v in over.items():
        p[k] = v
    return p


def fl(mask, x):
    return {"LotFloorMask": mask, "LotFloorRatio": x}


PROPOSALS = [
    ("J000", "fxqual10/G000",
     "対照: F003。G000 / H000 と1円まで一致すること（EA を差し替えたので回帰試験）",
     F003),

    ("J001", "J000", "SCA UJ 分母フロア 0.0040（およそ OOS 中央値・IS p20）",
     t(F003, **fl(M_SCA_UJ, 0.0040))),
    ("J002", "J000", "SCA UJ 分母フロア 0.0055（OOS p85 / IS 中央値）",
     t(F003, **fl(M_SCA_UJ, 0.0055))),
    ("J003", "J000", "SCA UJ 分母フロア 0.0070（IS p75 付近。ここより上は台地の外と見る）",
     t(F003, **fl(M_SCA_UJ, 0.0070))),

    ("J004", "J000", "SCA GJ 分母フロア 0.0055（**マイナスを予想する反証点**）",
     t(F003, **fl(M_SCA_GJ, 0.0055))),

    ("J005", "J000", "PB 2枠 分母フロア 0.0055（両枠の中央値付近）",
     t(F003, **fl(M_PB_BOTH, 0.0055))),
    ("J006", "J000", "PB 2枠 分母フロア 0.0070（p70〜p80 付近）",
     t(F003, **fl(M_PB_BOTH, 0.0070))),
]

# 対照 → 予想プラス（SCA UJ）→ 反証点（SCA GJ）→ 見込みの低い PB、の順。
# 途中で止まっても、判断に効く順に結果が揃う。
ORDER = ["J000", "J001", "J002", "J003", "J004", "J005", "J006"]


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
        m3.log(f"FXQUALJFL_START jobs={len(jobs)} 分母フロア（取引は捨てずロットだけ抑える）")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "J000" and window == "OOS" and row.get("status") != "OK":
                m3.log("FXQUALJFL_ABORT 対照が失敗した。中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUALJFL_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
