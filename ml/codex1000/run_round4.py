from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ml" / "codex1000"
DEALS = ROOT / "ml" / "tradeoff8" / "deals"
IS0, IS1 = pd.Timestamp("2021-06-21", tz="UTC"), pd.Timestamp("2026-06-21", tz="UTC")
OOS0, OOS1 = pd.Timestamp("2016-06-21", tz="UTC"), pd.Timestamp("2021-06-21", tz="UTC")
DEPOSIT = 1_500_000.0

LEGS = [
    "pullback_usdjpy_h4", "pullback_gbpjpy_h4", "pullback_audjpy_h4",
    "rsi_robust_usdjpy_h4", "rsi_robust_eurusd_h1", "rsi_robust_gbpusd_h4",
    "pairtrade_eurusd_gbpusd", "pullback_gold_h4", "carry_audjpy_d1",
    "sca_usdjpy_m15", "sca_gbpjpy_m15", "sca_gold_m15", "eth_ea_d1",
    "fundingrev_btcusd_d1", "bfxrev_btcusd_d1",
]
CANDIDATE = {
    "pullback_usdjpy_h4", "pullback_gbpjpy_h4", "pullback_audjpy_h4",
    "rsi_robust_usdjpy_h4", "carry_audjpy_d1", "fundingrev_btcusd_d1",
    "bfxrev_btcusd_d1",
}
GROUPS = {
    "jpy": {x for x in LEGS if "jpy" in x},
    "sca": {x for x in LEGS if x.startswith("sca_")},
    "pb": {x for x in LEGS if x.startswith("pullback_")},
    "rsi": {x for x in LEGS if x.startswith("rsi_")},
    "crypto": {"eth_ea_d1", "fundingrev_btcusd_d1", "bfxrev_btcusd_d1"},
    "gold": {"pullback_gold_h4", "sca_gold_m15"},
}

FAMILIES = [
    ("F01", "sleeve DD throttle", "B", "各スリーブの確定損益DDが閾値超過時に新規lotを縮小"),
    ("F02", "portfolio equity throttle", "B", "合算equityの過去ピーク比DDで全新規lotを縮小"),
    ("F03", "loss-streak brake", "B", "スリーブ別連敗数に応じて新規lotを縮小"),
    ("F04", "rolling expectancy gate", "B", "直近確定dealの平均損益が負のスリーブを縮小"),
    ("F05", "rolling PF gate", "B", "直近確定dealのPFが低いスリーブを縮小"),
    ("F06", "rolling hit-rate gate", "B", "直近勝率が閾値未満のスリーブを縮小"),
    ("F07", "calendar weekday quality", "B", "過去同曜日成績だけで当該曜日のlotを調整"),
    ("F08", "calendar month quality", "B", "過去同月成績だけで当該月のlotを調整"),
    ("F09", "session-hour quality", "B", "過去同entry時刻成績だけでlotを調整"),
    ("F10", "quarter quality", "B", "過去同四半期成績だけでlotを調整"),
    ("F11", "JPY cluster brake", "B", "直近JPYスリーブ損益悪化時にJPY群を縮小"),
    ("F12", "crypto cluster brake", "B", "暗号資産3本の直近損益悪化時に同群を縮小"),
    ("F13", "SCA cluster brake", "B", "SCA3本の直近損益悪化時に同群を縮小"),
    ("F14", "PB cluster brake", "B", "PB4本の直近損益悪化時に同群を縮小"),
    ("F15", "RSI cluster brake", "B", "RSI3本の直近損益悪化時に同群を縮小"),
    ("F16", "gold overlap brake", "B", "GOLD2本の直近損益悪化時に同群を縮小"),
    ("F17", "cross-sectional rank", "B", "過去成績下位のスリーブだけを縮小"),
    ("F18", "profit concentration cap", "B", "直近利益寄与が一極集中した群を縮小"),
    ("F19", "loss concentration cap", "B", "直近損失寄与が集中した群を縮小"),
    ("F20", "realized-vol throttle", "B", "確定deal絶対損益の上昇を実現vol代理にして縮小"),
    ("F21", "recovery confirmation", "B", "DD中は直近損益が回復するまで縮小を維持"),
    ("F22", "cooldown by elapsed days", "B", "大幅損失後の一定日数だけ縮小"),
    ("F23", "prior-year regime", "B", "前年同スリーブが赤字なら翌年lotを縮小"),
    ("F24", "prior-quarter regime", "B", "前四半期赤字スリーブを次四半期だけ縮小"),
    ("C01", "entry-side spread feed", "C", "実spread tickを全銘柄で保存しpercentile gate"),
    ("C02", "true concurrent exposure", "C", "position ID・方向・SLから通貨deltaを再構成"),
    ("C03", "macro event blackout", "C", "改訂履歴付き経済指標カレンダーとのpoint-in-time結合"),
    ("C04", "intrabar execution optimizer", "C", "全tick板情報によるlimit/stop/market執行比較"),
]


