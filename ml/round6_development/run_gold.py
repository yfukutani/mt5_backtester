"""Round 6 GOLD cause/exit sweep. MT5 launches are strictly sequential."""
from __future__ import annotations

import copy, csv, shutil, subprocess, time
from pathlib import Path
import yaml

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/"ml"/"round6_development"; CFG=ROOT/"configs"; LOG=ROOT/"logs"
OUT=ROOT/"gold_results.csv"; EXE=REPO/"mt5bt.bat"

BASE={
 "mt5_path":r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe",
 "expert":"MIX_EA_SIMVERIFY","symbol":"GOLD","period":"H4",
 "from_date":"2021.06.21","to_date":"2026.06.20","deposit":100000,
 "currency":"JPY","leverage":25,"model":"open_prices",
 "parameters":{
  "En_PB_USDJPY":False,"En_PB_GBPJPY":False,"En_PB_AUDJPY":False,"En_PB_GOLD":True,
  "En_RSI_USDJPY":False,"En_RSI_EURUSD":False,"En_RSI_GBPUSD":False,"En_PAIR":False,
  "En_CARRY":False,"En_VBO":False,"En_ETH":False,"En_BTC_FUND":False,"En_BFXREV":False,
  "En_SCA_GOLD":False,"En_SCA_USDJPY":False,"En_SCA_GBPJPY":False,
  "FundUseWebRequest":False,"BfxUseWebRequest":False,"SimVerifyMode":0,
 },"report_dir":"results"
}

CASES=[("OFF",0,1,1.5,1.0)]
for lb in (1,2,3,5,8):
 for th in (.75,1.0,1.25,1.5): CASES.append((f"CAUSE_L{lb}_T{th}",1,lb,th,1.0))
for i,th in enumerate((.20,.25,.30,.35,.40,.45,.50,.60,.70,.80,.90,1.0,1.1,1.2,1.3,1.4,1.5,1.75,2.0,2.5),1):
 CASES.append((f"EXIT_A{th}",2,1,1.5,th))

def summary(name):
 p=REPO/"results"/name/"summary.csv"
 if not p.exists(): return None
 with p.open(encoding="utf-8-sig",newline="") as f:d={r[0]:r[1] for r in csv.reader(f) if len(r)>1}
 try:return {"net":float(d["純利益"]),"pf":float(d["プロフィットファクター"]),
             "dd":float(d["最大相対DD%"]),"trades":int(float(d["総取引数"]))}
 except (KeyError,ValueError):return None

def main():
 CFG.mkdir(parents=True,exist_ok=True);LOG.mkdir(parents=True,exist_ok=True)
 rows=[];t=time.time()
 for n,mode,lb,shock,adv in CASES:
  run="r6gold_is_"+n.lower().replace(".","p")
  x=copy.deepcopy(BASE);x["report_name"]=run
  x["parameters"].update({"R6GoldMode":mode,"R6GoldLookbackBars":lb,
    "R6GoldShockATR":shock,"R6GoldAdverseATR":adv,"ResultFileName":run+"_result.csv",
    "EquityLogFile":run+"_deals.csv"})
  cp=CFG/(run+".yaml")
  with cp.open("w",encoding="utf-8",newline="") as f:yaml.safe_dump(x,f,sort_keys=False,allow_unicode=True)
  s=summary(run)
  if s is None:
   q=subprocess.run([str(EXE),"run",str(cp),"--no-charts","--no-html"],cwd=REPO,
                    capture_output=True,text=True,timeout=1800)
   (LOG/(run+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}",encoding="utf-8")
   s=summary(run)
  rows.append({"id":n,"family":"gold_cause" if mode==1 else ("gold_exit" if mode==2 else "baseline"),
               "mode":mode,"lookback":lb,"shock_atr":shock,"adverse_atr":adv,
               "status":"OK" if s else "FAILED",**(s or {})})
  with OUT.open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
  print(f"[{len(rows)}/{len(CASES)}] {n} {s}",flush=True)
 print(f"done {len(rows)} in {(time.time()-t)/60:.1f} min")

if __name__=="__main__":main()
