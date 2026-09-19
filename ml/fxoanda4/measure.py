"""第17ラウンド — **T036系は IS 窓でも生き残るのか**（OANDA BT1 端末）。

【なぜ測るのか — ここが本ラウンドの全部】
`docs/oanda_fx_terminal_cap_sweep_20260919.md` で、**OANDA 端末で実際に走り切る構成**が
1つ見つかっている:

    S050 = E04（Carry と PB USDJPY を外した7枠）＋ FxRiskMask=7（RSI3枠だけ risk%1.0）
           ＋ GlobalLotMult=3 ＋ MarginCapPct=50
    通期OOS 55か月 = **幾何 5.537%/月**（最終残高 9,688,767円・残高DD 44.91%）

目標は月利6%。**これは全複利ブック（XM・倍率2・cap90 の OOS 3.849%）より 1.7pt 高い。**
にもかかわらず**採用候補にできていない**。理由はただ一つ——

    🔴 **IS 窓（2021-06〜2026-06）を一度も測っていない。**

しかも T036系は **RSI 3枠に 1.0%×倍率3 ＝ 実効3%/取引**を集中させる構成で、
その RSI 3枠は全複利ブックの枠別損益では **IS で最も弱い**枠である。
ユーザー方針は「トレードオフでは IS（現状市場）を優先」なので、
**IS を測るまでこの 5.537% は採否の材料にならない。** 本ラウンドがその穴を埋める。

【⚠️ 先に踏んでおく地雷 — EA バイナリが古い】
OANDA 端末にデプロイされていた `MIX_EA_SIMVERIFY.mq5` は **2026-09-18 00:13 の版**
（149,077 バイト）で、リポジトリの現行（2026-09-19 20:08・196,104 バイト）**より古い**。
第12〜13ラウンドで足した `RsiTpMask_*` / `ScaRR_*` / `ScaOvsATR_*` / `ScaBE*` を持っていない。

    → chain.ps1 が **OANDA 側の MetaEditor64.exe で再コンパイルしてから**走らせる。

追加 input はすべて既定が no-op（`RsiTpMask_*=0`・`ScaRR_*=0.0` など・実装で確認済み）だが、
**diff には `LotRisk()` まわりの書き換えが含まれている。**「既定なら同じはず」で済ませない。
そこで **`O000` を必ず最初に回し、fxoanda3 の S050 OOS 純益 9,188,767円 を再現するか**を見る。

    再現しない場合、原因の候補は2つあり、この1本では切り分けられない:
      (a) EA の版が変わって挙動が変わった
      (b) fxoanda3 の数字がそもそも再現しない（端末・フィード側の非決定性）
    **どちらであっても「fxoanda3 の数字と本ラウンドの数字を並べてはいけない」**ことは確定する。
    その場合は本ラウンド内（同一EA）で閉じた比較だけを行い、doc にそう書く。

【測る順 — 途中で止まっても価値の高い側から埋まる】
1. `O000` 回帰（S050 OOS）        … これが落ちたら以降の解釈が変わる
2. `O001` **S050 IS**             … 本ラウンドの主役。ここだけでも埋まれば報告になる
3. `O020` **枠の質の移植（IS→OOS）**… 主題（枠ごとの改良）。RSI に3%が乗る土俵で初めて測る
4. `O002` S070 IS / `O003` S070 OOS … cap70 は窓中央値6.57%。通期は未測定のまま
5. `O021` / `O022`                … SCA 入口下限の移植と合成
6. `O004` S033 IS                 … 保守側の IS。S050 が IS で壊れたときの退避先
7. `O010` / `O011`                … 全複利ブックを **同じ OANDA 端末**で。2系統の初の同一土俵

【事前予想 — 外すと恥ずかしいので先に書く】
- `O000`: 再現する（±0.5%以内）。**見込み: 中**。`LotRisk` の書き換えが不安材料。
- `O001` **S050 IS**: Claude は **幾何 1.5〜3.0%/月**、Codex は **3.8%（レンジ 2.5〜4.8%）**と予想。
  **両者とも「OOS の 5.537% は IS では再現しない・6% には届かない」で一致。**
  根拠: 全複利ブックは OOS 2.488% に対し IS 4.028%（IS のほうが良い）だが、
  それは9枠の平均であって、**RSI 3枠だけを見ると IS の枠別損益は最弱**
  （XM 15枠の枠別表で IS +7,440〜+13,286円）。T036 はそこに3%を集中させている。
  Claude はさらに**口座破綻（ロスカットで打ち切り）も3割くらいの確率**と見る（Codex は見ない）。

  🔴 **Codex が枠別に割った結果、T036 の OOS 純益はほぼ RSI GBPUSD 1枠で出ている:**

      RSI GBPUSD +5,845,180 / RSI USDJPY +1,353,381 / RSI EURUSD +906,540
      （計 +8,105,101 ＝ 全体 +9,188,767 の 88%。うち **GU 単独で 64%**）
      Pair −1,997 / SCA USDJPY −82,923

  **つまり T036 の 5.537% は「1枠の OOS 成績に 3%/取引を賭けた数字」である。**
  IS でこれが平凡化するだけで全体が落ちる。**これが本ラウンドで最も確かめたいこと。**

- `O020`/`O023`（RSI の TP 群の移植）: **効き幅 ±0.3pt。見込み: 中。**
  全複利ブックでは `T001`(UJ) 単独が OOS +0.011pt、`T008`(EU) との合成で +0.107pt だった。
  T036 では RSI の重みが 6倍（0.5%×2 → 1.0%×3）なので**同じ変更が大きく出るはず**だが、
  複利の増幅は 12〜121倍とばらつくので**符号までは読めない**（第22報）。
  ⚠️ **Codex の指摘で設計を1か所変えた**: 当初は UJ＋EU（全複利で最良だった組）を移植する
  つもりだったが、**T036 で金を出しているのは GU（64%）**なので、
  **`RsiTpMask_GU`（全複利の `T005`・IS +0.075pt / OOS −0.031pt）を単独で測る `O023` を主役に据えた。**
  Codex の EU 評価は「見込み低・OOS の equity DD がむしろ悪化した」なので EU は外した。
- `O003` S070 通期OOS: **走り切ると予想する**（W1〜W3 が完走しているので）。
  ただし W3 の残高DD 57.8% があるので、**通期の equity DD は 70% を超える**と予想する。
- `O011`（全複利ブック 倍率2・**cap90** を OANDA で）: **建て直後の維持率 111%。
  OANDA は 100% で切るので、通期のどこかでロスカットされて打ち切られる**と予想する。
  **見込み: 低**（成績としては期待しない）。**これは「実行不可であること」を測る run である。**
- `O010c`/`O011c`（全複利ブックを **cap50** で）: ⚠️ **Codex の指摘で足した。**
  `O011`(cap90) と `S050`(cap50) を並べると **系統の差と cap の差が混ざる**。
  **cap を 50 に揃えた対が無いと「T036系 vs 全複利ブック」を言えない。**
  予想（Codex）: 倍率1 で OOS 1.6〜2.0% / IS 2.8〜3.5%、倍率2 で OOS 2.4〜3.1% / IS 4.0〜5.2%。

【土俵】
OANDA BT1（`C:\\Program Files\\OANDA MetaTrader 5_BT1`）・1:25・every_tick・入金50万円・
`BrokerMaxLot=0`（端末の 1注文10ロットがそのまま効く）・**維持率100%でロスカット**。
窓: OOS 2016.11.09〜2021.06.20（55か月）／IS 2021.06.20〜2026.06.20（60か月）。
`CAP_LOG=True`（並行セッションの申し送り: 残高DD と equity DD は OOS で 11〜16pt 違う）。
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

OANDA_HASH = "6142D304BFF2E6AB353977162D6F452C"
m3.EXE = r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"
m3.EA_EX5 = (Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal") / OANDA_HASH
             / "MQL5" / "Experts" / "MIX_EA_SIMVERIFY.ex5")
m3.ROOT = ROOT          # ロックは OANDA 側で独立（XM のパイプラインとは別）

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

# --- 第12〜13ラウンドで足した input を**明示的に no-op へ固定する** -----------
# BASE（fxrisk3 由来）はこれらを知らない。EA の既定値に任せると、
# あとで EA 既定が変わったときに黙って結果が動く。fxqual15 と同じ規約で固定する。
NOOP = {
    "BrokerMaxLot": 0,            # 0 = 端末の上限（OANDA は 10ロット）
    "TagDealTriggers": True,      # deal ログに退出理由を書く（解析用・売買には影響しない）
    "PbDiagCounters": True,
    "LotFloorMask": 0, "LotFloorRatio": 0.0,
    "PairSkipAtStop": False, "PairEqualNotional": False,
    "PairMaxHoldBars": 0, "PairEntryZOv": 0.0, "PairRequireZTurning": False,
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
    "PbArmMaxBars_UJ": 0, "PbArmMaxBars_GJ": 0,
    "RsiMechMask_UJ": 0, "RsiMechMask_EU": 0, "RsiMechMask_GU": 0,
    "RsiTpMask_UJ": 0, "RsiTpMult_UJ": 1.0,
    "RsiTpMask_EU": 0, "RsiTpMult_EU": 1.0,
    "RsiTpMask_GU": 0, "RsiTpMult_GU": 1.0,
    "ScaFilMask": 0, "ScaFilRangeMin": 0.0,
    "ScaFilHourFrom": -1, "ScaFilHourTo": -1, "ScaFilBuyOnly": False,
    "ScaBETriggerR": 0.0, "ScaBELockR": 0.0, "ScaBEMask": 0,
    "ScaRR_UJ": 0.0, "ScaRR_GJ": 0.0,
    "ScaOvsATR_UJ": 0.0, "ScaOvsATR_GJ": 0.0,
    "ScaRevOnlyMask": 0, "ScaRevDropMask": 0,
}

cfg = m3.cfg

# T036系の枠別重み。fxoanda3/measure.py から1文字も変えない。
W036 = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
            PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)
CARRY, PBUJ = "CARRY", "PB_USDJPY"


def t036(mult, cap, **extra):
    """T036系 ＋ E04（Carry と PB USDJPY を外す）。extra で枠の質の軸を足す。"""
    p = dict(NOOP)
    p.update(cfg(7, 1.0, mult, cap, **W036))
    for name in (CARRY, PBUJ):
        key = f"En_{name}"
        if key not in m3.BASE:
            raise KeyError(f"未知の枠スイッチ: {key}")
        p[key] = False
    for k, v in extra.items():
        if k not in p:
            raise KeyError(f"{k} は NOOP/cfg のどちらにも無い。綴りを確認すること")
        p[k] = v
    return p


def full_comp(mult, cap):
    """全複利ブック（9枠すべて risk%0.5×倍率・FxRiskMask=31）。枠は外さない。

    ⚠️ 9枠であることを**明示的に書く**。BASE の既定に任せると、BASE が将来変わったときに
    「T036系 vs 全複利ブック」の比較が黙って別物になる。
    """
    p = dict(NOOP)
    p.update(cfg(31, 0.5, mult, cap))
    p["En_CARRY"] = True          # T036系(E04)では False。ここが2系統の枠構成の差
    p["En_PB_USDJPY"] = True      # 同上
    return p


# --- 枠の質の移植（主題）----------------------------------------------------
# 全複利ブック（XM・9枠・risk%一律）で見つかった採用候補を、
# **RSI に実効3%/取引が乗る T036 の土俵**に載せ替えて初めて測る。
# ⚠️ 「全複利ブックでの効き幅」を予測値として使わないこと（第22報: 複利の増幅は 12〜121倍）。
TP_UJ = dict(RsiTpMask_UJ=120, RsiTpMult_UJ=1.5)       # fxqual13 T001（全複利での採用候補）
TP_GU = dict(RsiTpMask_GU=2, RsiTpMult_GU=1.5)         # fxqual13 T005（★T036 の稼ぎ頭は GU）
SCA_FLOOR = dict(ScaFilMask=1, ScaFilRangeMin=0.0048)  # 第20報 SCA USDJPY レンジ幅下限

PROPOSALS = [
    # --- 穴埋め（fxoanda3 §3 の未実施9run）---------------------------------
    ("O000", "fxoanda3/S050", "回帰試験: S050 を新EAで再走。OOS 純益 9,188,767 を再現するか",
     t036(3, 50)),
    ("O001", "O000", "★本命: S050 の **IS窓**（未測定）。T036系は現状市場で生き残るか",
     t036(3, 50)),
    ("O002", "fxoanda3/S070", "S070（cap70）の **IS窓**", t036(3, 70)),
    ("O003", "fxoanda3/S070", "S070 の通期OOS。fxoanda3 では 14.6秒で起動失敗して未測定",
     t036(3, 70)),
    ("O004", "fxoanda3/S033", "S033（cap33・保守側）の **IS窓**。S050 が IS で壊れたときの退避先",
     t036(3, 33)),

    # --- 枠の質の移植（本タスクの主題）-------------------------------------
    ("O023", "O000", "★RSI GBPUSD の TP（T005）を移植。**T036 の純益の64%を出している枠**",
     t036(3, 50, **TP_GU)),
    ("O020", "O000", "RSI USDJPY の TP（T001）を移植。全複利での採用候補を3%の土俵で",
     t036(3, 50, **TP_UJ)),
    ("O022", "O023", "合成: GU ＋ UJ（⚠️加算性は測る。足し算で見積もらない）",
     t036(3, 50, **TP_GU, **TP_UJ)),
    ("O021", "O000", "SCA USDJPY のレンジ幅下限（第20報）を T036 に移植",
     t036(3, 50, **SCA_FLOOR)),

    # --- 2系統を同じ端末で比べる（初）--------------------------------------
    # ⚠️ cap を揃えた対（O010c/O011c）が無いと「系統の差」と「cap の差」が混ざる（Codex #Q4）。
    ("O011", "fxqual14/V010", "全複利ブック 倍率2・**cap90** を OANDA端末で。実行可能性の検査（落ちると予想）",
     full_comp(2, 90)),
    ("O011c", "O011", "全複利ブック 倍率2・**cap50**。S050 と cap を揃えた本命の比較",
     full_comp(2, 50)),
    ("O010c", "fxqual14/V000", "全複利ブック 倍率1・**cap50**。XM では OOS 2.488%",
     full_comp(1, 50)),
]

# (proposal_id, window) を明示列挙する。**途中で止まっても価値の高い側から埋まる順。**
# IS を先に取るのは、ユーザー方針が「トレードオフでは IS を優先」だから。
JOBS = [
    ("O000", "OOS"),   # 1. 回帰。ここが落ちたら以降の解釈が変わる
    ("O001", "IS"),    # 2. ★本ラウンドの主役
    ("O023", "IS"),    # 3. ★主題（枠の質）。稼ぎ頭 GU の出口
    ("O020", "IS"),    # 4.    同・UJ
    ("O022", "IS"),    # 5.    合成
    ("O023", "OOS"),   # 6.
    ("O020", "OOS"),   # 7.
    ("O022", "OOS"),   # 8.
    ("O002", "IS"),    # 9.  cap70 の IS
    ("O003", "OOS"),   # 10. cap70 の通期OOS（fxoanda3 で起動失敗した穴）
    ("O011c", "IS"), ("O011c", "OOS"),   # 11-12. cap を揃えた2系統比較（倍率2）
    ("O010c", "IS"), ("O010c", "OOS"),   # 13-14. 同（倍率1）
    ("O011", "OOS"),   # 15. cap90 は OANDA で建てられるのか（落ちると予想）
    ("O004", "IS"),    # 16. cap33 の IS（S050 が壊れたときの退避先）
    ("O021", "IS"), ("O021", "OOS"),     # 17-18. SCA 入口下限の移植
]

# 回帰の期待値（fxoanda3/results.csv 実測）。Carry を外しているのでスワップ・ドリフトは無い。
EXPECT = {("O000", "OOS"): 9188767.0}
TOL = 0.005


def check(row):
    key = (row["proposal_id"], row["window"])
    if key not in EXPECT:
        return
    if row.get("status") != "OK":
        m3.log(f"REGRESSION {key} が FAILED。以降は fxoanda3 と並べられない")
        raise RuntimeError(f"{key} が FAILED です。中止します。")
    exp, got = EXPECT[key], float(row["net"])
    rel = abs(got - exp) / abs(exp)
    verdict = "EXACT" if abs(got - exp) < 1.0 else f"rel={rel:.5%}"
    m3.log(f"REGRESSION {key} expected={exp} got={got} -> {verdict}")
    if rel > TOL:
        # ⚠️ 止めない。原因が (a)EA版 か (b)非決定性 か、この1本では切り分けられないため、
        #    残りを走らせて**本ラウンド内で閉じた比較**を作るほうが価値が高い。
        m3.log("REGRESSION_DRIFT 🔴 fxoanda3 の数字と本ラウンドを並べてはいけない。"
               "以降は fxoanda4 内だけで比較すること。走行は続行する。")


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    by_id = {p[0]: p for p in PROPOSALS}
    missing = [pid for pid, _ in JOBS if pid not in by_id]
    if missing:
        raise KeyError(f"JOBS に未定義の案がある: {missing}")
    done = m3.load_done()
    jobs = [(by_id[pid], w) for pid, w in JOBS if (pid, w) not in done]
    if not jobs:
        print("全 job が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXOANDA4_START jobs={len(jobs)} OANDA端末(BT1) "
               f"T036系の IS 窓と、枠の質の移植")
        for (pid, base, desc, params), window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            check(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXOANDA4_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