def load_events() -> pd.DataFrame:
    rows = []
    for leg in LEGS:
        variant = "candidate" if leg in CANDIDATE else "baseline"
        f = DEALS / f"t8_pf_{variant}_{leg}.csv"
        d = pd.read_csv(f)
        d["time"] = pd.to_datetime(d["time"], unit="s", utc=True)
        d["leg"] = leg
        d["seq"] = np.arange(len(d))
        rows.append(d[["time", "profit", "leg", "seq"]])
    return pd.concat(rows).sort_values(["time", "leg", "seq"]).reset_index(drop=True)


def metrics(d: pd.DataFrame, start=None, end=None) -> dict:
    x = d
    if start is not None:
        x = x[(x.time >= start) & (x.time < end)]
    p = x.profit.to_numpy(float)
    pos, neg = p[p > 0].sum(), -p[p < 0].sum()
    eq = DEPOSIT + np.r_[0.0, np.cumsum(p)]
    peak = np.maximum.accumulate(eq)
    dd_abs = float(np.max(peak - eq))
    dd_pct = float(np.max(np.divide(peak - eq, peak, out=np.zeros_like(eq), where=peak != 0)) * 100)
    return {"net": float(p.sum()), "pf": float(pos / neg) if neg else 999.0,
            "dd_abs": dd_abs, "dd_pct": dd_pct, "trades": int(np.count_nonzero(p))}


def hist_values(hist, legs, n):
    a = []
    for leg in legs:
        a.extend(list(hist[leg])[-n:])
    return np.asarray(a, float)


