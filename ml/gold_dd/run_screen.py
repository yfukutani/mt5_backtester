"""Sequential GOLD2 IS/OOS MT5 screen. No post-processing of trade decisions."""
from __future__ import annotations

import copy, csv, math, subprocess, time
from pathlib import Path
import yaml

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/"ml"/"gold_dd"; CFG=ROOT/"configs"; LOG=ROOT/"logs"; DEALS=ROOT/"deals"
COMMON=Path.home()/"AppData/Roaming/MetaQuotes/Terminal/Common/Files"
OUT=ROOT/"screen_results.csv"; EXE=REPO/"mt5bt.bat"
BASE={"mt5_path":r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe","expert":"MIX_EA_SIMVERIFY",
 "symbol":"GOLD","period":"M15","deposit":900,"currency":"USD","leverage":25,"model":"every_tick",
 "parameters":{"En_PB_USDJPY":False,"En_PB_GBPJPY":False,"En_PB_AUDJPY":False,"En_PB_GOLD":True,
 "En_RSI_USDJPY":False,"En_RSI_EURUSD":False,"En_RSI_GBPUSD":False,"En_PAIR":False,"En_CARRY":False,
 "En_VBO":False,"En_ETH":False,"En_BTC_FUND":False,"En_BFXREV":False,"En_SCA_GOLD":True,
 "En_SCA_USDJPY":False,"En_SCA_GBPJPY":False,"FundUseWebRequest":False,"BfxUseWebRequest":False,
 "SimVerifyMode":0,"R6GoldMode":0,"R6CryptoMode":0},"report_dir":"results"}

CASES=[
 ("OFF",{}),("MUTEX",{"GoldDDMode":1}),
 ("PB_SL100",{"GoldDDMode":2,"GoldDDPBATRSL":1.0}),("PB_SL125",{"GoldDDMode":2,"GoldDDPBATRSL":1.25}),
 ("PB_SL150",{"GoldDDMode":2,"GoldDDPBATRSL":1.5}),("PB_SL175",{"GoldDDMode":2,"GoldDDPBATRSL":1.75}),
 ("PB_ADX25",{"GoldDDMode":2,"GoldDDPBADX":25.0}),("PB_ADX275",{"GoldDDMode":2,"GoldDDPBADX":27.5}),
 ("PB_ADX30",{"GoldDDMode":2,"GoldDDPBADX":30.0}),("PB_ADX35",{"GoldDDMode":2,"GoldDDPBADX":35.0}),
 ("PB_SLOPE15",{"GoldDDMode":2,"GoldDDPBSlopeATR":1.5}),("PB_SLOPE18",{"GoldDDMode":2,"GoldDDPBSlopeATR":1.8}),
 ("PB_SLOPE20",{"GoldDDMode":2,"GoldDDPBSlopeATR":2.0}),
 ("SCA_MAX060",{"GoldDDMode":2,"GoldDDSCAMaxRange":.60}),("SCA_MAX070",{"GoldDDMode":2,"GoldDDSCAMaxRange":.70}),
 ("SCA_MAX080",{"GoldDDMode":2,"GoldDDSCAMaxRange":.80}),("SCA_MAX090",{"GoldDDMode":2,"GoldDDSCAMaxRange":.90}),
 ("SCA_BUF075",{"GoldDDMode":2,"GoldDDSCABuffer":.075}),("SCA_BUF100",{"GoldDDMode":2,"GoldDDSCABuffer":.10}),
 ("SCA_BUF150",{"GoldDDMode":2,"GoldDDSCABuffer":.15}),("SCA_RR100",{"GoldDDMode":2,"GoldDDSCARR":1.0}),
 ("SCA_RR125",{"GoldDDMode":2,"GoldDDSCARR":1.25}),("SCA_RR200",{"GoldDDMode":2,"GoldDDSCARR":2.0}),
 ("SCA_NOBOOST",{"GoldDDMode":2,"GoldDDSCAUseBoost":False}),
 ("SCA_TE12",{"GoldDDMode":2,"GoldDDSCATradeEnd":12}),("SCA_TE13",{"GoldDDMode":2,"GoldDDSCATradeEnd":13}),
 ("SCA_TE14",{"GoldDDMode":2,"GoldDDSCATradeEnd":14}),("SCA_FC17",{"GoldDDMode":2,"GoldDDSCAForceClose":17}),
 ("SCA_FC18",{"GoldDDMode":2,"GoldDDSCAForceClose":18}),("SCA_FC19",{"GoldDDMode":2,"GoldDDSCAForceClose":19}),
 ("PB_NOTUE",{"GoldDDMode":4,"GoldDDPBWeekMask":58}),("SCA_NOMON",{"GoldDDMode":4,"GoldDDSCAWeekMask":60}),
 ("MUTEX_ADX30_MAX08",{"GoldDDMode":3,"GoldDDPBADX":30.0,"GoldDDSCAMaxRange":.8}),
]

def terminal_running():
    q=subprocess.run(["tasklist","/FI","IMAGENAME eq terminal64.exe","/NH"],capture_output=True,text=True)
    return "terminal64.exe" in q.stdout.lower()

def metrics(path,deposit=100000.0):
    rows=list(csv.DictReader(path.open(encoding="utf-8-sig",newline="")))
    ps=[float(r["profit_jpy"]) for r in rows]; vols=sorted({float(r["volume"]) for r in rows if float(r["volume"])>0})
    win=sum(x for x in ps if x>0); loss=-sum(x for x in ps if x<0); bal=peak=deposit; dd=0
    for p in ps:
        bal+=p; peak=max(peak,bal); dd=max(dd,peak-bal)
    return {"net_jpy":sum(ps),"pf_jpy":win/loss if loss else math.inf,"dd_jpy":dd/1000,
            "dd_amount_jpy":dd,"deal_rows":len(rows),"effective_lots":"|".join(f"{x:.2f}" for x in vols)}

def save(rows):
    fields=sorted({k for r in rows for k in r})
    with OUT.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def run_one(window,ident,params):
    run=f"gdd_{window.lower()}_{ident.lower()}"; cfg=copy.deepcopy(BASE)
    cfg.update({"from_date":"2021.06.21" if window=="IS" else "2016.06.21",
                "to_date":"2026.06.20" if window=="IS" else "2021.06.20","report_name":run})
    cfg["parameters"].update(params); cfg["parameters"].update({"ResultFileName":run+"_result.csv","EquityLogFile":run+"_deals.csv"})
    cp=CFG/(run+".yaml"); cp.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
    deal_common=COMMON/(run+"_deals.csv"); deal_local=DEALS/(run+"_deals.csv")
    if deal_common.exists(): deal_common.unlink()
    q=subprocess.run([str(EXE),"run",str(cp),"--no-charts","--no-html"],cwd=REPO,capture_output=True,text=True,timeout=2400)
    (LOG/(run+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}",encoding="utf-8")
    if not deal_common.exists(): return {"window":window,"id":ident,"status":"FAILED","returncode":q.returncode}
    deal_local.write_bytes(deal_common.read_bytes())
    return {"window":window,"id":ident,"status":"OK","returncode":q.returncode,**metrics(deal_local)}

def main():
    for p in (CFG,LOG,DEALS): p.mkdir(parents=True,exist_ok=True)
    rows=[]
    for window in ("IS","OOS"):
        for ident,params in CASES:
            while terminal_running():
                print("WAIT terminal64.exe",flush=True); time.sleep(15)
            r=run_one(window,ident,params); rows.append(r); save(rows); print(r,flush=True)

if __name__=="__main__": main()
