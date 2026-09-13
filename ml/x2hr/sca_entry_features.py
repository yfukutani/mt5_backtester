"""V105：**SCA GBPJPY 1枠に絞った建玉時特徴量の識別力**（簡易検証・2026-09-14）。

【V104で分かったこと】
**不毛月は月次の情報では予測できない。**

| 検証 | 弱局面 | IS窓 |
|---|---:|---:|
| 月次損益の自己相関（ラグ1） | **−0.425** | +0.145 |
| 前月マイナス→今月マイナスの予測力 | **−14.7pt（逆方向）** | +1.7pt |
| 前月のレンジ幅 vs 今月の損益 | +0.084 | +0.400 |
| 切り替えルールの12ヶ月マイナス窓 | **7/27 → 16/27（悪化）** | 0/50 → 0/50 |

**弱局面では自己相関が負なので、「悪い月の後に止める」は最悪の手だった。**

【本スクリプトで測ること】
月次で無理なら**取引単位**。ただし V077 は**ブック全体**で5種の特徴量を試して全滅した。
**SCA GBPJPY 1枠に絞れば見えるかもしれない**——不毛月の損失の86%はこの枠だから。

| 特徴量 | 出どころ | SCAでの意味 |
|---|---|---|
| **レンジ幅** | `\|price − sl\|/price` | **アジア時間のレンジの広さ。SCAの中核** |
| 時間帯 | `time` | ロンドン/NYのどちらで抜けたか |
| 曜日 | `time` | 月曜ギャップ・金曜手仕舞い |
| 方向 | `type` | 上抜け/下抜け |

**判定はIS窓で閾値を決めてOOS（弱局面）で評価する。**
さらに**「捨てた取引の損益」も出す**——V077の教訓（入口フィルタは取引数を減らすので
`S_q/S > 1/√q` を超えないと損）を踏まえ、**残す割合と質の改善を必ず併記する。**

【限界】
- `rel_sl` はストップ距離であってレンジ幅そのものではない（SCAはレンジからSLを引くので代理）
- SCA GBPJPY の弱局面は408件。**分位に割ると各100件程度で推定は粗い**
- ISで閾値を決めてOOSで評価するが、**OOSは何度も見ている**
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl

SCA_GJ = 20261001
WEAK = (datetime(2016, 11, 9, tzinfo=timezone.utc),
        datetime(2020, 1, 1, tzinfo=timezone.utc))
IS_W = (datetime(2021, 6, 21, tzinfo=timezone.utc),
        datetime(2026, 6, 21, tzinfo=timezone.utc))


def load_sca():
    fx, gold = dkl.resolve_runs()
    rec = []
    for window in ("OOS", "IS"):
        for src in (fx.get(window), gold.get(window)):
            if src is None:
                continue
            rows = []
            for r in csv.DictReader(open(src, encoding="utf-8")):
                if int(r["magic"]) != SCA_GJ:
                    continue
                rows.append((int(r["time"]), int(r["entry"]),
                             int(r["position_id"]), float(r["profit"]),
                             int(r["type"]), float(r["price"]), float(r["sl"])))
            rows.sort()
            opened = {}
            for t, entry, pid, profit, typ, price, sl in rows:
                if entry == 0:
                    rel = (abs(price - sl) / price
                           if sl > 0 and price > 0 else 0.0)
                    opened[pid] = (t, typ, rel)
                else:
                    o = opened.pop(pid, None)
                    if o is None or profit == 0.0:
                        continue
                    d = datetime.fromtimestamp(o[0], tz=timezone.utc)
                    rec.append({"t": o[0], "profit": profit, "side": o[1],
                                "rel": o[2], "hour": d.hour,
                                "wday": d.weekday(), "dt": d})
    rec.sort(key=lambda x: x["t"])
    return rec


def sub(rec, a, b):
    return [x for x in rec if a <= x["dt"] < b]


def stat(p):
    a = np.asarray(p, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0, 0.0, 0.0
    s = float(a.mean() / a.std(ddof=1))
    t = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
    return s, t, float(a.sum())


def main():
    print("=" * 112)
    print("V105：SCA GBPJPY 1枠に絞った建玉時特徴量の識別力（簡易検証）")
    print("=" * 112)
    print("★ V104より、不毛月は**月次では予測できない**（弱局面の自己相関は −0.425）。")
    print("  → 取引単位に降りる。ただしV077はブック全体で5種すべて失敗している。")
    print("  **SCA GBPJPY 1枠に絞れば見えるか。** 不毛月の損失の86%はこの枠。\n")

    rec = load_sca()
    W, I = sub(rec, *WEAK), sub(rec, *IS_W)
    print(f"  SCA GBPJPY：弱局面 {len(W)}件 / IS窓 {len(I)}件\n")

    # ---------- 1. 特徴量ごとの層別 ----------
    print("=" * 112)
    print("【1. 特徴量ごとの層別】**IS窓で層を作り、弱局面で同じ層を見る**")
    print("=" * 112)

    def show(name, keyfn, labels_fn):
        print(f"\n--- {name} ---")
        print(f"{'層':<20}{'IS件数':>8}{'IS 純益':>11}{'IS 1取引S':>11}"
              f"{'IS t値':>8}│{'弱件数':>8}{'弱 純益':>11}{'弱 1取引S':>11}{'弱 t値':>8}")
        groups = {}
        for x in I:
            groups.setdefault(keyfn(x, I), []).append(("I", x))
        for x in W:
            groups.setdefault(keyfn(x, I), []).append(("W", x))
        for g in labels_fn(I):
            items = groups.get(g, [])
            pi = [x["profit"] for tag, x in items if tag == "I"]
            pw = [x["profit"] for tag, x in items if tag == "W"]
            if len(pi) < 15 or len(pw) < 15:
                continue
            si, ti, gi = stat(pi)
            sw, tw, gw = stat(pw)
            print(f"{str(g):<20}{len(pi):>8}{gi:>11,.0f}{si:>11.4f}{ti:>8.2f}"
                  f"│{len(pw):>8}{gw:>11,.0f}{sw:>11.4f}{tw:>8.2f}")

    # レンジ幅の四分位（ISで境界を決める）
    rel_i = np.array([x["rel"] for x in I if x["rel"] > 0])
    qs = np.quantile(rel_i, [0.25, 0.5, 0.75]) if len(rel_i) > 20 else None

    def rel_key(x, ref):
        if qs is None or x["rel"] <= 0:
            return "不明"
        r = x["rel"]
        if r <= qs[0]:
            return "レンジ 最小25%"
        if r <= qs[1]:
            return "レンジ 25-50%"
        if r <= qs[2]:
            return "レンジ 50-75%"
        return "レンジ 最大25%"

    show("レンジ幅（|price−sl|/price・ISで四分位）", rel_key,
         lambda ref: ["レンジ 最小25%", "レンジ 25-50%",
                      "レンジ 50-75%", "レンジ 最大25%"])
    show("時間帯（UTC時）", lambda x, ref: x["hour"],
         lambda ref: sorted({x["hour"] for x in ref}))
    show("曜日（0=月）", lambda x, ref: x["wday"],
         lambda ref: sorted({x["wday"] for x in ref}))
    show("方向", lambda x, ref: "買い" if x["side"] == 0 else "売り",
         lambda ref: ["買い", "売り"])

    # ---------- 2. ISで選んだフィルタをOOSで評価 ----------
    print("\n" + "=" * 112)
    print("【2. IS窓で選んだフィルタを弱局面で評価】")
    print("=" * 112)
    print("  V077の教訓：割合 q を残すと `S_q/S > 1/√q` を超えないと損になる。")
    print("  **残す割合と必要な改善率を必ず併記する。**\n")

    base_s, base_t, base_g = stat([x["profit"] for x in W])
    print(f"  弱局面の基準：{len(W)}件 / 純益 {base_g:+,.0f}円 / "
          f"1取引S {base_s:.4f}\n")

    filters = []
    # レンジ幅：ISで1取引シャープが最大の層を残す
    if qs is not None:
        best, bp = None, -1e9
        for g in ["レンジ 最小25%", "レンジ 25-50%", "レンジ 50-75%",
                  "レンジ 最大25%"]:
            pi = [x["profit"] for x in I if rel_key(x, I) == g]
            if len(pi) < 15:
                continue
            s, _, _ = stat(pi)
            if s > bp:
                best, bp = g, s
        filters.append((f"レンジ幅：IS最良の層のみ（{best}）",
                        lambda x, g=best: rel_key(x, I) == g))
    # 時間帯：ISで平均が正の時間だけ
    by_h = {}
    for x in I:
        by_h.setdefault(x["hour"], []).append(x["profit"])
    good_h = {h for h, v in by_h.items() if len(v) >= 10 and np.mean(v) > 0}
    filters.append(("時間帯：IS平均が正の時のみ",
                    lambda x, s=good_h: x["hour"] in s))
    # 曜日
    by_w = {}
    for x in I:
        by_w.setdefault(x["wday"], []).append(x["profit"])
    good_w = {w for w, v in by_w.items() if len(v) >= 10 and np.mean(v) > 0}
    filters.append(("曜日：IS平均が正の曜日のみ",
                    lambda x, s=good_w: x["wday"] in s))
    # 方向
    by_s = {}
    for x in I:
        by_s.setdefault(x["side"], []).append(x["profit"])
    best_side = max(by_s.items(), key=lambda kv: float(np.mean(kv[1])))[0]
    filters.append((f"方向：IS優位側のみ（{'買い' if best_side==0 else '売り'}）",
                    lambda x, s=best_side: x["side"] == s))

    print(f"{'フィルタ':<34}{'残る割合':>10}{'必要な改善':>12}"
          f"{'弱 純益':>11}{'弱 1取引S':>11}{'実際の改善':>12}{'判定':>7}")
    for name, fn in filters:
        keep = [x["profit"] for x in W if fn(x)]
        if len(keep) < 15:
            continue
        q = len(keep) / len(W)
        need = 1.0 / math.sqrt(q) - 1.0
        s, _, g = stat(keep)
        got = (s / base_s - 1.0) if base_s > 0 else float("nan")
        ok = got > need
        print(f"{name:<34}{100*q:>9.0f}%{100*need:>11.1f}%"
              f"{g:>11,.0f}{s:>11.4f}{100*got:>11.1f}%"
              f"{'OK' if ok else 'NG':>7}")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・`rel_sl` はストップ距離であってレンジ幅そのものではない（代理）")
    print("  ・SCA GBPJPY の弱局面は408件。分位に割ると各100件程度で推定は粗い")
    print("  ・ISで閾値を決めてOOSで評価するが、**OOSは何度も見ている**")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()
