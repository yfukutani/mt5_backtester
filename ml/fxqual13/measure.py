"""第25報 第13ラウンド `ml/fxqual13` — RSI 3枠の機構別 TP（棚卸しの最後の未測定軸）。

【何を閉じるか】
Codex の棚卸し（`docs/codex_oafx_inventory_20260919.md`）が「未実装・未測定」として
残した3軸のうち、SCA の2つは第12ラウンドで閉じた（12案すべて棄却）。
**残る1つが「RSI 3枠の機構別退出」である。これで棚卸しはゼロになる。**

現行は R/B/D の3機構が OR で入口に同居し、**退出は共通の固定 TP ひとつ**しか無い。
「BB 回帰で入った玉と、ダブルボトムで入った玉が、同じ距離で利確する理由は無い」が動機。

【第1段階は TP だけ。SL は触らない】
Codex の助言に従う。SL を動かすと `risk%` の分母（`lot = リスク額 ÷ SL距離`）が変わるので、
**「退出設計の効果」と「1取引の重みづけの変化」が混ざって因果が読めなくなる。**
SL 固定なら変わるのは**勝率と実現RR だけ**である。

【⚠️ このラウンドの要は「全コード」対照である】
`RsiTpMask_*=127`（全コードに同じ倍率）を各枠に置く。これが無いと、
**「機構別にしたから効いた」のか「単にこの枠の TP を伸ばしたから効いた」のかが分離できない。**
第12ラウンドの overshoot 群には、この対照が無くて解釈に困る点があった。

【事前の予想 — 低い】
- Codex の査読は **「0.00pt 中心・定量幅なし」**（`docs/codex_oafx_round12_20260919.md`）。
- **第12ラウンドは12案中10案で IS が悪化した。**「いまの構成は IS について局所最適に
  座っている」と書いた。**本ラウンドも IS はほぼ全点マイナスになると予想する。**
- 枠別の事前:
  - **RSI USDJPY**: 第16報で「**D を含む足で勝ち B 単独で負ける（両窓同符号）**」。
    採用済みの `RsiMechMask_UJ=124` が既に R単独・B単独を落としている。
    **勝っている群の TP を伸ばす（T001）が、このラウンドで唯一まともな上振れ候補。
    それでも ±0.05pt と予想する。**
  - **RSI GBPUSD**: 第16報で「**B 単独が主戦力で落とすものが無い**」。
    主戦力の TP をいじる＝枠の性格そのものを変える。**両方向とも悪化と予想。**
  - **RSI EURUSD**: 第16報で「**B と RB が両方とも符号反転＝入口が窓に対して不安定**」。
    **不安定な入口の退出を最適化しても、その不安定さを増幅するだけ。両窓ばらばらと予想。**

【今回は `CAP_LOG` を立てる】
第12ラウンドは立て忘れて **equity DD を落とした**（`docs/oanda_fx_sleeve_quality_round12_*.md` §4.5）。
OOS では equity DD が残高DD より 11〜16pt 大きいので、**残高DD だけでは採否を論じられない。**
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
m3.CAP_LOG = True     # 第12ラウンドの反省。equity DD を必ず取る。

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
    "MarginCapPct": 0,
    "ScaRR_UJ": 0.0, "ScaRR_GJ": 0.0,
    "ScaOvsATR_UJ": 0.0, "ScaOvsATR_GJ": 0.0,
    # 第25報の新 input（既定で完全に inert でなければならない）
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

# 全複利・倍率1・候補3件 ＝ fxqual10 G005 ＝ fxqualexec E000 ＝ fxqual12 Q000。
COMP1 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
             RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0, **CAND)

# コードのビットマスク（コード = R|B<<1|D<<2、マスク bit = code-1）
M_D_ANY = 8 | 16 | 32 | 64   # 120: D を含む全コード(4,5,6,7)
M_B_ONLY = 2                 # 2:   B 単独(コード2)
M_RB = 4                     # 4:   RB 同時(コード3)
M_ALL = 127                  # 127: 全コード（対照）


def t(**over):
    p = dict(COMP1)
    p.update(over)
    return p


PROPOSALS = [
    # ⚠️ 回帰試験。**OOS +1,431,459 / IS +4,845,523 と1円まで一致しなければならない。**
    #    今回は CAP_LOG=True なので、対照の equity DD もここで取れる
    #    （OOS 34.57% / IS 40.23% ＝ fxqualexec E000 と一致するはず）。
    ("T000", "fxqual12/Q000",
     "対照＝回帰試験: RsiTpMask_* が既定0で inert か（Q000 と1円まで一致すること）",
     COMP1),

    # --- RSI USDJPY: 第16報「D を含む足で勝つ」---
    ("T001", "T000", "UJ: **D を含む群**の TP を 1.5倍（勝っている群を伸ばす）",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=1.5)),
    ("T002", "T000", "UJ: 同 0.7倍（反証点。伸ばすのが正しいなら悪化するはず）",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=0.7)),
    ("T003", "T000", "UJ: **RB 同時**の TP を 0.7倍（D を含まない唯一の許可コード）",
     t(RsiTpMask_UJ=M_RB, RsiTpMult_UJ=0.7)),
    ("T004", "T000", "UJ 対照: **全コード** 1.5倍（機構別かどうかを分離する錨）",
     t(RsiTpMask_UJ=M_ALL, RsiTpMult_UJ=1.5)),

    # --- RSI GBPUSD: 第16報「B 単独が主戦力」---
    ("T005", "T000", "GU: **B 単独**の TP を 1.5倍", t(RsiTpMask_GU=M_B_ONLY, RsiTpMult_GU=1.5)),
    ("T006", "T000", "GU: 同 0.7倍", t(RsiTpMask_GU=M_B_ONLY, RsiTpMult_GU=0.7)),
    ("T007", "T000", "GU 対照: **全コード** 1.5倍", t(RsiTpMask_GU=M_ALL, RsiTpMult_GU=1.5)),

    # --- RSI EURUSD: 第16報「B と RB が符号反転＝入口が不安定」---
    ("T008", "T000", "EU: **B 単独**の TP を 1.5倍", t(RsiTpMask_EU=M_B_ONLY, RsiTpMult_EU=1.5)),
    ("T009", "T000", "EU: 同 0.7倍", t(RsiTpMask_EU=M_B_ONLY, RsiTpMult_EU=0.7)),
    ("T010", "T000", "EU 対照: **全コード** 1.5倍", t(RsiTpMask_EU=M_ALL, RsiTpMult_EU=1.5)),
]

# 回帰 → USDJPY（唯一まともな候補）→ GBPUSD → EURUSD。
# 途中で止まっても価値の高い側から埋まる。各枠の「全コード」対照を必ず同じ枠の直後に置く。
ORDER = ["T000",
         "T001", "T002", "T003", "T004",
         "T005", "T006", "T007",
         "T008", "T009", "T010"]


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
        m3.log(f"FXQUAL13_START jobs={len(jobs)} RSI の機構別TP（棚卸しの最後）")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL13_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
