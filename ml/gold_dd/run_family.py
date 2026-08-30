"""Run concrete proposal variants in MT5, strictly one process at a time.

Each proposal is a real EA run.  No deal deletion or counterfactual
post-processing is used.  The deal log is used only to compute metrics and
verify effective lots after the EA has made all decisions.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/"ml"/"gold_dd"; CFG=ROOT/"configs"; LOG=ROOT/"logs"; DEALS=ROOT/"deals"
PROPOSALS=ROOT/"proposals.csv"; SCREEN=ROOT/"screen_results.csv"
COMMON=Path.home()/"AppData/Roaming/MetaQuotes/Terminal/Common/Files"
EXE=REPO/"mt5bt.bat"
BASE_NET=331176.79; BASE_PF=1.8718825447675405; BASE_DD=32052.72
OOS_BASE_NET=60050.52; OOS_BASE_PF=1.3961922853288133; OOS_BASE_DD=13806.08

BASE={"mt5_path":r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
 "expert":"MIX_EA_SIMVERIFY","symbol":"GOLD","period":"M15","deposit":900,
 "currency":"USD","leverage":25,"model":"every_tick",
 "parameters":{"En_PB_USDJPY":False,"En_PB_GBPJPY":False,"En_PB_AUDJPY":False,
 "En_PB_GOLD":True,"En_RSI_USDJPY":False,"En_RSI_EURUSD":False,
 "En_RSI_GBPUSD":False,"En_PAIR":False,"En_CARRY":False,"En_VBO":False,
 "En_ETH":False,"En_BTC_FUND":False,"En_BFXREV":False,"En_SCA_GOLD":True,
 "En_SCA_USDJPY":False,"En_SCA_GBPJPY":False,"FundUseWebRequest":False,
 "BfxUseWebRequest":False,"SimVerifyMode":0,"R6GoldMode":0,"R6CryptoMode":0},
 "report_dir":"results","from_date":"2021.06.21","to_date":"2026.06.20"}

# Families whose concrete proposal keys are already implemented by the
# existing GoldDD parameter-override path.  New families are added here only
# after their default-OFF EA implementation compiles and passes OFF regression.
IMPLEMENTED={
 "pb_atr_sl": {"GoldDDMode":2}, "pb_rr":{"GoldDDMode":2},
 "pb_adx":{"GoldDDMode":2}, "pb_slope":{"GoldDDMode":2},
 "sca_min_range":{"GoldDDMode":2}, "sca_max_range":{"GoldDDMode":2},
 "sca_buffer":{"GoldDDMode":2}, "sca_rr":{"GoldDDMode":2},
 "sca_boost":{"GoldDDMode":2,"GoldDDSCAUseBoost":True},
 "sca_trade_end":{"GoldDDMode":2}, "sca_force_close":{"GoldDDMode":2},
 "sca_weekday":{"GoldDDMode":4}, "pb_weekday":{"GoldDDMode":4},
}

def running():
    q=subprocess.run(["tasklist","/NH"],capture_output=True,text=True)
    s=q.stdout.lower(); return "terminal64.exe" in s or "metatester64.exe" in s

def wait_free():
    while running():
        print("WAIT: terminal64/metatester64 present",flush=True); time.sleep(15)

def metrics(path:Path):
    rows=list(csv.DictReader(path.open(encoding="utf-8-sig",newline="")))
    ps=[float(r["profit_jpy"]) for r in rows]
    win=sum(x for x in ps if x>0); loss=-sum(x for x in ps if x<0)
    bal=peak=100000.0; dd=0.0
    for p in ps: bal+=p; peak=max(peak,bal); dd=max(dd,peak-bal)
    lots=sorted({float(r["volume"]) for r in rows if float(r["volume"])>0})
    return {"net_jpy":sum(ps),"pf_jpy":win/loss if loss else math.inf,
            "dd_amount_jpy":dd,"dd_jpy":dd/1000.0,"deal_rows":len(rows),
            "effective_lots":"|".join(f"{x:.2f}" for x in lots)}

def classify_is(m):
    dd=m["dd_amount_jpy"]
    nr=m["net_jpy"]/BASE_NET; pr=m["pf_jpy"]/BASE_PF; dr=dd/BASE_DD
    if abs(m["net_jpy"]-BASE_NET)<.01 and abs(m["pf_jpy"]-BASE_PF)<1e-9 and abs(dd-BASE_DD)<.01:
        status="IS_BASELINE_EQUIVALENT"
    elif m["net_jpy"]>BASE_NET and m["pf_jpy"]>BASE_PF and dd<=BASE_DD:
        status="IS_SURVIVOR_STRICT"
    elif dd<BASE_DD and nr>=.80 and pr>=.90:
        status="IS_SURVIVOR_DD"
    elif m["net_jpy"]<=BASE_NET and m["pf_jpy"]<=BASE_PF and dd>=BASE_DD:
        status="IS_REJECT_DOMINATED"
    elif nr<.75 and dr>.80:
        status="IS_REJECT_PROFIT_LOSS"
    elif pr<.80:
        status="IS_REJECT_PF_LOSS"
    else:
        status="IS_SURVIVOR_TRADEOFF"
    reason=(f"IS net={m['net_jpy']:.2f} ({nr:.3f}x), PF={m['pf_jpy']:.6f} "
            f"({pr:.3f}x), DD={dd:.2f}円/{m['dd_jpy']:.5f}pt ({dr:.3f}x); baseline "
            f"net={BASE_NET:.2f}, PF={BASE_PF:.6f}, DD={BASE_DD:.2f}")
    return status,reason

def classify_oos(m,is_status):
    dd=m["dd_amount_jpy"]
    nr=m["net_jpy"]/OOS_BASE_NET; pr=m["pf_jpy"]/OOS_BASE_PF; dr=dd/OOS_BASE_DD
    strict=m["net_jpy"]>OOS_BASE_NET and m["pf_jpy"]>OOS_BASE_PF and dd<=OOS_BASE_DD
    dd_ok=dd<OOS_BASE_DD and nr>=.80 and pr>=.90
    if strict and is_status=="IS_SURVIVOR_STRICT": status="OOS_PASS_STRICT_BOTH"
    elif dd_ok and is_status.startswith("IS_SURVIVOR"): status="OOS_PASS_DD_BOTH"
    elif m["net_jpy"]<=OOS_BASE_NET and m["pf_jpy"]<=OOS_BASE_PF and dd>=OOS_BASE_DD:
        status="OOS_REJECT_DOMINATED"
    elif nr<.75 and dr>.80: status="OOS_REJECT_PROFIT_LOSS"
    elif pr<.80: status="OOS_REJECT_PF_LOSS"
    else: status="OOS_TRADEOFF"
    reason=(f"OOS net={m['net_jpy']:.2f} ({nr:.3f}x), PF={m['pf_jpy']:.6f} "
            f"({pr:.3f}x), DD={dd:.2f}円/{m['dd_jpy']:.5f}pt ({dr:.3f}x); baseline "
            f"net={OOS_BASE_NET:.2f}, PF={OOS_BASE_PF:.6f}, DD={OOS_BASE_DD:.2f}; IS={is_status}")
    return status,reason

def write_rows(path,rows,fields=None):
    if fields is None: fields=list(rows[0])
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
    tmp.replace(path)

def update_screen(rec):
    rows=list(csv.DictReader(SCREEN.open(encoding="utf-8-sig",newline=""))) if SCREEN.exists() else []
    rows=[r for r in rows if not (r.get("proposal_id")==rec["proposal_id"] and r.get("window")==rec["window"])]
    rows.append(rec)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    write_rows(SCREEN,rows,fields)

def run_one(row,window):
    family=row["family"]; pid=row["id"]
    if family not in IMPLEMENTED: raise RuntimeError(f"family not implemented: {family}")
    params=json.loads(row["parameter_json"])
    run=f"gdd2_{window.lower()}_{pid.lower()}_20260814"
    cfg=copy.deepcopy(BASE);cfg["report_name"]=run
    if window=="OOS": cfg.update({"from_date":"2016.06.21","to_date":"2021.06.20"})
    cfg["parameters"].update(IMPLEMENTED[family]);cfg["parameters"].update(params)
    cfg["parameters"].update({"ResultFileName":run+"_result.csv","EquityLogFile":run+"_deals.csv"})
    cp=CFG/(run+".yaml"); deal_common=COMMON/(run+"_deals.csv"); deal_local=DEALS/(run+"_deals.csv")
    if not deal_common.exists():
        cp.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
        wait_free()
        q=subprocess.run([str(EXE),"run",str(cp),"--no-charts","--no-html"],cwd=REPO,
                         capture_output=True,text=True,timeout=2400)
        (LOG/(run+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}",encoding="utf-8")
        if q.returncode!=0: raise RuntimeError(f"{run}: mt5bt rc={q.returncode}")
    if not deal_common.exists(): raise RuntimeError(f"{run}: FILE_COMMON deal missing")
    shutil.copyfile(deal_common,deal_local)
    m=metrics(deal_local)
    status,reason=classify_is(m) if window=="IS" else classify_oos(m,row["status"])
    now=datetime.now(timezone.utc).isoformat()
    if window=="IS":
        row.update({"status":status,"reason":reason,"is_net_jpy":f"{m['net_jpy']:.10f}",
                    "is_pf":f"{m['pf_jpy']:.12f}","is_dd_jpy":f"{m['dd_amount_jpy']:.10f}",
                    "effective_lots":m["effective_lots"],"run_id":run,"updated_at":now})
    else:
        row.update({"status":status,"reason":reason,"oos_net_jpy":f"{m['net_jpy']:.10f}",
                    "oos_pf":f"{m['pf_jpy']:.12f}","oos_dd_jpy":f"{m['dd_amount_jpy']:.10f}",
                    "effective_lots":m["effective_lots"],"run_id":run,"updated_at":now})
    update_screen({"window":window,"id":pid,"proposal_id":pid,"family":family,
        "parameter_json":row["parameter_json"],"status":"OK","decision":status,
        "reason":reason,"returncode":"0",**m})
    return m,status

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--family",required=True);ap.add_argument("--limit",type=int,default=20)
    ap.add_argument("--window",choices=("IS","OOS"),default="IS")
    a=ap.parse_args(); (CFG).mkdir(parents=True,exist_ok=True);LOG.mkdir(exist_ok=True);DEALS.mkdir(exist_ok=True)
    rows=list(csv.DictReader(PROPOSALS.open(encoding="utf-8-sig",newline="")))
    if a.window=="IS":
        todo=[r for r in rows if r["family"]==a.family and not r["status"].startswith("IS_")][:a.limit]
    else:
        rank={"IS_SURVIVOR_STRICT":0,"IS_SURVIVOR_DD":1,"IS_SURVIVOR_TRADEOFF":2}
        todo=[r for r in rows if r["family"]==a.family and r["status"] in rank and not r["oos_net_jpy"]]
        todo.sort(key=lambda r:(rank[r["status"]],r["id"]));todo=todo[:a.limit]
    if not todo: print("NO_PENDING_ROWS",flush=True);return
    for target in todo:
        m,status=run_one(target,a.window)
        # Persist the proposal ledger after every actual run.
        write_rows(PROPOSALS,rows,list(rows[0]))
        print(json.dumps({"id":target["id"],"family":a.family,"decision":status,**m},ensure_ascii=False),flush=True)

if __name__=="__main__": main()
