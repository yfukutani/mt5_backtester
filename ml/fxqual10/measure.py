"""第10ラウンド `ml/fxqual10` — **SCA USDJPY のレンジ幅下限を、複利サイジングの上で掃引する**。

【なぜこのラウンドか】
確認ラウンド（`ml/fxqualcfm`・第17報）で、**枠の質の改善は複利にすると効き幅が
11.9〜14.7倍になる**ことが実測された。同じ EA 変更が、固定ロットで +0.028pt、
全複利で +0.333pt（OOS 幾何月利）である。

**この事実は、これまでの「測る価値がない」という価値判断を全部つくり直す。**
Codex の棚卸し（`docs/codex_oafx_inventory_20260919.md`）が各軸に付けた
「±0.02pt 以下」「±0.03pt 以下」という見込みは、**すべて固定ロットでの数字**だった。
複利では同じものが ±0.24pt〜±0.36pt を意味しうる。目標 6% に対し現在地 OOS 3.34%
（`F005`・倍率2）で、不足は約 2.7pt。**+0.2pt 級の軸は「価値がない」水準ではない。**

【この軸を選んだ根拠 — `ml/fxqualcfm` の deal ログを両窓で割り直した】
`F002`（全複利・倍率1）の OOS 枠別内訳:

    pb_gj +299,856 / sca_gj +307,007 / carry +283,163 / rsi_gu +94,106 /
    rsi_uj +24,142 / pb_uj +23,029 / rsi_eu +15,863 / pair +1,996 /
    **sca_uj −59,795  ← 唯一のマイナス枠**

固定ロットの `F000` では sca_uj は **−2,224** にすぎない。**risk%化で 27倍に増幅されている。**
機構は既知である（`oanda_fx_risk_sizing_20260915.md` §4d）——
**SCA の SL距離＝アジア時間のレンジ幅**なので、risk%化は「狭いレンジほど大きく賭ける」
ことに等しく、SCA USDJPY は**狭いレンジのブレイクが赤字**の枠である。

SL距離（entry-SL）の5分位で割ると、**両窓とも最小分位が単独で最悪**である:

| 窓 | Q1（最も狭い） | 1取引平均 | Q2 | Q3 | Q4 | Q5 |
|---|---:|---:|---:|---:|---:|---:|
| OOS(266件) | **−45,986** | **−868** | +5,648 | −50,303 | +21,562 | +9,284 |
| IS(327件)  | **−70,323** | **−1,082** | +84,133 | +71,620 | +56,126 | +28,547 |

比（`dist/entry`・EA 1927行の判定式そのもの）の空間で下限を入れた**素朴な合計**は、
**0.0026〜0.0042 の全点で両窓プラス**である（OOS +17k〜+98k / IS +16k〜+78k）。
0.0045 以上で IS が負に転じ、0.0060 では IS −119,159 になる。

> [!warning] **⚠️ この「素朴な合計」は予測値として使ってはいけない。並行セッションの指摘で2点、実測で1点、破れている。**
>
> **(1) `ScaFilRangeMin` は日内で解除されるゲートである**（並行セッションの指摘）。
> EA 1925-1928行の `dist` は SL距離（買いなら `ask − scaRangeLow`）、`entry` はその時点の `ask` で、
> **`scaRangeLow` は日内固定でも `ask` は動く。** 09:15 の初回ブレイクが閾値を下回って
> 止められても、10:00 の再ブレイクでは `dist/entry` が大きくなってゲートを通る。
> `scaTradedL` は発注成功時にしか立たないので、その日の枠は終わっていない。
> **第5ラウンドの時間帯ゲートと同じ機構である。**
> 実測されたずれ率（`ml/fxqual9/shift.py`・F006）は **OOS 7% / IS 18%**。
> 時間帯ゲートの 89% よりずっと小さいが、ゼロではない。
>
> **(2) 複利では止めた取引が後続のロットを変える。**
> 負けを1件止める → その時点の equity が上がる → **以降の全取引のロットが増える。**
> 素朴な合計は元のロットのまま足しているので、この経路を含まない。
> `F002 → F003` では、**触っていない枠の変化が全体の 66%** を占めた
> （pb_gj +60,490・carry +44,049・sca_gj +89,456 ＝ +193,995 / 全体 +291,723）。
>
> **(3) 実測で、素朴な合計は片側で符号を外している。**
> 同じ手続きを**固定ロットの `F000` ログ**に当てて `F006`（0.00595）と突き合わせた:
>
> | | 素朴な合計 | **実測（F006）** | 判定 |
> |---|---|---:|---|
> | OOS | +4,975（0.0056）〜 +3,678（0.0060） | **+3,991** | **当たり**（帯の内側） |
> | IS  | −1,060（0.0056）〜 −6,425（0.0060） | **+3,393** | **符号ごと外れ** |
>
> IS の外れ幅（約 +7,400〜+9,800）は、**ずれ率 18% と符号が整合する**——
> 止められた負けが後ろへずれて生き返るのではなく、**止められた勝ちが戻ってきている。**
>
> なお手続き自体は正しく、**`oanda_fx_last_axes_20260915.md` の B1 上位50% の数字
> （残 +2,751 / Δ +4,975）を1円まで再現する。** 壊れているのは手続きではなく、
> **「止めた取引は消える」という前提**である。

**したがって、以下の帯は「予測」ではなく「掃く範囲」である。** 採否は実測だけで決める。
掃引点には **0.0060（F006 の 0.00595 に隣接）も入れる**——素朴な合計はここで IS が
大きく負（−119,159）と言うが、**その素朴な合計が IS で外れることが実証されている**ので、
「素朴な合計が負」を理由に点を落とすことはしない。

【この軸は「新案」ではなく、宣言されたまま測られていない宿題である】
`oanda_fx_risk_sizing_20260915.md`（2026-09-15）はこう書いている:

> **SCA に対する正しい手は risk%化ではなく、次のどちらかである。**
> - そのまま固定ロットで `Mult_SCA_*` と `GlobalLotMult` で増量する
> - **レンジ幅フィルタ（Claude案 B1）で狭いレンジを捨ててから risk%化する**
>   ——狭いレンジを捨てれば、risk%化の逆選択が消える。**これが fxrisk4 の主題になる。**

**`ml/fxrisk4` は存在しない。** 宣言から4日、この軸は測られていない。

【過学習について正直に書く】
**しきい値は OOS と IS の deal ログを見て決めた。** したがって
**このラウンドの OOS は、この軸については out-of-sample ではない。**
それを踏まえたうえで、この軸が単なる曲線あてはめでないと考える理由は2つある:

1. **機構が先にある。** 「狭いレンジ → risk%で大ロット → ブレイクは騙し」は
   2026-09-15 に**この解析より前に**文書化されている。
2. **09-15 の独立な分割と一致する。** 同 doc は FULL窓・固定ロット・594取引で
   SL距離の四分位を割り、「**利益はレンジが広い半分だけが作っている。狭い半分は赤字**」
   と結論している（最小25%の中央値 0.321・25-50% の中央値 0.455）。
   **比に直すと 0.0029〜0.0041** で、本ラウンドの帯とほぼ同じである。
   **私が見る前に、別の窓・別のサイジングで同じ境界が出ていた。**

それでも **FULL窓と、しきい値を動かしたときの台地性**で確認するまでは採用しない。

【採否の基準（測る前に書く）】
1. **両窓プラスが 3点以上連続していること。** 1点だけ突出しても採らない
   （第16報 V007・第7ラウンド Z007 で同じ失敗を2回している）。
2. **採るなら帯の中央**を採る。**ピークを採らない。**
3. **最優先の合否は口座破綻の有無。** 次に最大DD が悪化していないこと。
   sca_uj の赤字を消す施策なので DD は下がるはずで、**上がったら機構の理解が間違っている。**

【事前の予想】
- **素朴な合計は予測に使わない**（上の (1)(2)(3) で3回破れている）。
  それでも**符号の向きだけは信じる**——SL距離の最小分位が両窓とも単独で最悪、
  という観察は分位に頼らない粗い事実で、09-15 の独立な四分位分割とも一致する。
- **⚠️ `G006` は「上限値」ではない。「この枠が無いのと同じ」の基準線である。**
  当初「どの掃引点も G006 を超えない」と書いたが**逆である**——G006 は 266取引を
  全部消してこの枠の寄与を 0 にするのに対し、下限フィルタは**赤字だけ消して黒字を残す。**
  残りが黒字なら **フィルタは G006 を上回る**（切り直しでは thr=0.0042 で +38,213 残る）。
  **上回ると予想する。ただし自信は低い**（切り直しは IS で符号を外している）。
  **どの点も G006 を超えなければ、SCA USDJPY を複利構成から外すのが正解**であり、
  それはそれで「枠を1つ畳む」という決着になる。
- **比較は2つに分ける**（並行セッションの指摘）。**採否はブックの幾何月利と最大DD**、
  **機構の確認は SCA USDJPY の枠純益**。G006 は equity 経路を大きく変えるので、
  ブックで見ると触っていない枠の動きが「フィルタの効果」に混ざる。
- OOS 幾何月利 **2.337% → 2.4〜2.8%**、最大DD **28.47% → 25〜29%** と見る。
  自信は低い。**±0.2pt の幅で当てられるとは思っていない。**
- **目標 6% には、この軸だけでは届かない。** 期待値は +0.1〜0.4pt である。
  現在地は `F005`（倍率2）の OOS 3.340% で、不足は約 2.7pt。**桁がひとつ足りない。**

【構成】
土台は `ml/fxqualcfm` の **`F003`**（R036 全複利・倍率1 ＋ 採用候補2件）。
対照 `G000` は `F003` と**1円まで一致すること**——一致しなければ
`ml/fxqual9` の新 input が既定値で不変ではなかったことになる（独立確認の2例目）。

**EA は触らない。** 使うのは既存 input（`ScaFilMask` / `ScaFilRangeMin`）だけなので、
デプロイもコンパイルも行わない。どのバイナリでも走る。
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
WINS = ("OOS", "IS")   # FULL は採用候補が絞れてから別ラウンドで測る

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
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

# R036 = 全複利・倍率1（含み益なしで成立する最良）。CAND = 採用済みの2件。
R036 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
            RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0)
CAND = {"RsiMechMask_UJ": 124, "PbSlopeATR_UJ": 1.40}
F003 = dict(R036, **CAND)


def t(base, **over):
    p = dict(base)
    for k, v in over.items():
        p[k] = v
    return p


def floor_(x):
    """SCA USDJPY だけにレンジ幅下限を掛ける（bit0 = magic 20261000）。"""
    return {"ScaFilMask": 1, "ScaFilRangeMin": x}


# 素朴な合計（deal ログから外挿・**実測ではない**）を description に残しておく。
# ここに書いた予測とのずれが、そのまま「複利の経路効果」の大きさになる。
PROPOSALS = [
    ("G000", "fxqualcfm/F003",
     "対照: F003（R036 全複利・倍率1 ＋ 採用候補2件）。F003 と1円まで一致すること",
     F003),

    ("G001", "G000", "SCA UJ レンジ幅下限 0.0026（素朴予測 OOS +17,379 / IS +78,447）",
     t(F003, **floor_(0.0026))),
    ("G002", "G000", "SCA UJ レンジ幅下限 0.0030（素朴予測 OOS +52,840 / IS +55,539）",
     t(F003, **floor_(0.0030))),
    ("G003", "G000", "SCA UJ レンジ幅下限 0.0036（素朴予測 OOS +29,228 / IS +21,102）",
     t(F003, **floor_(0.0036))),
    ("G004", "G000", "SCA UJ レンジ幅下限 0.0042（素朴予測 OOS +98,008 / IS +35,831）",
     t(F003, **floor_(0.0042))),
    ("G005", "G000", "SCA UJ レンジ幅下限 0.0048（素朴な合計 OOS +74,431 / IS −24,875）",
     t(F003, **floor_(0.0048))),
    # 0.0060 は F006 の 0.00595 の隣。素朴な合計は IS −119,159 と言うが、
    # **その素朴な合計こそが F006 の IS で符号ごと外れた**ので、点を落とさず測る。
    ("G007", "G000", "SCA UJ レンジ幅下限 0.0060（F006 の 0.00595 に隣接。素朴な合計 OOS +64,172 / IS −119,159）",
     t(F003, **floor_(0.0060))),

    # --- 走行中に見つかった、これより大きい問題 -------------------------------
    # 枠別を**3窓すべて**で固定ロットと並べたら、**符号が反転する枠が1つだけあった**:
    #
    #   枠        固定OOS   複利OOS    固定IS      複利IS   固定FULL     複利FULL
    #   sca_uj    -2,224   -59,795    18,563     170,103    16,339      563,327
    #   sca_gj    42,219   307,007    73,773   **-621,336** 115,992  **-1,826,948**  ⚠
    #
    # **SCA USDJPY が赤字なのは OOS だけで、IS と FULL では複利でも黒字である。**
    # **SCA GBPJPY のほうが、2窓で符号が反転し、桁もひとつ大きい**
    # （FULL で +115,992 → −1,826,948。振れ幅 −1,942,940）。
    #
    # ⚠️ これは 2026-09-15 の粗い模擬が**外している**。同 doc は GBPJPY について
    # 「狭いレンジでも黒字なので 115,992 → 111,708 とほぼ横ばい」と書いた。
    # **実測は −1,826,948。** 模擬は equity 経路を固定し、Rev ブースト×6 が
    # 複利で乗ることを含めていなかった。**切り直し系の見積りが外れた4例目。**
    #
    # したがって `FxRiskMask` のビットを枠別に落とす構成を測る。**既存 input だけ**。
    # これはサイジング掃引ではなく「**この枠を risk% に入れてよいか**」という
    # 枠ごとの問いである（`oanda_fx_risk_sizing_20260915.md` が
    # 「固定ロット枠を risk%化するのは枠ごとに符号が変わる施策」と書いたそのもの）。
    ("G008", "G000", "SCA GBPJPY だけ risk% から外す（FxRiskMask=15）。複利FULL −1,826,948 の枠",
     t(F003, FxRiskMask=15)),
    ("G009", "G000", "SCA 2枠とも risk% から外す（FxRiskMask=7）＝ fxrisk1 の R036 が実際に測っていた構成",
     t(F003, FxRiskMask=7)),

    # 上限（何をやっても超えられない値）。ScaFilRangeMin=1.0 は dist/entry<1.0 が
    # 常に真なので、**SCA USDJPY の発注が1件も出ない**＝枠を丸ごと外した構成。
    # 既存 input だけで枠を外せるので、Mult_*=0（最小ロットへ丸め戻される恐れがある）を使わない。
    ("G006", "G000", "SCA USDJPY を丸ごと外す（ScaFilRangeMin=1.0 で全件棄却）。**下限掃引の上限値**",
     t(F003, **floor_(1.0))),
]

ORDER = ["G000", "G008", "G009", "G006", "G004", "G002", "G007", "G001", "G003", "G005"]
# 対照 → **符号反転枠の risk% 解除2点**（いちばん大きい問題）→ 基準線（枠外し）→
# 帯の中心 → 帯の左 → F006 隣接点 → 端、の順。
# 途中で止まっても「この軸に天井がいくらあるか」から先に埋まる並びにする。


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
        m3.log(f"FXQUAL10_START jobs={len(jobs)} SCA UJ レンジ幅下限を複利の上で掃引")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "G000" and window == "OOS" and row.get("status") != "OK":
                m3.log("FXQUAL10_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL10_END -> {m3.OUT}")


if __name__ == "__main__":
    main()
