"""Round 6 crypto cause/exit sweep. MT5 launches are strictly sequential."""
from __future__ import annotations
import copy, csv, subprocess, time
from pathlib import Path
import yaml
from ml.round6_phase2.run_gold_usd import BASE, REPO, ROOT, CFG, LOG, EXE

OUT=ROOT/"crypto_results.csv"
CAUSE=[(f"CAUSE_L{lb}_C{cd}_D{drop}",1,lb,cd,drop,10.0)
       for lb in (1,2,3,5,8) for cd in (1,3) for drop in (3.0,5.0,7.5,10.0)]
# Tick tests are expensive (~3.5 min/window on this terminal). Test the six most
# protective points first; the remaining 33 integer thresholds stay explicitly untested.
EXIT=[(f"EXIT_D{p}",2,1,1,5.0,float(p)) for p in range(2,8)]

def summary(run):
    p=REPO/"results"/run/"summary.csv"
    if not p.exists(): return None
    with p.open(encoding="utf-8-sig",newline="") as f: d={r[0]:r[1] for r in csv.reader(f) if len(r)>1}
    try: return {"net":float(d["純利益"]),"pf":float(d["プロフィットファクター"]),
                 "dd":float(d["最大相対DD%"]),"trades":int(float(d["総取引数"]))}
    except (KeyError,ValueError): return None

def config(period,item,model):
    ident,mode,lb,cd,drop,adverse=item
    run=f"r6p2_crypto_{period.lower()}_{ident.lower().replace('.','p')}_{'tick' if model=='every_tick' else 'open'}"
    x=copy.deepcopy(BASE); x.update({"currency":"JPY","deposit":100000,"symbol":"BTCUSD","period":"D1",
        "from_date":"2021.06.21" if period=="IS" else "2016.06.21",
        "to_date":"2026.06.20" if period=="IS" else "2021.06.20","report_name":run,"model":model})
    x["parameters"].update({"En_PB_GOLD":False,"En_ETH":True,"En_BTC_FUND":True,"En_BFXREV":True,
        "R6CryptoMode":mode,"R6CryptoLookbackDays":lb,"R6CryptoCooldownDays":cd,
        "R6CryptoShockPct":drop,"R6CryptoAdversePct":adverse,
        "ResultFileName":run+"_result.csv","EquityLogFile":run+"_deals.csv"})
    return run,x

def load_rows():
    return list(csv.DictReader(OUT.open(encoding="utf-8",newline=""))) if OUT.exists() else []

def save(rows):
    with OUT.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["period","id","family","model","status","net","pf","dd","trades"])
        w.writeheader();w.writerows(rows)

def sweep(family):
    CFG.mkdir(parents=True,exist_ok=True);LOG.mkdir(parents=True,exist_ok=True)
    cases=CAUSE if family=="crypto_cause" else EXIT
    model="open_prices" if family=="crypto_cause" else "every_tick"
    rows=load_rows(); done={(r["period"],r["id"],r["model"]) for r in rows}
    for period in ("IS","OOS"):
      for item in [("OFF",0,1,1,5.0,10.0),*cases]:
        run,x=config(period,item,model); key=(period,item[0],model)
        if key in done: continue
        cp=CFG/(run+".yaml");cp.write_text(yaml.safe_dump(x,sort_keys=False),encoding="utf-8")
        s=summary(run)
        if s is None:
          q=subprocess.run([str(EXE),"run",str(cp),"--no-charts","--no-html"],cwd=REPO,
                           capture_output=True,text=True,timeout=1800)
          (LOG/(run+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}",encoding="utf-8")
          s=summary(run)
        row={"period":period,"id":item[0],"family":family if item[0]!="OFF" else "baseline",
             "model":model,"status":"OK" if s else "FAILED",**(s or {})}
        rows.append(row);save(rows);print(row,flush=True)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("family",choices=("crypto_cause","crypto_exit"));a=ap.parse_args()
    sweep(a.family)
