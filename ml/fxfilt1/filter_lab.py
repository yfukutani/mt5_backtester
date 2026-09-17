"""SCA 2枠の入口フィルタを、OANDA FX の9枠ブック自身の取引ログで事前に測る（段階2）。

【なぜ必要か】
docs/oanda_fx_risk_sizing_20260915.md の 5b節 は、SCAの入口フィルタ B2（時間帯）/ B3（方向）を
「本命」と書いたが、その数値は X2_HIGH_RISK の窓（IS窓／弱局面）での SCA GBPJPY 単枠の
ものだった。同じ枠（magic 20261001）ではあるが、OANDA FX の FULL/OOS 窓で再現する保証はない。
本スクリプトはそれを、MT5を1回も回さずに確かめる。

【なぜ取引ログだけで正しく測れるか】
SCA 2枠は基準runで固定ロット（0.01 × Revブースト）である。入口フィルタは
「取引を発注しない」だけで、残った取引のロット・SL・決済は一切変わらない。
したがって「フィルタ後の純益 = 残った取引の profit の総和」が厳密に成立する。
（risk%サイジングと組み合わせた場合は成立しない。そちらは近似として別に出す。）

【窓】
FULL = 2016-11-09〜2026-06-20（115か月）、OOS = 2016-11-09〜2021-06-20（55か月）。
OOS は FULL の前半である（EAは近年のデータで作られたため、前半が未知期間にあたる）。
よって IS = FULL − OOS = 2021-06-20〜2026-06-20。
フィルタは IS だけで決め、OOS で評価する。IS で決めた閾値を OOS に当てて初めて意味がある。

【限界】
- 段階2の簡易検証。採用の最終判断は MT5 バックテストで行う（CLAUDE.md）。
- 枠内の損益しか見ていない。証拠金の取り合いなど9枠の相互作用は反映されない。
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCA = {20261000: "SCA USDJPY", 20261001: "SCA GBPJPY"}
# OOS の終端（FULL の前半と後半を分ける境目）
SPLIT = int(datetime(2021, 6, 20, tzinfo=timezone.utc).timestamp())


def find_baseline() -> Path:
    """固定ロットの基準run（T001 = mask=0）の FULL 窓 deal ログ。"""
    for d, pat in ((ROOT / "fxrisk3" / "run_deals", "ft_full_T001_*_deals.csv"),
                   (ROOT / "fxrisk2" / "run_deals", "fs_full_S001_*_deals.csv")):
        hits = sorted(d.glob(pat))
        if hits:
            return hits[-1]
    raise SystemExit("基準runの deal ログが見つかりません")


def load(path: Path):
    """position_id で IN/OUT を突き合わせ、SCA 2枠の1取引を組み立てる。"""
    opens, trades = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        if m not in SCA:
            continue
        if r["entry"] == "0":
            opens[r["position_id"]] = r
        else:
            o = opens.pop(r["position_id"], None)
            if o is None:
                continue
            price, sl = float(o["price"]), float(o["sl"])
            if not (price > 0 and sl > 0):
                continue
            t = int(o["time"])
            trades[m].append({
                "t": t,
                "hour": datetime.fromtimestamp(t, timezone.utc).hour,
                "dow": datetime.fromtimestamp(t, timezone.utc).weekday(),
                "buy": o["type"] == "0",
                "vol": float(o["volume"]),
                "rng": abs(price - sl) / price,   # レンジ幅（価格比）
                "pl": float(r["profit"]),          # 口座通貨（円）
                "oos": t < SPLIT,
            })
    return trades


def agg(rows):
    n = len(rows)
    net = sum(r["pl"] for r in rows)
    win = sum(1 for r in rows if r["pl"] > 0)
    return n, net, (win / n if n else 0.0)


def delta(net, base_net):
    """基準比。基準が赤字のときの「%」は符号が反転して誤読を招くので、差額で出す。"""
    if base_net > 0:
        return f"{100 * net / base_net - 100:+.1f}%"
    return f"{net - base_net:+,.0f}"


def risk_sim(rows, ref_rng):
    """risk%サイジングを模擬した純益（ロット ∝ 1/レンジ幅）。

    ロットの丸め・証拠金・最小ロットの壁を無視した粗い近似。
    「risk%化でこの枠の符号がどちらへ動くか」の向きだけを見る。
    """
    return sum(r["pl"] * (ref_rng / r["rng"]) for r in rows)


def show(label, sub, base_is, base_oos, ref_rng=None):
    """IS / OOS それぞれの残存数・純益・基準比を1行で出す。"""
    i = [r for r in sub if not r["oos"]]
    o = [r for r in sub if r["oos"]]
    ni, neti, _ = agg(i)
    no, neto, _ = agg(o)
    ki = f"{100 * ni / base_is[0]:.0f}%" if base_is[0] else "-"
    ko = f"{100 * no / base_oos[0]:.0f}%" if base_oos[0] else "-"
    tail = ""
    if ref_rng is not None:
        tail = f"{risk_sim(i, ref_rng):>11,.0f}{risk_sim(o, ref_rng):>11,.0f}"
    print(f"{label:<32}{ni:>6}{ki:>6}{neti:>11,.0f}{delta(neti, base_is[1]):>10}"
          f"{no:>7}{ko:>6}{neto:>11,.0f}{delta(neto, base_oos[1]):>10}{tail}")


def main():
    path = find_baseline()
    print(f"基準run: {path.name}（固定ロット・FULL窓）")
    print("IS = 2021-06-20〜2026-06-20 ／ OOS = 2016-11-09〜2021-06-20")
    print("フィルタは IS だけで決め、OOS に当てて評価する。\n")
    trades = load(path)

    for magic, name in SCA.items():
        rows = trades[magic]
        if not rows:
            print(f"{name}: 突き合わせできた取引なし\n")
            continue
        is_rows = [r for r in rows if not r["oos"]]
        oos_rows = [r for r in rows if r["oos"]]
        base_is, base_oos = agg(is_rows), agg(oos_rows)

        # risk%模擬の基準レンジ幅（IS の中央値）。固定ロットと同スケールに揃える。
        ref_rng = sorted(r["rng"] for r in is_rows)[len(is_rows) // 2]

        print(f"=== {name} — 全{len(rows)}取引 ===")
        hdr = ("フィルタ", "IS件数", "残率", "IS純益", "基準比",
               "OOS件数", "残率", "OOS純益", "基準比", "IS risk%", "OOS risk%")
        print(f"{hdr[0]:<32}{hdr[1]:>6}{hdr[2]:>6}{hdr[3]:>11}{hdr[4]:>10}"
              f"{hdr[5]:>7}{hdr[6]:>6}{hdr[7]:>11}{hdr[8]:>10}{hdr[9]:>11}{hdr[10]:>11}")
        show("(なし・基準)", rows, base_is, base_oos, ref_rng)

        # --- B1: レンジ幅。IS の四分位で閾値を決め、OOS に当てる ---
        qs = sorted(r["rng"] for r in is_rows)
        thresholds = {}
        for label, frac in (("上位25%", 0.75), ("上位50%", 0.50)):
            thr = qs[int(len(qs) * frac)]
            thresholds[label] = thr
            show(f"B1 レンジ幅 {label}(IS閾値)",
                 [r for r in rows if r["rng"] >= thr], base_is, base_oos, ref_rng)

        # --- B2: 時間帯。IS で純益がプラスの時間だけ残す ---
        by_hour = defaultdict(float)
        for r in is_rows:
            by_hour[r["hour"]] += r["pl"]
        good_h = {h for h, v in by_hour.items() if v > 0}
        show(f"B2 時間帯 IS優位のみ({len(good_h)}時間)",
             [r for r in rows if r["hour"] in good_h], base_is, base_oos, ref_rng)

        # --- B3: 方向。IS で優位な側だけ残す ---
        buy_is = sum(r["pl"] for r in is_rows if r["buy"])
        sell_is = sum(r["pl"] for r in is_rows if not r["buy"])
        side = buy_is >= sell_is
        show(f"B3 方向 {'買いのみ' if side else '売りのみ'}(IS優位)",
             [r for r in rows if r["buy"] == side], base_is, base_oos, ref_rng)

        # --- 組み合わせ ---
        show("B2 × B3",
             [r for r in rows if r["hour"] in good_h and r["buy"] == side],
             base_is, base_oos, ref_rng)
        thr75 = thresholds["上位25%"]
        show("B1(上位25%) × B2",
             [r for r in rows if r["rng"] >= thr75 and r["hour"] in good_h],
             base_is, base_oos, ref_rng)
        thr50 = thresholds["上位50%"]
        show("B1(上位50%) × B2",
             [r for r in rows if r["rng"] >= thr50 and r["hour"] in good_h],
             base_is, base_oos, ref_rng)
        show("B1 × B2 × B3",
             [r for r in rows
              if r["rng"] >= thr75 and r["hour"] in good_h and r["buy"] == side],
             base_is, base_oos, ref_rng)

        # --- 根拠の開示: IS で何を見て決めたか ---
        print(f"  IS優位と判定した時間（サーバー時刻）: "
              f"{sorted(good_h) if good_h else 'なし'}")
        print(f"  IS  買い {buy_is:>12,.0f}円 / 売り {sell_is:>12,.0f}円")
        oos_buy = sum(r["pl"] for r in oos_rows if r["buy"])
        oos_sell = sum(r["pl"] for r in oos_rows if not r["buy"])
        print(f"  OOS 買い {oos_buy:>12,.0f}円 / 売り {oos_sell:>12,.0f}円"
              "   <- IS の向きが OOS でも同じか")
        # 時間帯ごとの内訳（IS と OOS を並べる。過剰適合の有無を見るため）
        oos_by_hour = defaultdict(float)
        for r in oos_rows:
            oos_by_hour[r["hour"]] += r["pl"]
        hours = sorted(set(by_hour) | set(oos_by_hour))
        print("  時間別純益（左=IS / 右=OOS）: " + " ".join(
            f"{h:02d}:{by_hour[h]:+,.0f}/{oos_by_hour[h]:+,.0f}" for h in hours))
        print()

    portfolio_impact(trades)
    print("\n右2列は risk% サイジングの模擬（ロット ∝ 1/レンジ幅）。丸め・証拠金・")
    print("最小ロットの壁を無視した粗い近似で、符号の向きだけを見るためのもの。")
    print("段階2の簡易検証。採用の最終判断は MT5 バックテストで行う。")


# 9枠ブック全体の OOS 純益（fxrisk3 results.csv より）。フィルタの効果を
# 「ブック全体の月利が何ポイント動くか」に翻訳するために使う。
BOOK_OOS_NET = {
    "T001（対照・複利なし・倍率1）": 246_721,
    "T034（実行可能な最良・risk1.0%×倍率1）": 1_132_932,
}
OOS_MONTHS = 55


def portfolio_impact(trades):
    """枠の改善量を、ブック全体の月利の変化に翻訳する（過大評価を防ぐため）。"""
    rows = trades[20261001]
    oos = [r for r in rows if r["oos"]]
    is_rows = [r for r in rows if not r["oos"]]
    by_hour = defaultdict(float)
    for r in is_rows:
        by_hour[r["hour"]] += r["pl"]
    good_h = {h for h, v in by_hour.items() if v > 0}
    gain = (sum(r["pl"] for r in oos if r["hour"] in good_h)
            - sum(r["pl"] for r in oos))

    print("\n=== ブック全体への効き（SCA GBPJPY の B2 時間帯フィルタ・OOS窓）===")
    print(f"枠の改善額: {gain:+,.0f}円（55か月）")
    print(f"{'構成':<40}{'OOS純益':>12}{'月利':>8}{'改善後':>12}{'月利':>8}{'差':>8}")
    for label, net in BOOK_OOS_NET.items():
        before = ((500_000 + net) / 500_000) ** (1 / OOS_MONTHS) - 1
        after = ((500_000 + net + gain) / 500_000) ** (1 / OOS_MONTHS) - 1
        print(f"{label:<40}{net:>12,.0f}{100 * before:>7.2f}%"
              f"{net + gain:>12,.0f}{100 * after:>7.2f}%"
              f"{100 * (after - before):>+7.2f}pt")


if __name__ == "__main__":
    main()
