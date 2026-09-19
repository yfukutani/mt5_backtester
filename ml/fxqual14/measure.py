"""第26報 第14ラウンド `ml/fxqual14` — 枠ごとの依存度を、実行可能な構成で測り直す（LOSO）。

【なぜ「枠の質」から降りるのか】
Codex に「棚卸しが尽きた前提で出し直せ」と依頼した回答（2026-09-19・第14回）は
**「B は該当なし。未測定軸として再提案できるものはありません」**だった。
こちらの読み（第24報「いまの構成は IS について局所最適に座っている」）と一致する。
**13ラウンド・約100案・224run で枠の質による前進は +0.484pt。ここは閉じる。**

【代わりに何を測るのか — Codex の推奨3点のうち2点】
Codex の推奨:
  1. 許容 equity DD を先に決める（ユーザー判断事項。こちらでは決めない）
  2. Carry を含むブックのモデルリスクを測る
  3. **完全複利・cap込みの leave-one-sleeve-out を9本**測る
     （目的は枠別損益の帰属ではなく「その枠を失ったときブックがどうなるか」）

本ラウンドは 3 を主軸に、2 を Carry の扱いとして измерする。

【動機 — Carry が土台を壊していないか】
T000（倍率1・完全複利）の枠別純益:

| 枠 | OOS 純益 / 取引数 | IS 純益 / 取引数 |
|---|---:|---:|
| **Carry AUDJPY** | **341,439 / 7** | **2,754,029 / 7** |
| SCA GBPJPY | 426,099 / 621 | **−719,706** / 683 |
| PB GBPJPY | 387,525 / 15 | 1,027,109 / 13 |
| PB USDJPY | 107,369 / 13 | 731,148 / 49 |
| RSI GBPUSD | 103,360 / 62 | 206,436 / 65 |
| RSI USDJPY | 54,494 / 68 | 298,458 / 90 |
| SCA USDJPY | 6,026 / 103 | 215,491 / 214 |
| RSI EURUSD | 3,163 / 269 | 319,501 / 275 |
| Pair EU/GU | 1,984 / 30 | 13,057 / 56 |
| **合計** | **1,431,459** | **4,845,523** |

**IS 純益の 56.8% を Carry が 7取引で出している。**
そして Carry の損益は MT5 テスターの「現在のスワップ率を全履歴に一律適用」という
近似に支配され、**走らせた日によって動く**ことが実測済みである
（`docs/oanda_fx_carry_swap_drift_20260919.md`: 同一設定・同一取引数で FULL −4,070円）。
さらに `docs/oanda_fx_sleeve_removal_20260916.md` は
**「倍率を上げたときに口座を殺すのは Carry である」**（倍率5 で1取引が口座の88%）と
書いている。ただしあの数字は**上限50・cap100 の下**のもので、本番条件では再現しない。

> **したがって問いは2つ。**
> **(a) この9枠ブックは、どの枠にどれだけ依存しているのか（完全複利・cap90 で）**
> **(b) 倍率の上限を縛っているのは Carry なのか**

【⚠️ 引き算ではなく再実行でしか答えられない】
第22報で確定済み: **複利では枠別損益はブックの分解ではない。**
枠を外すと、その枠の損益以上にブックが減ることがある（他の8枠に回る資金が減るため）。
Codex も同じ指摘をした。**だから9本すべて実際に走らせる。**

【構成】
すべて **候補3件・完全複利（FxRiskMask=31 / FxRiskPct=0.5）・MarginCapPct=90**。
cap90 は `docs/oanda_fx_executability_20260919.md` が「実行可能」と確認した実用域。

- V000 = E002（倍率1・cap90）の回帰試験。**OOS 1,431,459 / IS 4,966,997 と一致すること**
- V001 = Carry を外す（倍率1）  ← 最優先
- V010 = E005（倍率2・cap90）の回帰試験。**OOS 3,491,431 / IS 30,121,151 と一致すること**
- V011 = 倍率2・Carry 抜き
- V012/V013 = 倍率3 の対照と Carry 抜き ← **(b) の答え**
- V002〜V009 = 残り8枠の LOSO（倍率1）

【事前の予想】
- **V001（倍率1・Carry 抜き）: IS は −1.3〜−2.0pt の大幅悪化**。
  IS 純益の 56.8% が消えるので当然。**だがそれは「Carry が強い」の証明ではなく、
  「IS の判定がスワップ近似に支配されている」の証明でもある。どちらとも読める。**
  OOS は −0.4〜−0.8pt 程度と予想（寄与 23.9%）。
- **V012/V013（倍率3）: ここが本ラウンドの唯一の上振れ候補。**
  倍率2・cap90 が OOS 3.849%。線形なら倍率3 で 5.0% 前後だが、
  cap の発動率が 倍率2 で既に 98.2%（OOS）まで来ているので**線形には伸びない**。
  **倍率3 の対照が破綻（元本割れ）する可能性が実在する**ので、必ず対で測る。
  Carry 抜きで破綻が消えるなら、Codex/第20報の「倍率の律速は Carry」が本番条件で追認される。
- **V002〜V009: ほとんどが両窓マイナス**。ただし Pair（OOS 1,984円/30取引）と
  RSI EURUSD（OOS 3,163円/269取引）は**外してもブックがほぼ動かない**はずで、
  動くならそれは「証拠金を空けた効果」である。そこが読みどころ。

【CAP_LOG は立てる】equity DD なしでは倍率3 の可否を論じられない。
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

# fxqual13 の BASE と1文字も変えない（比較可能性のため）。
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

# 倍率1・cap90 ＝ fxqualexec E002（OOS 1,431,459 / IS 4,966,997）。
COMP1 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
             RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0,
             MarginCapPct=90, **CAND)
COMP2 = dict(COMP1, GlobalLotMult=2)   # ＝ E005（OOS 3,491,431 / IS 30,121,151）
COMP3 = dict(COMP1, GlobalLotMult=3)   # 未測定


def drop(basecfg, en_key):
    """枠をひとつ外す。**Mult_*=0 では外れない**（Clamp が最小ロットに戻すため）。"""
    p = dict(basecfg)
    p[en_key] = False
    return p


PROPOSALS = [
    ("V000", "fxqualexec/E002",
     "対照＝回帰試験: 倍率1・cap90。OOS 1,431,459 / IS 4,966,997 と一致すること",
     COMP1),

    # --- (a)(b) の核心。Carry の座を、実行可能な構成で測り直す ---
    ("V001", "V000", "**Carry AUDJPY を外す**（倍率1）。IS 純益の 56.8% が 7取引で消える",
     drop(COMP1, "En_CARRY")),
    ("V010", "fxqualexec/E005",
     "対照＝回帰試験: 倍率2・cap90。OOS 3,491,431 / IS 30,121,151 と一致すること",
     COMP2),
    ("V011", "V010", "倍率2・**Carry 抜き**", drop(COMP2, "En_CARRY")),
    ("V012", "V010", "**倍率3・cap90（未測定）**。破綻するかどうかを先に見る", COMP3),
    ("V013", "V012", "倍率3・**Carry 抜き**。倍率の律速が Carry なら、ここで差が出る",
     drop(COMP3, "En_CARRY")),

    # --- 残り8枠の LOSO（倍率1） ---
    ("V002", "V000", "SCA GBPJPY を外す（OOS 最大の稼ぎ頭・IS は −719,706）",
     drop(COMP1, "En_SCA_GBPJPY")),
    ("V003", "V000", "PB GBPJPY を外す（両窓で2番目・取引13〜15）",
     drop(COMP1, "En_PB_GBPJPY")),
    ("V004", "V000", "PB USDJPY を外す", drop(COMP1, "En_PB_USDJPY")),
    ("V005", "V000", "RSI GBPUSD を外す", drop(COMP1, "En_RSI_GBPUSD")),
    ("V006", "V000", "RSI USDJPY を外す", drop(COMP1, "En_RSI_USDJPY")),
    ("V007", "V000", "RSI EURUSD を外す（OOS 3,163円/269取引＝実質ゼロ・証拠金だけ食う）",
     drop(COMP1, "En_RSI_EURUSD")),
    ("V008", "V000", "SCA USDJPY を外す（OOS 6,026円/103取引）",
     drop(COMP1, "En_SCA_USDJPY")),
    ("V009", "V000", "Pair EU/GU を外す（OOS 1,984円/30取引＝最小の枠）",
     drop(COMP1, "En_PAIR")),
]

# 回帰 → Carry（倍率1）→ 倍率2 の対照と Carry 抜き → 倍率3 の対（上振れ候補）
# → 残り8枠の LOSO（寄与の大きい順）。
# 途中で止まっても、判断に効く側から埋まる。
ORDER = ["V000", "V001",
         "V010", "V011",
         "V012", "V013",
         "V002", "V003", "V004", "V005", "V006", "V007", "V008", "V009"]

# 回帰試験の期待値（fxqualexec/results.csv より）。合わなければ止める。
EXPECT = {
    "V000": {"OOS": 1431459.0, "IS": 4966997.0},
    "V010": {"OOS": 3491431.0, "IS": 30121151.0},
}


def check(row):
    """回帰試験。**ただし Carry のスワップ・ドリフトがあるので閾値を置く。**

    `docs/oanda_fx_carry_swap_drift_20260919.md`: 同一設定・同一取引数でも
    テスターのスワップ率が日をまたいで変わり、Carry の損益だけが動く（FULL −4,070円）。
    したがって「1円も違わないこと」を止める条件にすると、無害なドリフトで
    ラウンドごと落ちる。**0.5% を超えたときだけ止める。** それ未満は記録して進む。
    """
    pid, win = row["proposal_id"], row["window"]
    if pid not in EXPECT:
        return
    exp = EXPECT[pid][win]
    if row.get("status") != "OK":
        raise RuntimeError(f"{pid}({win}) が FAILED です。中止します。")
    got = float(row["net"])
    rel = abs(got - exp) / abs(exp)
    tag = "EXACT" if abs(got - exp) < 1.0 else f"DRIFT rel={rel:.5%}"
    m3.log(f"REGRESSION {pid} {win} expected={exp} got={got} -> {tag}")
    if rel > 0.005:
        raise RuntimeError(
            f"{pid}({win}) が fxqualexec を再現しませんでした"
            f"（期待 {exp} / 実測 {got} / 乖離 {rel:.3%}）。"
            "スワップ・ドリフトでは説明できない幅です。比較できない数字は積みません。")


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
        m3.log(f"FXQUAL14_START jobs={len(jobs)} LOSO（枠ごとの依存度）＋倍率3")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            check(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL14_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
