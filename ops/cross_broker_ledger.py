# -*- coding: utf-8 -*-
"""cross_broker_ledger.py v2 -- クロスブローカー執行コスト台帳（B-3改良版）

mixlog CSV（MIX_EAのEnableOpsLogが書く <prefix>_YYYYMM.csv・各端末のMQL5\\Files配下）から
同期枠（既定: SCA×3 / PairTrade / VBO）のXM↔OANDA突合台帳を生成する。

2026-07-25改善案 B-3 / F-6 で追加した点:
  1. 1:1突合が成立しなかったシグナルを警告として明示出力（従来は無警告で除外）＋カバー率表示
  2. S-4是正日を境にした before/after フラグ（--s4-start/--s4-end のXM 2倍リスク期間）。
     期間内のXM側重複往復（同magic・同symbol・近接エントリー・同ロット）は1本に補正して突合し
     S4_DEDUP フラグを付け、既定でコスト集計から除外（--include-s4 で含める）
  3. 両ブローカーのエントリー/決済時刻差を併記し、決済時刻差が --time-diff-limit 秒（既定60）を
     超えるペアは TIMEDIFF フラグでコスト集計から除外（F-3: 決済非同期時の前提崩れ対策）

使い方（運用PCの例）:
  python cross_broker_ledger.py --xm <XM端末>\\MQL5\\Files\\mixlog_202607.csv ^
      --oanda <OANDA-FX端末>\\...\\mixlog_202607.csv --oanda <OANDA-CFD端末>\\...\\mixlog_202607.csv ^
      --s4-start "2026-07-21 00:07" --s4-end "<是正日時>" --out ledger.csv

注意: mixlogのtime列はTimeCurrent（サーバー時刻）のエポック秒。XMとOANDAのサーバー時差が
ある場合は --tz-shift-oanda（時間単位）で補正する（両者GMT+3なら0のまま）。
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SLEEVE_NAMES = {
    20261000: "SCA_USDJPY",
    20261001: "SCA_GBPJPY",
    20261002: "SCA_GOLD",
    20260629: "PAIR",
    20260680: "VBO_USDJPY",
}
DEFAULT_MAGICS = sorted(SLEEVE_NAMES)
DUP_WINDOW_S = 120       # 同一ソース内の重複判定: エントリー時刻がこれ以内かつ同ロット
LEG_CLUSTER_S = 120      # 複数銘柄枠（PairTrade）のレグを1シグナルに束ねる窓


def read_deals(paths, magics):
    """mixlog CSV群からDEAL行を読む。列: time,type,magic,symbol,f1..f6,note"""
    deals = []
    for path in paths:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                try:
                    if row["type"] != "DEAL":
                        continue
                    magic = int(row["magic"])
                    if magic not in magics:
                        continue
                    deals.append({
                        "time": int(row["time"]),
                        "magic": magic,
                        "symbol": row["symbol"],
                        "side": int(float(row["f1"])),
                        "lot": float(row["f2"]),
                        "price": float(row["f3"]),
                        "pnl": float(row["f6"]),
                        "inout": row["note"].strip(),
                        "src": path,
                    })
                except (KeyError, ValueError):
                    continue
    deals.sort(key=lambda d: d["time"])
    return deals


def build_roundtrips(deals):
    """(magic,symbol)ごとにIN→OUTをFIFOで往復化。決済されていないINはopenとして返す。"""
    rts, opens = [], []
    queues = defaultdict(list)
    for d in deals:
        key = (d["magic"], d["symbol"])
        if d["inout"] == "IN":
            queues[key].append(d)
        elif d["inout"] == "OUT" and queues[key]:
            e = queues[key].pop(0)
            rts.append({
                "magic": d["magic"], "symbol": d["symbol"], "lot": e["lot"],
                "entry_time": e["time"], "exit_time": d["time"],
                "pnl": e["pnl"] + d["pnl"],
            })
    for q in queues.values():
        opens.extend(q)
    return rts, opens


def dedup_roundtrips(rts, s4_start, s4_end, warnings, side_label):
    """同magic・同symbol・エントリー近接・同ロットの重複往復を検出。
    S-4期間内は1本に補正（S4_DEDUPフラグ）、期間外は警告のみ（補正しない）。"""
    out = []
    used = [False] * len(rts)
    rts = sorted(rts, key=lambda r: (r["magic"], r["symbol"], r["entry_time"]))
    for i, r in enumerate(rts):
        if used[i]:
            continue
        dups = []
        for j in range(i + 1, len(rts)):
            s = rts[j]
            if used[j] or s["magic"] != r["magic"] or s["symbol"] != r["symbol"]:
                continue
            if abs(s["entry_time"] - r["entry_time"]) <= DUP_WINDOW_S and s["lot"] == r["lot"]:
                dups.append(j)
        r = dict(r)
        r["flags"] = []
        if dups:
            in_s4 = s4_start is not None and s4_start <= r["entry_time"] and (s4_end is None or r["entry_time"] < s4_end)
            ts = datetime.utcfromtimestamp(r["entry_time"]).strftime("%Y-%m-%d %H:%M")
            if in_s4:
                for j in dups:
                    used[j] = True
                r["flags"].append("S4_DEDUP_%dto1" % (len(dups) + 1))
                warnings.append("[S4-DEDUP] %s %s %s entry=%s: %d duplicate roundtrips in the S-4 window collapsed to 1"
                                % (side_label, SLEEVE_NAMES.get(r["magic"], r["magic"]), r["symbol"], ts, len(dups) + 1))
            else:
                warnings.append("[WARN-DUP] %s %s %s entry=%s: %d near-simultaneous roundtrips OUTSIDE the S-4 window (not collapsed; investigate)"
                                % (side_label, SLEEVE_NAMES.get(r["magic"], r["magic"]), r["symbol"], ts, len(dups) + 1))
        out.append(r)
    return out


def build_signals(rts):
    """同magicで近接エントリーの往復（PairTradeの2レグ等）を1シグナルに束ねる。"""
    signals = []
    rts = sorted(rts, key=lambda r: (r["magic"], r["entry_time"]))
    cur = None
    for r in rts:
        if (cur is not None and r["magic"] == cur["magic"]
                and r["entry_time"] - cur["entry_time_last"] <= LEG_CLUSTER_S):
            cur["legs"].append(r)
            cur["entry_time_last"] = r["entry_time"]
        else:
            if cur is not None:
                signals.append(cur)
            cur = {"magic": r["magic"], "entry_time": r["entry_time"],
                   "entry_time_last": r["entry_time"], "legs": [r]}
    if cur is not None:
        signals.append(cur)
    for s in signals:
        s["symbols"] = "+".join(sorted({l["symbol"] for l in s["legs"]}))
        s["lot"] = max(l["lot"] for l in s["legs"])
        s["pnl"] = sum(l["pnl"] for l in s["legs"])
        s["exit_time"] = max(l["exit_time"] for l in s["legs"])
        s["flags"] = sorted({f for l in s["legs"] for f in l.get("flags", [])})
    return signals


def match_signals(xm, oa, window_s, warnings):
    """同magicのシグナルをエントリー時刻近接で1:1突合。1:Nは警告して除外。"""
    pairs, used_oa = [], set()
    for x in xm:
        cands = [(abs(x["entry_time"] - o["entry_time"]), i) for i, o in enumerate(oa)
                 if o["magic"] == x["magic"] and abs(x["entry_time"] - o["entry_time"]) <= window_s]
        cands.sort()
        name = SLEEVE_NAMES.get(x["magic"], str(x["magic"]))
        ts = datetime.utcfromtimestamp(x["entry_time"]).strftime("%Y-%m-%d %H:%M")
        if not cands:
            warnings.append("[UNMATCHED] XM %s %s entry=%s: no OANDA counterpart within %ds"
                            % (name, x["symbols"], ts, window_s))
            continue
        free = [c for c in cands if c[1] not in used_oa]
        if len(cands) > 1:
            warnings.append("[WARN-1N] XM %s %s entry=%s: %d OANDA candidates within window (nearest used)"
                            % (name, x["symbols"], ts, len(cands)))
        if not free:
            warnings.append("[UNMATCHED] XM %s %s entry=%s: all OANDA candidates already paired (N:1 collision)"
                            % (name, x["symbols"], ts))
            continue
        i = free[0][1]
        used_oa.add(i)
        pairs.append((x, oa[i]))
    for i, o in enumerate(oa):
        if i not in used_oa:
            name = SLEEVE_NAMES.get(o["magic"], str(o["magic"]))
            ts = datetime.utcfromtimestamp(o["entry_time"]).strftime("%Y-%m-%d %H:%M")
            warnings.append("[UNMATCHED] OANDA %s %s entry=%s: no XM counterpart within %ds"
                            % (name, o["symbols"], ts, window_s))
    return pairs


def main(argv=None):
    ap = argparse.ArgumentParser(description="cross-broker execution-cost ledger v2 (B-3)")
    ap.add_argument("--xm", action="append", required=True, help="XM mixlog CSV (repeatable)")
    ap.add_argument("--oanda", action="append", required=True,
                    help="OANDA mixlog CSV (repeatable; pass both FX and CFD terminals)")
    ap.add_argument("--out", default="ledger.csv")
    ap.add_argument("--magics", type=int, nargs="*", default=DEFAULT_MAGICS)
    ap.add_argument("--match-window", type=int, default=600, help="entry-time match window seconds")
    ap.add_argument("--time-diff-limit", type=int, default=60,
                    help="exclude pairs whose exit-time difference exceeds this (seconds)")
    ap.add_argument("--s4-start", default="2026-07-21 00:07",
                    help="start of the XM double-instance period, server-time 'YYYY-MM-DD HH:MM' ('' to disable)")
    ap.add_argument("--s4-end", default="",
                    help="correction datetime, server-time 'YYYY-MM-DD HH:MM' (empty = still open)")
    ap.add_argument("--include-s4", action="store_true",
                    help="include S4-deduped pairs in the cost statistics (default: excluded)")
    ap.add_argument("--tz-shift-oanda", type=float, default=0.0,
                    help="hours to ADD to OANDA times to align with XM server time")
    args = ap.parse_args(argv)

    def parse_dt(s):
        if not s:
            return None
        return int((datetime.strptime(s, "%Y-%m-%d %H:%M") - datetime(1970, 1, 1)).total_seconds())

    s4_start, s4_end = parse_dt(args.s4_start), parse_dt(args.s4_end)
    magics = set(args.magics)
    warnings = []

    xm_deals = read_deals(args.xm, magics)
    oa_deals = read_deals(args.oanda, magics)
    shift = int(args.tz_shift_oanda * 3600)
    for d in oa_deals:
        d["time"] += shift

    xm_rts, xm_open = build_roundtrips(xm_deals)
    oa_rts, oa_open = build_roundtrips(oa_deals)
    xm_rts = dedup_roundtrips(xm_rts, s4_start, s4_end, warnings, "XM")
    oa_rts = dedup_roundtrips(oa_rts, None, None, warnings, "OANDA")
    xm_sig = build_signals(xm_rts)
    oa_sig = build_signals(oa_rts)

    for d in xm_open + oa_open:
        side = "XM" if d in xm_open else "OANDA"
        ts = datetime.utcfromtimestamp(d["time"]).strftime("%Y-%m-%d %H:%M")
        warnings.append("[OPEN] %s %s %s entry=%s lot=%.2f: position still open (not in ledger)"
                        % (side, SLEEVE_NAMES.get(d["magic"], d["magic"]), d["symbol"], ts, d["lot"]))

    pairs = match_signals(xm_sig, oa_sig, args.match_window, warnings)

    rows = []
    for x, o in pairs:
        entry_diff = x["entry_time"] - o["entry_time"]
        exit_diff = x["exit_time"] - o["exit_time"]
        flags = list(x["flags"]) + list(o["flags"])
        if s4_start is not None and s4_start <= x["entry_time"] and (s4_end is None or x["entry_time"] < s4_end):
            flags.append("S4_PERIOD")
        else:
            flags.append("POST_S4" if (s4_end is not None and x["entry_time"] >= s4_end) else "PRE_S4")
        excluded = []
        if abs(exit_diff) > args.time_diff_limit:
            excluded.append("TIMEDIFF")
        # 集計除外はXM側の実重複を補正したペアのみ（決済レースで執行品質が汚染されているため）。
        # 単発だがS-4期間内のペアはS4_PERIODフラグ付きで集計に残し、期間別に分割表示する。
        if not args.include_s4 and any(f.startswith("S4_DEDUP") for f in flags):
            excluded.append("S4")
        rows.append({
            "sleeve": SLEEVE_NAMES.get(x["magic"], str(x["magic"])),
            "magic": x["magic"], "symbols": x["symbols"], "lot": "%.2f" % x["lot"],
            "xm_entry": datetime.utcfromtimestamp(x["entry_time"]).strftime("%Y-%m-%d %H:%M:%S"),
            "entry_diff_s": entry_diff, "exit_diff_s": exit_diff,
            "xm_pnl": "%.0f" % x["pnl"], "oanda_pnl": "%.0f" % o["pnl"],
            "diff_xm_minus_oanda": "%.0f" % (x["pnl"] - o["pnl"]),
            "flags": "|".join(flags), "excluded": "|".join(excluded),
            "in_stats": 0 if excluded else 1,
        })

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        cols = ["sleeve", "magic", "symbols", "lot", "xm_entry", "entry_diff_s", "exit_diff_s",
                "xm_pnl", "oanda_pnl", "diff_xm_minus_oanda", "flags", "excluded", "in_stats"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    stat = [r for r in rows if r["in_stats"] == 1]
    total = sum(float(r["diff_xm_minus_oanda"]) for r in stat)
    print("=" * 78)
    print("cross-broker ledger v2  (magics: %s)" % ", ".join(SLEEVE_NAMES.get(m, str(m)) for m in sorted(magics)))
    print("XM signals=%d  OANDA signals=%d  matched pairs=%d  in cost stats N=%d"
          % (len(xm_sig), len(oa_sig), len(pairs), len(stat)))
    cov = 100.0 * len(pairs) / max(1, max(len(xm_sig), len(oa_sig)))
    print("coverage=%.0f%%  excluded: TIMEDIFF=%d  S4=%d"
          % (cov, sum(1 for r in rows if "TIMEDIFF" in r["excluded"]),
             sum(1 for r in rows if "S4" in r["excluded"])))
    if stat:
        print("cumulative XM-OANDA diff = %+.0f JPY  (mean %+.1f JPY/pair, N=%d)"
              % (total, total / len(stat), len(stat)))
        # S-4是正日をまたぐデータを暗黙に混在させない: 期間別の内訳を常に表示する
        for period in ("PRE_S4", "S4_PERIOD", "POST_S4"):
            seg = [r for r in stat if period in r["flags"].split("|")]
            if seg:
                seg_total = sum(float(r["diff_xm_minus_oanda"]) for r in seg)
                print("  segment %-9s N=%d  diff=%+.0f JPY" % (period, len(seg), seg_total))
    print("-" * 78)
    if warnings:
        print("WARNINGS (%d):" % len(warnings))
        for wmsg in warnings:
            print("  " + wmsg)
    else:
        print("WARNINGS: none")
    print("ledger written: %s (%d rows)" % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