def proposal_params(i):
    windows = [8, 12, 20, 30, 45, 60, 90, 120]
    scales = [0.0, .25, .5, .75, .9]
    return windows[i % 8], scales[(i // 8) % 5]


def simulate(events, family, idx):
    window, scale = proposal_params(idx)
    hist = defaultdict(lambda: deque(maxlen=500))
    pending = defaultdict(deque)
    sleeve_eq, sleeve_peak = defaultdict(float), defaultdict(float)
    total_eq = total_peak = 0.0
    streak = defaultdict(int)
    last_loss = {}
    calendar = defaultdict(lambda: defaultdict(list))
    out = []

    def score(vals, kind="mean"):
        if len(vals) < max(4, window // 4): return None
        if kind == "pf":
            pos, neg = vals[vals > 0].sum(), -vals[vals < 0].sum()
            return pos / neg if neg else 9.0
        if kind == "hit": return float(np.mean(vals > 0))
        return float(np.mean(vals))

    def entry_weight(leg, t):
        vals = np.asarray(list(hist[leg])[-window:], float)
        w = 1.0
        if family == "F01":
            dd = sleeve_peak[leg] - sleeve_eq[leg]; threshold = [500,1000,2000,4000,8000][idx//8]
            if dd > threshold: w = scale
        elif family == "F02":
            threshold = [1000,2500,5000,10000,20000][idx//8]
            if total_peak-total_eq > threshold: w = scale
        elif family == "F03" and streak[leg] >= [1,2,3,4,5][idx//8]: w = scale
        elif family in {"F04","F05","F06"}:
            kind = {"F04":"mean","F05":"pf","F06":"hit"}[family]
            s = score(vals, kind); threshold = {"mean":0,"pf":1.0,"hit":.5}[kind]
            if s is not None and s < threshold: w = scale
        elif family in {"F07","F08","F09","F10"}:
            key = {"F07":t.weekday(),"F08":t.month,"F09":t.hour,"F10":t.quarter}[family]
            cv = np.asarray(calendar[leg][(family,key)][-window:], float)
            s = score(cv)
            if s is not None and s < 0: w = scale
        elif family in {"F11","F12","F13","F14","F15","F16"}:
            gname = {"F11":"jpy","F12":"crypto","F13":"sca","F14":"pb","F15":"rsi","F16":"gold"}[family]
            if leg in GROUPS[gname]:
                gv = hist_values(hist, GROUPS[gname], window)
                if score(gv) is not None and score(gv) < 0: w = scale
        elif family == "F17":
            means = {z: score(np.asarray(list(hist[z])[-window:],float)) for z in LEGS}
            valid = [v for v in means.values() if v is not None]
            if valid and means[leg] is not None and means[leg] <= np.quantile(valid,[.2,.35,.5,.65,.8][idx//8]): w=scale
        elif family in {"F18","F19"}:
            sums = {z: np.asarray(list(hist[z])[-window:],float) for z in LEGS}
            contrib = {z:(v[v>0].sum() if family=="F18" else -v[v<0].sum()) for z,v in sums.items()}
            total=sum(contrib.values())
            cap=[.15,.2,.25,.3,.4][idx//8]
            if total>0 and contrib[leg]/total>cap: w=scale
        elif family == "F20" and len(vals)>=window:
            recent=np.mean(np.abs(vals[-max(4,window//4):])); base=np.mean(np.abs(vals))
            if base>0 and recent/base>[1.1,1.25,1.5,1.75,2.0][idx//8]: w=scale
        elif family == "F21":
            dd=sleeve_peak[leg]-sleeve_eq[leg]
            if dd>[500,1000,2000,4000,8000][idx//8] and (len(vals)<4 or vals[-4:].sum()<=0): w=scale
        elif family == "F22" and leg in last_loss:
            days=[1,2,3,5,10][idx//8]
            if (t-last_loss[leg]).total_seconds()<days*86400: w=scale
        elif family == "F23":
            prev=[p for tt,p in calendar[leg][("year",t.year-1)]]
            if prev and sum(prev)<0: w=scale
        elif family == "F24":
            pq=(t.year-1,4) if t.quarter==1 else (t.year,t.quarter-1)
            prev=[p for tt,p in calendar[leg][("qtr",pq)]]
            if prev and sum(prev)<0: w=scale
        return w

    for r in events.itertuples(index=False):
        if r.profit == 0:
            pending[r.leg].append((entry_weight(r.leg, r.time), r.time))
            out.append((r.time, 0.0, r.leg))
            continue
        w, et = pending[r.leg].popleft() if pending[r.leg] else (entry_weight(r.leg,r.time),r.time)
        p = float(r.profit) * w
        out.append((r.time,p,r.leg))
        hist[r.leg].append(p)
        sleeve_eq[r.leg]+=p; sleeve_peak[r.leg]=max(sleeve_peak[r.leg],sleeve_eq[r.leg])
        total_eq+=p; total_peak=max(total_peak,total_eq)
        streak[r.leg] = streak[r.leg]+1 if p<0 else 0
        if p < -[250,500,1000,2000,4000][idx//8]: last_loss[r.leg]=r.time
        keys=(("F07",et.weekday()),("F08",et.month),("F09",et.hour),("F10",et.quarter))
        for k in keys: calendar[r.leg][k].append(p)
        calendar[r.leg][("year",r.time.year)].append((r.time,p))
        calendar[r.leg][("qtr",(r.time.year,r.time.quarter))].append((r.time,p))
    return pd.DataFrame(out,columns=["time","profit","leg"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events=load_events()
    baseline={"full":metrics(events),"is":metrics(events,IS0,IS1),"oos":metrics(events,OOS0,OOS1)}
    proposals=[]; results=[]
    for fid,name,cls,desc in FAMILIES:
        count=40 if cls=="B" else 10
        for i in range(count):
            pid=f"{fid}-{i+1:02d}"
            if cls=="B":
                window,scale=proposal_params(i)
                params={"lookback_completed_deals":window,"risk_scale":scale}
                d=simulate(events,fid,i)
                mm={"full":metrics(d),"is":metrics(d,IS0,IS1),"oos":metrics(d,OOS0,OOS1)}
                survive=mm["is"]["net"]>0 and mm["oos"]["net"]>0
                strict=survive and all(mm[w]["net"]>baseline[w]["net"] and mm[w]["pf"]>baseline[w]["pf"] and mm[w]["dd_pct"]<=baseline[w]["dd_pct"]+1e-12 for w in ("is","oos"))
                tradeoff=survive and not strict and mm["full"]["net"]>baseline["full"]["net"] and mm["full"]["net"]/max(mm["full"]["dd_pct"],1e-9)>baseline["full"]["net"]/baseline["full"]["dd_pct"]
                row={"proposal_id":pid,"family":fid,"status":"OK","survive":survive,"strict":strict,"tradeoff":tradeoff,"params":json.dumps(params)}
                for w in ("is","oos","full"):
                    for k,v in mm[w].items(): row[f"{w}_{k}"]=v
                results.append(row)
            else:
                params={"variant":i+1,"required_data_or_build":desc}
                results.append({"proposal_id":pid,"family":fid,"status":"NOT_TESTED_C","survive":False,"strict":False,"tradeoff":False,"params":json.dumps(params)})
            proposals.append({"proposal_id":pid,"family":fid,"family_name":name,"class":cls,"overview":desc,"rationale":"現行deal列の弱点または未観測の執行情報を対象化","test_method":"entry時点までの確定dealのみでlot倍率を決定しIS/OOS/全期間を再生" if cls=="B" else "必要データと検証専用EAを実装後にtick再測定","variation":json.dumps(params,ensure_ascii=False)})
    pd.DataFrame(proposals).to_csv(OUT/"proposals.csv",index=False,encoding="utf-8-sig")
    rdf=pd.DataFrame(results)
    rdf.to_csv(OUT/"results.csv",index=False,encoding="utf-8-sig")
    (OUT/"baseline.json").write_text(json.dumps(baseline,indent=2),encoding="utf-8")
    print(json.dumps({"baseline":baseline,"counts":rdf.status.value_counts().to_dict(),"survive":int(rdf.survive.sum()),"strict":int(rdf.strict.sum()),"tradeoff":int(rdf.tradeoff.sum())},indent=2))


if __name__ == "__main__": main()
