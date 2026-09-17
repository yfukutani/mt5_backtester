"""第14報：**枠そのものの質**を測る最初のラウンド（2026-09-18）。

【主題が変わった】
2026-09-08〜09-17 の全ラウンドは「ロットの大小」だった（倍率・複利・risk%・cap・
枠の重み・入金・業者上限・証拠金予算）。2026-09-17 のユーザー指示で主題が変わった。

    次は現状の戦略の精度向上を目指してください。
    一個一個の戦略に改良点がないか Codex と Claude で両方で案を出し合い、
    有効な手立てを探してください。

本ラウンドは **サイジングを一切動かさない。** 全案が同じロット規則（本番現行相当・
`RefCap=78,000` 固定・倍率1・重み全1.0）を使い、**枠の入口と出口の規則だけ**を変える。

【土俵に本番現行サイジングを選んだ理由】
固定サイジング（RefCap>0）なら、ロットが口座残高にも証拠金にも依存しない。
したがって **枠の改良の効き目がロットの二次効果に混ざらない。** 倍率・複利・cap の
組合せは既に測り切っており、良い改良が見つかればそちら側は後から掛け直せる。

【窓】
    OOS  2016.11.09 - 2021.06.20 （55か月）
    IS   2021.06.20 - 2026.06.20 （60か月）  ← **本プロジェクトで IS窓を明示的に測る初回**

これまでの OANDA FX ラウンドは OOS と FULL(115か月) しか測っておらず、
「IS窓の測定が無い」ことが積み残しになっていた（CLAUDE.md の報告規律は IS/OOS 併記を要求）。
ここで IS を独立した窓として測る。

【何を測るか — 段階2（ml/fxqual1/*.py）が指した3か所】

1. **RSI 3枠のドテン** （`RsiNoFlipMode` / `RsiNoFlipMask`）
   SLでもTPでもない決済は 97〜100% が反対シグナルのドテン。
   出た側の ΣR は OOS -8.1 / IS -17.9 で**両窓とも負け**。
   ただし**入った側**は OOS +15.9R / IS -8.8R。**OOS では入った側が稼いでいる。**
   → ドテンをやめるのは IS に効き OOS に逆効果、という予想。**当たるか測る。**

2. **SCA 2枠の時間** （`ScaHourMask` / `ScaForceCloseOv` / `ScaTradeEndOv`）
   SCA の取引の 60〜77% は 22時の強制決済で終わり、**利益はそこに集中**する。
   TP到達は 3〜7% しかない。退出時刻はこの枠の主要パラメータなのに未掃引。

3. **PB 2枠の入口の広さ** （`PbAdxThr_*` / `PbSlopeATR_*`）
   PB GBPJPY は 115か月で 28取引しかないが平均 R 1.34(OOS)/1.69(IS)。
   **律速は質ではなく頻度**。絞りを緩めて頻度を上げられるか。

4. **SCA の買い限定** （既存入力 `ScaFilMask` / `ScaFilBuyOnly`・実装不要）
   SCA GBPJPY の直近2.5年の負け -57,746円 は**ほぼ全部が売り側**（-59,367円）。
   ただし方向の非対称は枠によって向きが逆で（RSI EURUSD は直近だけ売りが良い）、
   **相場観の賭けになる疑いが濃い。** 見込みは低いが入力が既にあるので同じ土俵で測る。

【予想 — 外すと恥ずかしいので先に書く】
- ドテン停止は **IS で改善・OOS で悪化**する。両窓改善なら段階2の読みが甘かったということ。
- SCA の強制決済を早めると **取引の質は上がるが総量が減って純益は落ちる**。
- PB の絞りを緩めると **取引数は増えるが平均Rが落ち、差し引きはほぼゼロ**。
  （過去2周のパラメータ再最適化はこの近傍を既に見ている）
- 買い限定は **OOS と 2022-23 を捨てる**ので通期では負ける。

【留保】
- 本ラウンドは **XM端末・XM銘柄**で走る。OANDA の答えそのものではない
  （フィード差・スプレッド差・スワップ差は別問題）。枠の改良の**向き**を見る。
- `ml/fxcomp1` の C001（同じ構成）は **レバレッジのバグで 1:100 で走っていた**
  （2026-09-15 に発覚）。本ラウンドは 1:25。**C001 の数字とは直接並べられない。**
  対照 Q000 が本ラウンド内の唯一の基準である。
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
m3.CAP_LOG = False          # 本ラウンドは cap を使わないので計装は不要
# ロックは fxmargin3 と共有（端末は1台しか使えない）。

WINDOWS = {
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
    "IS":  ("2021.06.20", "2026.06.20", 60.0),
}
m3.WINDOWS = WINDOWS
WINS = ("OOS", "IS")

# 本番現行サイジング（C001 と同じ）。ここから先、**サイジングは全案で同一**。
SIZING = {
    "GlobalLotMult": 1,
    "MarginCapPct": 0,          # cap は使わない（枠の質だけを見る）
    "BrokerMaxLot": 0,
    "FxRiskMask": 0, "FxRiskPct": 0.5, "FxRiskRefCap": 0,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    SIZING[f"Mult_{_k}"] = 1.0
# 枠の質の軸は全案で明示する（EA既定値が変わっても比較が壊れないように）。
QUALITY_OFF = {
    "RsiNoFlipMode": 0, "RsiNoFlipMask": 0,
    "ScaHourMask": 0, "ScaForceCloseOv": 0, "ScaTradeEndOv": 0,
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
    "ScaFilMask": 0, "ScaFilRangeMin": 0.0,
    "ScaFilHourFrom": -1, "ScaFilHourTo": -1, "ScaFilBuyOnly": False,
    "CarryExitPeriod": 0, "CarryExitOnly": False, "CarryHoldBars": 0,
}


def q(**over):
    p = dict(SIZING)
    p.update(QUALITY_OFF)
    for k, v in over.items():
        if k not in p:
            raise KeyError(f"本ラウンドで触らない入力を触ろうとしている: {k}")
        p[k] = v
    return p


PROPOSALS = [
    # --- 対照 ---------------------------------------------------------
    ("Q000", "本番現行", "対照: 本番現行サイジング・枠の質の軸はすべて無効。"
                        "本ラウンドの唯一の基準", q()),

    # --- 1. RSI のドテン（段階2で最も強い手がかり）----------------------
    ("Q001", "Q000", "RSI 3枠: 反対シグナルを無視する（保有継続・新規なし）",
     q(RsiNoFlipMode=1)),
    ("Q002", "Q000", "RSI 3枠: 決済はするが反対の新規は出さない",
     q(RsiNoFlipMode=2)),
    ("Q003", "Q000", "RSI EURUSD だけ反対シグナルを無視（ドテンが最も多い枠）",
     q(RsiNoFlipMode=1, RsiNoFlipMask=2)),
    ("Q004", "Q000", "RSI USDJPY + GBPUSD だけ反対シグナルを無視",
     q(RsiNoFlipMode=1, RsiNoFlipMask=5)),

    # --- 2. SCA の時間（利益の大半が出ている出口を初めて動かす）---------
    ("Q005", "Q000", "SCA 2枠: 強制決済 22時 -> 20時", q(ScaHourMask=3, ScaForceCloseOv=20)),
    ("Q006", "Q000", "SCA 2枠: 強制決済 22時 -> 18時", q(ScaHourMask=3, ScaForceCloseOv=18)),
    ("Q007", "Q000", "SCA 2枠: 強制決済 22時 -> 23時（遅らせる側も見る）",
     q(ScaHourMask=3, ScaForceCloseOv=23)),
    ("Q008", "Q000", "SCA GBPJPY だけ強制決済 20時（直近の負けが集中している枠）",
     q(ScaHourMask=2, ScaForceCloseOv=20)),
    ("Q009", "Q000", "SCA 2枠: 発注締切 12時 -> 10時（レンジ確定直後だけ取る）",
     q(ScaHourMask=3, ScaTradeEndOv=10)),
    ("Q010", "Q000", "SCA 2枠: 発注締切 12時 -> 15時（遅い抜けも拾う）",
     q(ScaHourMask=3, ScaTradeEndOv=15)),

    # --- 3. PB の入口の広さ（質は最良・頻度が律速）----------------------
    ("Q011", "Q000", "PB GBPJPY: ADX閾値 30 -> 25", q(PbAdxThr_GJ=25.0)),
    ("Q012", "Q000", "PB GBPJPY: ADX閾値 30 -> 22.5", q(PbAdxThr_GJ=22.5)),
    ("Q013", "Q000", "PB GBPJPY: slope下限 1.5 -> 1.2ATR", q(PbSlopeATR_GJ=1.2)),
    ("Q014", "Q000", "PB GBPJPY: ADX 25 ＋ slope 1.2ATR（両方緩める）",
     q(PbAdxThr_GJ=25.0, PbSlopeATR_GJ=1.2)),
    ("Q015", "Q000", "PB USDJPY: ADX閾値 27.5 -> 22.5", q(PbAdxThr_UJ=22.5)),
    ("Q016", "Q000", "PB USDJPY: slope下限 1.2 -> 0.9ATR", q(PbSlopeATR_UJ=0.9)),

    # --- 4. SCA の買い限定（実装済み入力・見込みは低いと先に書く）-------
    ("Q017", "Q000", "SCA GBPJPY だけ買い限定（直近の負けは売り側に集中）",
     q(ScaFilMask=2, ScaFilBuyOnly=True)),
    ("Q018", "Q000", "SCA 2枠とも買い限定", q(ScaFilMask=3, ScaFilBuyOnly=True)),

    # --- 5. Carry: 「退出だけ変える」を本当に退出だけにする（Codex #36）--------
    # Codex の査読で、`CarryExitPeriod>0` が ProcCarry() で
    #   entry_th = MathMax(MA200, ExitMA) / exit_th = ExitMA
    # と**入口も退出も同時に**置き換えていることが分かった。ヒステリシス帯
    # （entry=MA200+0.75ATR）が消えるので、**「退出だけ変えた実験」になっていない。**
    # `ml/fxcarry1` の C10/C11 はこの交絡を含む。
    # ここで 3対照（現行 / 既存切替＝交絡あり / 退出だけ）を同じ土俵で並べる。
    ("Q019", "Q000", "Carry: 既存の退出SMA切替 40（入口も変わる＝交絡あり・fxcarry1 C10 相当）",
     q(CarryExitPeriod=40)),
    ("Q020", "Q019", "Carry: 入口はヒステリシス帯のまま・退出だけ SMA40（Codex #36）",
     q(CarryExitPeriod=40, CarryExitOnly=True)),
    ("Q021", "Q019", "Carry: 同じく退出だけ SMA20", q(CarryExitPeriod=20, CarryExitOnly=True)),
]

# 対照 → 手がかりの強い順。途中で止まっても判断に効く数字から埋まる。
ORDER = ["Q000",
         "Q001", "Q003", "Q002", "Q004",
         "Q005", "Q008", "Q006", "Q007", "Q009", "Q010",
         "Q019", "Q020", "Q021",
         "Q011", "Q013", "Q014", "Q012", "Q015", "Q016",
         "Q017", "Q018"]


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
        print("全案・両窓が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXQUAL1_START jobs={len(jobs)} 枠の質の4軸 leverage=1:25 "
               "sizing=本番現行(RefCap78000/倍率1/重み1.0)")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "Q000":
                if row.get("status") != "OK":
                    m3.log("FXQUAL1_ABORT 対照 Q000 が失敗した。基準が取れないので中止する")
                    return
                m3.log(f"Q000_BASELINE {window} net={row['net']} "
                       f"trades={row['trades']} dd%={row['dd_pct']}")
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
