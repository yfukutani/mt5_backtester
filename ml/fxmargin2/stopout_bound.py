"""「含み損を含まない証拠金判定」という積年の穴を、SL から厳密に塞ぐ（段階2）。

【何に答えるか】
`docs/oanda_fx_scagj_weight_20260915.md` §4 と `margin_feasibility.py` は
どちらも同じ警告を付けている——

> equity は確定損益だけで作っており、含み益・含み損を含まない。

この穴があるせいで、A10（証拠金上限サイジング）の結果を採否に使えない。
本スクリプトは**近似ではなく上界**でこれを塞ぐ。

【なぜ上界が取れるか】
建玉には SL が入っている。**SL より下へは（ギャップを除き）損は進まない。**
したがって、ある時点の「起こりうる最悪の equity」は

    equity_worst = 確定equity − Σ_建玉 (約定価格 と SL の差 × ロット × 契約 × JPY換算)

であり、これは**その時点で実際に起きうる最悪値の下限**である。
これを使えば証拠金維持率の**最悪値**が出る:

    margin_level_worst = equity_worst / 使用証拠金

OANDA証券MT5 は**証拠金維持率 100% で追証・50% でロスカット**である。
`margin_level_worst` が 50% を割らなければ、**その構成はロスカットされない**と言える
（ギャップ・スワップ・SL未設定の建玉を除く。下記の限界を読むこと）。

【限界・必ず読むこと】
- **週明けギャップ・指標時の飛びは SL を越える。** 上界は「SLが機能した場合」の話。
- **SL を持たない建玉**（Carry など）は損失に下限が無い。件数と寄与を別に出す。
- **スワップ・手数料**は含まない。
- 確定 equity は deal ログの profit（スワップ込みの決済損益）から積んでいる。
- **段階2の簡易検証。採用の最終判断は MT5 バックテストで行う。**
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import margin_cap_sim as M

STOPOUT_LEVEL = 0.50      # 証拠金維持率 50% でロスカット
MARGINCALL_LEVEL = 1.00   # 100% で追証


def sl_loss_jpy(row, lot):
    """この建玉が SL で決済されたときの損失（JPY・正の値）。SL 無しなら None。"""
    sl = float(row["sl"])
    if sl <= 0:
        return None
    price = float(row["price"])
    magic = int(row["magic"])
    kind = M.KIND.get(magic)
    if kind is None:
        return None
    dist = abs(price - sl)
    quote_loss = dist * lot * M.CONTRACT          # 決済通貨建ての損失
    if kind == "price":                            # クロス円＝決済通貨がJPY
        return quote_loss
    usdjpy = float(row["usdjpy"])                  # ドルストレート＝決済通貨がUSD
    return quote_loss * usdjpy if usdjpy > 0 else None


def run(rows, comp_magics, cap):
    """A10 と同じロット決定を行いながら、含み損の上界つきで証拠金維持率を追う。"""
    log_eq = sim_eq = float(M.DEPOSIT)
    used = 0.0
    pos = {}
    worst_level = float("inf")     # equity_worst / used の最小値
    worst_at = None
    worst_detail = ""
    nosl_open_max = 0              # SL無し建玉の同時最大数
    nosl_margin_max = 0.0          # SL無し建玉が占めた証拠金の最大
    below_call = below_stop = 0
    obs = 0

    for r in rows:
        magic = int(r["magic"])
        pid = r["position_id"]
        if r["entry"] == "0":
            rate = M.jpy_rate(r)
            vol = float(r["volume"])
            if rate is None or rate <= 0 or vol <= 0:
                continue
            need_unit = vol * M.CONTRACT * rate / M.LEVERAGE
            k = (sim_eq / log_eq) if (magic in comp_magics and log_eq > 0) else 1.0
            k = max(0.0, k)
            if cap is not None and sim_eq > 0:
                avail = cap * sim_eq - used
                if need_unit * k > avail:
                    k = max(0.0, avail / need_unit) if need_unit > 0 else 0.0
            lot = math.floor(vol * k / M.LOT_STEP) * M.LOT_STEP
            if lot < M.MIN_LOT - 1e-12:
                pos[pid] = {"k": 0.0, "need": need_unit, "vl": vol,
                            "m": magic, "risk": 0.0, "nosl": False}
                continue
            k = lot / vol
            risk = sl_loss_jpy(r, lot)
            pos[pid] = {"k": k, "need": need_unit, "vl": vol, "m": magic,
                        "risk": risk if risk is not None else 0.0,
                        "nosl": risk is None}
            used += need_unit * k
        else:
            p = pos.get(pid)
            profit = float(r["profit"])
            vol = float(r["volume"])
            log_eq += profit
            if p is None:
                sim_eq += profit
            else:
                sim_eq += profit * p["k"]
                frac = min(1.0, vol / p["vl"]) if p["vl"] > 0 else 1.0
                used -= p["need"] * p["k"] * frac
                p["vl"] -= vol
                if p["vl"] <= 1e-9:
                    pos.pop(pid, None)
            used = max(0.0, used)

        # ---- この時点の「起こりうる最悪の equity」で維持率を見る ----
        live = [p for p in pos.values() if p["k"] > 0]
        if used > 0 and live:
            risk_sum = sum(p["risk"] for p in live)
            nosl = [p for p in live if p["nosl"]]
            nosl_open_max = max(nosl_open_max, len(nosl))
            nosl_margin_max = max(nosl_margin_max,
                                  sum(p["need"] * p["k"] for p in nosl))
            eq_worst = sim_eq - risk_sum
            level = eq_worst / used
            obs += 1
            if level < MARGINCALL_LEVEL:
                below_call += 1
            if level < STOPOUT_LEVEL:
                below_stop += 1
            if level < worst_level:
                worst_level = level
                worst_at = int(r["time"])
                by = defaultdict(float)
                for p in live:
                    by[p["m"]] += p["risk"]
                worst_detail = " / ".join(
                    "%s %s" % (M.SLEEVE_NAME.get(m, m), format(round(v), ","))
                    for m, v in sorted(by.items(), key=lambda x: -x[1])[:3])

    when = (datetime.fromtimestamp(worst_at, timezone.utc).strftime("%Y-%m-%d")
            if worst_at else "-")
    return {"worst_level": worst_level if worst_level < float("inf") else 0.0,
            "when": when, "detail": worst_detail, "obs": obs,
            "below_call": below_call, "below_stop": below_stop,
            "nosl_max": nosl_open_max, "nosl_margin": nosl_margin_max,
            "net": sim_eq - M.DEPOSIT}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--caps", default="none,1.0,0.7,0.5,0.3,0.2")
    args = ap.parse_args()
    ids = args.ids or ["T036", "T035", "T043", "T034"]
    repo = Path(__file__).resolve().parents[2]
    caps = [None if c == "none" else float(c) for c in args.caps.split(",")]

    print("含み損の上界つき証拠金維持率（SLまで逆行した最悪ケース）")
    print("OANDA証券MT5: 維持率100%で追証・50%でロスカット。")
    print("SLを持たない建玉は損失に下限が無いため別掲。ギャップ・スワップは未考慮。\n")
    for pid in ids:
        params, desc = M.params_of(repo, pid)
        comp = M.compounding_magics(params)
        print("■ %s  %s" % (pid, desc))
        for win in ("full", "oos"):
            rows = M.load(repo, pid, win)
            if not rows:
                continue
            print("  --- %s ---" % win.upper())
            print("    %6s %14s %12s %12s %10s %12s %11s"
                  % ("cap", "純益", "最悪維持率", "その日", "追証割れ",
                     "ロスカット", "SL無し建玉"))
            for cap in caps:
                s = run(rows, comp, cap)
                label = "無制限" if cap is None else "%.0f%%" % (cap * 100)
                verdict = "★ロスカット" if s["below_stop"] else (
                    "追証" if s["below_call"] else "安全")
                print("    %6s %14s %10.0f%% %12s %6d/%-6d %6d  %s  最大%d本/%s円"
                      % (label, format(round(s["net"]), ","),
                         s["worst_level"] * 100, s["when"],
                         s["below_call"], s["obs"], s["below_stop"], verdict,
                         s["nosl_max"], format(round(s["nosl_margin"]), ",")))
        print()
    print("注: 「安全」は『SLが機能する限りロスカットされない』の意味である。")
    print("    週明けギャップ・指標時の飛びはSLを越えるため、この保証の外にある。")


if __name__ == "__main__":
    main()
