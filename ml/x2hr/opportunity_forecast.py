"""V028：候補3位「残存取引機会数サイジング」の**事前ゲート**（Codex設計）。

【Codexの設計（要旨）】
候補3位の新規性は「取引のない日を含む暦日の上で、**過去情報だけから**残存機会数の予測を
更新すること」にある。現行の方策B（`dynamic_k.py`）は暦時間ベースではなく、
「窓全体の平均頻度から固定した取引回数ベース」であり、運用時点で使える予測になっていない。

Codexは、到達確率の大規模比較へ進む**前に**通すべきゲートを指定した。本スクリプトは
そのうち最初の2つを実装する。

- **ゲート1：ログ復元の成立** — 入口・出口の突合、数量収支、時刻順序を監査する
- **ゲート2：機会予測に追加情報があるか** — IS前半で仕様を固定し、**IS後半**で
  「60日件数のMAEが単純平均比で10%以上改善」するかを見る。
  改善しなければ複雑なモデルへ進まず、候補3位は打ち切る。

【機会の定義（Codex指定）】
> 既存戦略が通常稼働し発注が成立するという条件で、期限までに新たに開始する
> ポジション・エピソードの期待数。

deal行数や決済回数ではない。**枠（magic）ごとの「フラット→保有」への遷移**を1件と数える。
エピソード内の追加建ては独立した機会として数えない（Codexの最小案に従う）。

【予測時点の情報だけを使う】
時点 t の予測には、**t より前の180暦日**に開始したエピソードだけを使う。
t 以降に決済された建玉の情報（保有期間・結果）は一切見ない。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k_lag as dkl

LOOKBACK_DAYS = 180
HORIZONS = (7, 30, 60)
GATE_IMPROVEMENT = 0.10   # Codex提案の工学的基準（既存の実証値ではない）

# 窓の暦日範囲（docs/X2_HIGH_RISK_requirements.md §3）
WINDOW_RANGE = {
    "IS":   (datetime(2021, 6, 21, tzinfo=timezone.utc), datetime(2026, 6, 20, tzinfo=timezone.utc)),
    "OOS":  (datetime(2016, 11, 9, tzinfo=timezone.utc), datetime(2021, 6, 20, tzinfo=timezone.utc)),
    "FULL": (datetime(2016, 11, 9, tzinfo=timezone.utc), datetime(2026, 6, 20, tzinfo=timezone.utc)),
}


# ---------------------------------------------------------------- エピソードの復元
def raw_deals(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        rows.append((int(r["time"]), int(r["magic"]), int(r["entry"]),
                     int(r["position_id"]), float(r["volume"]), float(r["profit"])))
    rows.sort()
    return rows


def episodes_and_audit(paths):
    """複数ログから (magic, t_in, t_out) を復元し、エピソード（フラット→保有）を数える。

    position_id はログ間で衝突しうるため、**ログ元 + position_id** で管理する（Codex指摘）。
    profit==0 の出口も捨てない（状態復元に必要）。
    """
    opened = {}
    intervals = []
    audit = dict(rows=0, in_rows=0, out_rows=0, unmatched_out=0,
                 still_open=0, vol_mismatch=0, magic0_out=0)
    for src, p in paths:
        for t, magic, entry, pid, vol, profit in raw_deals(p):
            audit["rows"] += 1
            key = (src, pid)
            if entry == 0:
                audit["in_rows"] += 1
                opened[key] = (t, magic, vol)
            else:
                audit["out_rows"] += 1
                o = opened.pop(key, None)
                if o is None:
                    audit["unmatched_out"] += 1
                    if magic == 0:
                        audit["magic0_out"] += 1
                    continue
                t_in, m_in, v_in = o
                if abs(v_in - vol) > 1e-9:
                    audit["vol_mismatch"] += 1
                m = m_in if m_in != 0 else magic
                intervals.append((m, t_in, t))
    audit["still_open"] = len(opened)
    intervals.sort(key=lambda x: x[1])

    # 枠ごとに「フラット→保有」への遷移を数える
    holding_until = defaultdict(lambda: -1)
    episodes = []           # (magic, t_start)
    for m, t_in, t_out in intervals:
        if t_in >= holding_until[m]:
            episodes.append((m, t_in))
        holding_until[m] = max(holding_until[m], t_out)
    episodes.sort(key=lambda x: x[1])
    return episodes, intervals, audit


def daily_counts(episodes, d0, d1):
    """暦日 -> その日に開始したエピソード数。無取引日は0で埋める。"""
    n_days = (d1 - d0).days + 1
    counts = np.zeros(n_days, dtype=float)
    for _, t in episodes:
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        i = (dt.date() - d0.date()).days
        if 0 <= i < n_days:
            counts[i] += 1
    return counts


# ---------------------------------------------------------------- 予測モデル
def forecast_simple(counts, origin, horizon):
    """単純平均：過去180日の合計 ÷ 180 × horizon。"""
    lo = origin - LOOKBACK_DAYS
    return counts[lo:origin].sum() / LOOKBACK_DAYS * horizon


def forecast_weekday(counts, origin, horizon, weekday_of):
    """曜日別頻度：λ̂_w = 過去180日のその曜日の件数 ÷ その曜日の日数。"""
    lo = origin - LOOKBACK_DAYS
    num = np.zeros(7)
    den = np.zeros(7)
    for i in range(lo, origin):
        w = weekday_of[i]
        num[w] += counts[i]
        den[w] += 1
    lam = np.where(den > 0, num / np.maximum(den, 1), 0.0)
    return sum(lam[weekday_of[i]] for i in range(origin, origin + horizon))


# ---------------------------------------------------------------- メイン
def main():
    fx, gold = dkl.resolve_runs()
    print("=" * 92)
    print("V028：候補3位（残存機会数サイジング）の事前ゲート（Codex設計）")
    print("=" * 92)

    for window in ("IS", "OOS"):
        if window not in fx or window not in gold:
            continue
        srcs = [("fx", fx[window]), ("gold", gold[window])]
        episodes, intervals, audit = episodes_and_audit(srcs)
        d0, d1 = WINDOW_RANGE[window]

        print(f"\n### 窓 {window}  ({d0:%Y-%m-%d} 〜 {d1:%Y-%m-%d})")
        print("--- ゲート1：ログ復元の成立 ---")
        print(f"  deal行 {audit['rows']}  入口 {audit['in_rows']}  出口 {audit['out_rows']}")
        print(f"  未突合の出口 {audit['unmatched_out']}（うちmagic=0 {audit['magic0_out']}）"
              f" / テスト終了時の未決済 {audit['still_open']}"
              f" / 数量不一致 {audit['vol_mismatch']}")
        ok1 = (audit["unmatched_out"] == 0 and audit["vol_mismatch"] == 0)
        print(f"  建玉区間 {len(intervals)}件 → エピソード {len(episodes)}件"
              f"（1エピソードあたり{len(intervals)/max(len(episodes),1):.2f}建玉）")
        print(f"  判定: {'✅ 復元は成立' if ok1 else '⚠️ 要注意（未突合または数量不一致あり）'}")

        counts = daily_counts(episodes, d0, d1)
        n_days = len(counts)
        weekday_of = [(d0 + timedelta(days=i)).weekday() for i in range(n_days)]
        active = float((counts > 0).mean())
        print(f"  暦日 {n_days}日 / エピソードのある日 {100*active:.1f}% / "
              f"1日平均 {counts.mean():.2f}件")
        by_wd = [counts[[i for i in range(n_days) if weekday_of[i] == w]].mean() for w in range(7)]
        names = "月火水木金土日"
        print("  曜日別1日平均: " + "  ".join(f"{names[w]}{by_wd[w]:.2f}" for w in range(7)))

        # --- ゲート2：IS前半で仕様固定 → IS後半で評価 ---
        half = n_days // 2
        print(f"--- ゲート2：機会予測に追加情報があるか（前半{half}日で仕様固定 → "
              f"後半で評価） ---")
        print(f"{'期間':>6}{'評価起点数':>10}{'実績平均':>10}"
              f"{'単純平均MAE':>12}{'曜日別MAE':>11}{'改善率':>9}{'判定':>8}")
        results = {}
        for H in HORIZONS:
            origins = [t for t in range(max(half, LOOKBACK_DAYS), n_days - H)]
            if not origins:
                continue
            act, f_s, f_w = [], [], []
            for t in origins:
                act.append(counts[t:t + H].sum())
                f_s.append(forecast_simple(counts, t, H))
                f_w.append(forecast_weekday(counts, t, H, weekday_of))
            act = np.array(act); f_s = np.array(f_s); f_w = np.array(f_w)
            mae_s = float(np.abs(f_s - act).mean())
            mae_w = float(np.abs(f_w - act).mean())
            imp = (mae_s - mae_w) / mae_s if mae_s > 0 else 0.0
            verdict = "通過" if imp >= GATE_IMPROVEMENT else "不通過"
            results[H] = (mae_s, mae_w, imp)
            print(f"{H:>5}日{len(origins):>10}{act.mean():>10.1f}"
                  f"{mae_s:>12.2f}{mae_w:>11.2f}{100*imp:>8.1f}%{verdict:>8}")

        if 60 in results:
            _, _, imp60 = results[60]
            print(f"\n  → 主ゲート（60日・改善率10%以上）: "
                  f"{'✅ 通過' if imp60 >= GATE_IMPROVEMENT else '❌ 不通過'}"
                  f"（改善率 {100*imp60:.1f}%）")

        # 参考：予測/実績比のばらつき（Codex指定の確認項目）
        if 60 in results:
            origins = [t for t in range(max(half, LOOKBACK_DAYS), n_days - 60)]
            act = np.array([counts[t:t + 60].sum() for t in origins])
            f_s = np.array([forecast_simple(counts, t, 60) for t in origins])
            ratio = f_s / np.maximum(act, 1e-9)
            print(f"  参考（単純平均の予測/実績比・60日）: 中央値 {np.median(ratio):.2f}  "
                  f"10%点 {np.percentile(ratio, 10):.2f}  90%点 {np.percentile(ratio, 90):.2f}")
            print(f"  参考（60日実績件数のばらつき）: 中央値 {np.median(act):.0f}  "
                  f"最小 {act.min():.0f}  最大 {act.max():.0f}  "
                  f"変動係数 {act.std()/act.mean():.2f}")

    print("\n完了。")


if __name__ == "__main__":
    main()
