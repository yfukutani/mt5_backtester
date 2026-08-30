"""Make every GDD proposal concrete and machine-trackable.

This does not claim a backtest.  It replaces the old placeholder
``family固有水準NN/20`` with an explicit, point-in-time parameterization and
adds result/status fields.  Actual metrics are written only by MT5 runners.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "proposals.csv"

HOURS = [0,1,2,4,6,8,12,16,20,24,30,36,42,48,60,72,96,120,144,168]
COOLDOWN = [1,2,3,4,6,8,12,16,20,24,30,36,48,60,72,96,120,144,168,240]
MASKS = [62,61,59,55,47,60,58,54,46,57,53,45,51,43,39,30,29,27,23,15]
EMA_PAIRS = [(5,20),(5,30),(8,21),(8,34),(10,30),(10,40),(10,50),(12,36),(12,48),(15,40),
             (15,50),(15,60),(18,54),(20,50),(20,60),(20,75),(25,60),(25,75),(30,75),(30,100)]

MAJOR_REASONS = {
    "sca_retest": "ブレイク→再接触→再離脱の状態機械と日次状態検証が必要",
    "vol_regime_atr": "rolling ATR分位を各時点までのデータだけで更新する実装が必要",
    "vol_regime_rvol": "rolling realized-vol分位のpoint-in-time実装が必要",
    "trend_regime": "ADX×MA傾きの2次元状態機械と役割割当が必要",
    "event_calendar": "改訂・公表時刻を保持したpoint-in-time経済指標データが必要",
    "slippage_guard": "stop-limit注文状態機械と未約定・再発注の扱いが必要",
    "tail_hedge": "別Magicヘッジの発注・解消・証拠金を含む状態機械が必要",
    "role_switch": "PB/SCAのregime選択と状態引継ぎを行う状態機械が必要",
    "walkforward_selector": "過去窓のみで更新するwalk-forward選択器とウォームアップが必要",
}


def spec(family: str, i: int) -> dict:
    n = i + 1
    overlap_policy = {
        "overlap_mutex": 1, "overlap_priority_pb": 2, "overlap_priority_sca": 3,
        "overlap_direction": 4, "overlap_opposite": 5,
    }
    if family in overlap_policy:
        return {"GoldLabOverlapPolicy": overlap_policy[family],
                "GoldLabOverlapCooldownHours": HOURS[i]}
    if family == "pb_atr_sl":
        vals=[.5,.6,.7,.8,.9,1.,1.1,1.2,1.25,1.3,1.4,1.5,1.6,1.7,1.75,1.8,1.9,2.,2.25,2.5]
        return {"GoldDDPBATRSL": vals[i]}
    if family == "pb_rr": return {"GoldDDPBRR": round(.5+.1*i,2)}
    if family == "pb_adx": return {"GoldDDPBADX": 10+2.5*i}
    if family == "pb_slope": return {"GoldDDPBSlopeATR": round(.2*i,2)}
    if family == "pb_ema_pair":
        f,s=EMA_PAIRS[i]; return {"GoldLabPBFastEMA": f, "GoldLabPBSlowEMA": s}
    if family == "pb_trend_ma": return {"GoldLabPBTrendMA": 50+25*i}
    if family == "pb_adx_period": return {"GoldLabPBADXPeriod": 5+i}
    if family == "pb_candle_body": return {"GoldLabPBCandleBodyMin": round(.05*n,2)}
    if family == "pb_close_location": return {"GoldLabPBCloseLocationMin": round(.05*n,2)}
    if family == "pb_pullback_depth": return {"GoldLabPBPullbackDepthATR": round(.1*n,2)}
    if family == "pb_extension_cap": return {"GoldLabPBExtensionCapATR": round(.5*n,2)}
    if family == "pb_higher_tf": return {"GoldLabPBHigherTFMA": 50+25*i}
    if family == "pb_hold_limit": return {"GoldLabPBHoldBars": 4*n}
    if family == "pb_breakeven": return {"GoldLabPBBETriggerATR": round(.25*n,2)}
    if family == "pb_trailing": return {"GoldLabPBTrailATR": round(.25*n,2)}
    if family == "sca_min_range": return {"GoldDDSCAMinRange": round(.05*n,2)}
    if family == "sca_max_range": return {"GoldDDSCAMaxRange": round(.5+.1*i,2)}
    if family == "sca_buffer": return {"GoldDDSCABuffer": round(.01*i,2)}
    if family == "sca_rr": return {"GoldDDSCARR": round(.5+.1*i,2)}
    if family == "sca_boost": return {"GoldDDSCABoostMult": n}
    if family == "sca_trade_end": return {"GoldDDSCATradeEnd": 4+i}
    if family == "sca_force_close": return {"GoldDDSCAForceClose": 4+i}
    if family == "sca_range_start": return {"GoldLabSCARangeStart": i}
    if family == "sca_range_end": return {"GoldLabSCARangeEnd": 4+i}
    if family in ("sca_weekday","pb_weekday"):
        return {"GoldDDSCAWeekMask" if family=="sca_weekday" else "GoldDDPBWeekMask": MASKS[i]}
    if family == "sca_one_direction":
        return {"GoldLabSCADirectionPolicy": 1 if i<10 else 2,
                "GoldLabSCADriftMinATR": round(.1*(i%10),2)}
    if family == "sca_failed_break": return {"GoldLabSCAFailedBreakLockHours": n}
    if family == "portfolio_loss_cooldown": return {"GoldLabPortfolioCooldownHours": COOLDOWN[i]}
    if family == "sleeve_loss_cooldown": return {"GoldLabSleeveCooldownHours": COOLDOWN[i]}
    if family == "daily_loss_cap": return {"GoldLabDailyLossCapJPY": 1000*n}
    if family == "weekly_loss_cap": return {"GoldLabWeeklyLossCapJPY": 2000*n}
    if family == "equity_overlap_cap": return {"GoldLabFloatingLossCapPct": round(.1*n,2)}
    if family == "range_regime": return {"GoldLabPrevRangeATRMax": round(.25*n,2)}
    if family == "gap_regime": return {"GoldLabGapATRMax": round(.1*n,2)}
    if family == "spread_gate": return {"GoldLabMaxSpreadPoints": 10*n}
    if family in MAJOR_REASONS: return {"design_level": n}
    raise KeyError(family)


def main() -> None:
    rows=list(csv.DictReader(PATH.open(encoding="utf-8-sig",newline="")))
    per_family={}
    for r in rows:
        idx=per_family.get(r["family"],0); per_family[r["family"]]=idx+1
        s=spec(r["family"],idx)
        r["variation"]=json.dumps(s,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        r["parameter_json"]=r["variation"]
        if r["family"] in MAJOR_REASONS:
            r["status"]="UNTESTED_MAJOR_DEVELOPMENT"
            r["reason"]=MAJOR_REASONS[r["family"]]
        else:
            r["status"]="PENDING_IMPLEMENTATION"
            r["reason"]="具体値定義済み。検証専用EAへの既定OFF実装とMT5実測待ち"
        for k in ("is_net_jpy","is_pf","is_dd_jpy","oos_net_jpy","oos_pf","oos_dd_jpy",
                  "effective_lots","run_id","updated_at"):
            r[k]=""
    assert len(rows)==1000 and all(v==20 for v in per_family.values())
    fields=list(rows[0])
    with PATH.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(f"concretized {len(rows)} proposals; major={sum(r['status'].startswith('UNTESTED_MAJOR') for r in rows)}")


if __name__=="__main__": main()
