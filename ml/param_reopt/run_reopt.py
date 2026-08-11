"""Exhaustive production-parameter re-optimization (MT5 calls are sequential)."""
from __future__ import annotations

import ast, copy, csv, itertools, shutil, subprocess, time
from collections import Counter
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "ml" / "param_reopt"
CFG, LOG, OUT = ROOT / "configs", ROOT / "logs", ROOT / "results.csv"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
FIELDS = ["id","sleeve","ea","symbol","base","parameter","value","overrides","model",
          "is_net","is_pf","is_dd","is_n","oos_net","oos_pf","oos_dd","oos_n",
          "survives","strict","tradeoff","status","note"]
C=[]

def add(sleeve, base, parameter, value, overrides=None, note=""):
    ov = overrides or {parameter:value}
    val = str(value).replace("-","m").replace(".","p").replace(" ","")
    C.append({"id":f"{sleeve}__{parameter}__{val}","sleeve":sleeve,"base":base,
              "parameter":parameter,"value":value,"overrides":ov,"note":note})

def axis(sleeve, base, p, values, fixed=None, note=""):
    for v in values: add(sleeve,base,p,v,{**(fixed or {}),p:v},note)

# Deliberately one-axis first.  Values already covered in codex500 are omitted where practical.
pbs={"PB_USDJPY":"configs/pullback_usdjpy_h4.yaml","PB_GBPJPY":"configs/pullback_gbpjpy_h4.yaml",
     "PB_AUDJPY":"configs/pullback_audjpy_h4.yaml","PB_GOLD":"configs/pullback_gold_h4.yaml"}
for s,b in pbs.items():
    axis(s,b,"TrendMA_Period",[100,150,250,300])
    axis(s,b,"FastEMA_Period",[10,15,25,30,35])
    axis(s,b,"SlowEMA_Period",[35,40,60,75,100])
    axis(s,b,"ADX_Period",[7,10,20,28])
    axis(s,b,"ADX_Threshold",[15.0,20.0,27.5,30.0])
    axis(s,b,"ATR_Period",[7,10,20,28])
    axis(s,b,"ATR_SL_Mult",[1.0,2.0,2.5,3.0])
    axis(s,b,"RR_Ratio",[1.0,2.5,3.0,5.0])
    if s != "PB_GBPJPY": axis(s,b,"MA_Slope_Lookback",[10,30,40],note="effective only when trend-strength is enabled")

rsis={"RSI_EURUSD":"configs/rsi_robust_eurusd_h1.yaml","RSI_USDJPY":"configs/rsi_robust_usdjpy_h4.yaml",
      "RSI_GBPUSD":"configs/rsi_robust_gbpusd_h4.yaml"}
for s,b in rsis.items():
    axis(s,b,"MA_Period",[100,150,250,300])
    axis(s,b,"BB_Period",[10,15,25,35,40])
    axis(s,b,"BB_Deviation",[1.5,1.75,2.25,2.75,3.0])
    axis(s,b,"RSI_Period",[5,7,10,21,28])
    for x in [65.0,70.0,80.0,85.0]:
        add(s,b,"RSI_levels",x,{"RSI_OverboughtExtreme":x,"RSI_Overbought":x-2.5,
            "RSI_OversoldExtreme":100-x,"RSI_Oversold":102.5-x})
    axis(s,b,"StopLoss_Pips",[25,40,60,75,100])
    axis(s,b,"TakeProfit_Pips",[50,75,125,150,200])
    axis(s,b,"Swing_Lookback",[1,2,4,5,7])
    axis(s,b,"DP_Pattern_Bars",[20,40,80,100,120])
    axis(s,b,"DP_Tolerance_ATR",[0.25,0.5,0.75,1.5,2.0])

scas={"SCA_USDJPY":"configs/sca_usdjpy_m15.yaml","SCA_GBPJPY":"configs/sca_gbpjpy_m15.yaml",
      "SCA_GOLD":"configs/sca_gold_m15.yaml"}
for s,b in scas.items():
    axis(s,b,"RangeStartHour",[1,2,3])
    axis(s,b,"RangeEndHour",[7,8,10,11])
    axis(s,b,"TradeEndHour",[10,12,14,16,18])
    axis(s,b,"ForceCloseHour",[18,20,21,23])
    axis(s,b,"MinRange_ATRd",[0.1,0.2,0.3,0.5,0.6])
    axis(s,b,"MaxRange_ATRd",[0.6,0.8,1.2,1.5])
    axis(s,b,"Break_Buffer_ATRd",[0.01,0.025,0.075,0.1])
    axis(s,b,"RR_Ratio",[1.0,1.25,1.75,2.5,3.0])
    axis(s,b,"D1Trend_MA",[100,150,250,300],{"UseD1TrendFilter":True},"includes enabling the target-specific D1 filter")

axis("CARRY_AUDJPY","configs/carry_audjpy_d1.yaml","TrendMA_Method",[1,2,3],note="ENUM: EMA/SMMA/LWMA")
axis("CARRY_AUDJPY","configs/carry_audjpy_d1.yaml","RequirePositiveSwap",[False])
axis("CARRY_AUDJPY","configs/carry_audjpy_d1.yaml","ExitMA_Period",[10,30,50,100])
axis("CARRY_AUDJPY","configs/carry_audjpy_d1.yaml","ReentryCooldown",[1,3,7,10])

axis("PAIR_EURGBP","configs/pairtrade_eurusd_gbpusd.yaml","Lookback",[50,75,125,150,250,300,400])
axis("PAIR_EURGBP","configs/pairtrade_eurusd_gbpusd.yaml","Entry_Z",[2.5,3.0,3.5,4.5,5.0])
axis("PAIR_EURGBP","configs/pairtrade_eurusd_gbpusd.yaml","Exit_Z",[-2.0,-1.5,-0.5,0.0,0.5])
axis("PAIR_EURGBP","configs/pairtrade_eurusd_gbpusd.yaml","Stop_Z",[4.25,4.5,4.75,5.5,6.0,7.0])

axis("BFX_BTC","configs/bfxrev_btcusd_d1.yaml","DropPct",[5,7.5,12.5,15,20,25])
axis("BFX_BTC","configs/bfxrev_btcusd_d1.yaml","LookbackDays",[1,2,3,7,10,14,20])
axis("BFX_BTC","configs/bfxrev_btcusd_d1.yaml","HoldDays",[2,3,5,7,14,20,30])
axis("FUNDING_BTC","configs/fundingrev_btcusd_d1.yaml","Threshold_Pct8h",[-.001,-.002,-.003,-.005,-.006,-.008,-.01])
axis("FUNDING_BTC","configs/fundingrev_btcusd_d1.yaml","MaxHoldDays",[3,5,7,10,14,30,40])
axis("ETH_ETHUSD","configs/eth_ea_d1.yaml","TrendMA_Period",[100,125,150,175,225,250,300])
axis("ETH_ETHUSD","configs/eth_ea_d1.yaml","ExitMA_Period",[10,20,30,50,60,80,100])
axis("ETH_ETHUSD","configs/eth_ea_d1.yaml","ReentryCooldown",[0,1,3,7,10,14])
axis("ETH_ETHUSD","configs/eth_ea_d1.yaml","MA_Method",[1,2,3],note="ENUM: EMA/SMMA/LWMA")

# Stage 2: local two-axis refinement around the four strict winners from stage 1.
for a,b in itertools.product([28.0,30.0,32.0],[7,10,14,20]):
    add("PB_GBPJPY","configs/pullback_gbpjpy_h4.yaml","ADX_Threshold_x_ADX_Period",f"{a}/{b}",
        {"ADX_Threshold":a,"ADX_Period":b},"stage-2 refinement")
for a,b in itertools.product([20,25,30],[75,105,125]):
    add("RSI_EURUSD","configs/rsi_robust_eurusd_h1.yaml","StopLoss_x_TakeProfit",f"{a}/{b}",
        {"StopLoss_Pips":a,"TakeProfit_Pips":b},"stage-2 refinement")
for a,b in itertools.product([0.075,0.1,0.125],[0.3,0.4,0.5]):
    add("SCA_USDJPY","configs/sca_usdjpy_m15.yaml","Buffer_x_MinRange",f"{a}/{b}",
        {"Break_Buffer_ATRd":a,"MinRange_ATRd":b},"stage-2 refinement")
for a,b in itertools.product([125,150,175],[30,40,50]):
    add("ETH_ETHUSD","configs/eth_ea_d1.yaml","TrendMA_x_ExitMA",f"{a}/{b}",
        {"TrendMA_Period":a,"ExitMA_Period":b},"stage-2 refinement")

def load(rel):
    with (REPO/rel).open(encoding="utf-8") as f:return yaml.safe_load(f)
def exe():
    p=shutil.which("mt5bt") or r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
    if not Path(p).exists():raise FileNotFoundError(p)
    return p
def run_name(c,w): return ("preopt_"+c["id"]+"_"+w).replace("/","_")
def build(c,w):
    x=copy.deepcopy(load(c["base"])); x["parameters"].update(c["overrides"])
    n=run_name(c,w);x["from_date"],x["to_date"]=WINDOWS[w]
    # Source-history limits take precedence where the configured start is later.
    if c["sleeve"]=="BFX_BTC" and w=="OOS":x["from_date"]="2016.12.01"
    if c["sleeve"]=="FUNDING_BTC" and w=="OOS":x["from_date"]="2019.09.01"
    if c["sleeve"]=="ETH_ETHUSD" and w=="OOS":x["from_date"]="2016.11.01"
    if c["sleeve"].startswith("SCA_"):x["model"]="every_tick"
    x["parameters"]["ResultFileName"]=n+"_r.csv";x["report_dir"]="results";x["report_name"]=n
    CFG.mkdir(parents=True,exist_ok=True);p=CFG/(n+".yaml")
    with p.open("w",encoding="utf-8",newline="") as f:yaml.safe_dump(x,f,allow_unicode=True,sort_keys=False)
    return p
def summary(n):
    p=REPO/"results"/n/"summary.csv"
    if not p.exists():return None
    with p.open(encoding="utf-8-sig",newline="") as f:d={r[0]:r[1] for r in csv.reader(f) if len(r)>1}
    try:return {"net":float(d["純利益"]),"pf":float(d["プロフィットファクター"]),
                "dd":float(d["最大相対DD%"]),"n":int(float(d["総取引数"]))}
    except (KeyError,ValueError):return None
def execute(c,w):
    n=run_name(c,w); old=summary(n)
    if old:return old
    p=build(c,w);LOG.mkdir(parents=True,exist_ok=True)
    try:q=subprocess.run([exe(),"run",str(p)],cwd=REPO,capture_output=True,text=True,timeout=1800)
    except subprocess.TimeoutExpired as e:
        (LOG/(n+".log")).write_text("TIMEOUT\n"+str(e),encoding="utf-8");return None
    (LOG/(n+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}",encoding="utf-8")
    return summary(n)
def read_rows():
    if not OUT.exists():return []
    with OUT.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write_rows(rows):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,FIELDS);w.writeheader();w.writerows({k:r.get(k,"") for k in FIELDS} for r in rows)
def baseline(sleeve,base):
    # GOLD OOS is a known data-availability failure; do not repeatedly launch MT5 for it on resume.
    return {w:(None if sleeve in {"PB_GOLD","SCA_GOLD"} and w=="OOS" else
               execute({"id":sleeve+"__BASE","sleeve":sleeve,"base":base,"overrides":{}},w)) for w in WINDOWS}
def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--list",action="store_true");ap.add_argument("--limit",type=int);a=ap.parse_args()
    if a.list:print(len(C),Counter(x["sleeve"] for x in C));return
    selected=C[:a.limit] if a.limit else C; rows=read_rows(); done={r["id"] for r in rows}
    bases={c["sleeve"]:c["base"] for c in C}; bl={s:baseline(s,b) for s,b in bases.items()};t=time.time()
    for i,c in enumerate(selected,1):
        if c["id"] in done:continue
        cfg=load(c["base"]); ir,orr=execute(c,"IS"),execute(c,"OOS")
        row={**c,"ea":cfg["expert"],"symbol":cfg["symbol"],"overrides":repr(c["overrides"]),"model":cfg["model"]}
        if ir and orr:
            for px,r in (("is",ir),("oos",orr)):
                for k,v in r.items():row[f"{px}_{k}"]=v
            bi,bo=bl[c["sleeve"]]["IS"],bl[c["sleeve"]]["OOS"]
            row["survives"] = ir["net"]>0 and orr["net"]>0
            row["strict"] = bool(row["survives"] and ir["net"]>bi["net"] and ir["pf"]>bi["pf"] and ir["dd"]<=bi["dd"] and orr["net"]>bo["net"] and orr["pf"]>bo["pf"] and orr["dd"]<=bo["dd"])
            gains=sum([ir["net"]>bi["net"],ir["pf"]>bi["pf"],ir["dd"]<=bi["dd"],orr["net"]>bo["net"],orr["pf"]>bo["pf"],orr["dd"]<=bo["dd"]])
            row["tradeoff"]=bool(row["survives"] and not row["strict"] and gains>=4);row["status"]="OK"
        else:row["status"]="UNVERIFIABLE"
        rows=[r for r in rows if r["id"]!=c["id"]]+[row];write_rows(rows)
        print(f"[{i}/{len(selected)}] {c['id']} {row['status']} strict={row.get('strict','')}",flush=True)
    print(f"done {len(selected)} candidates in {(time.time()-t)/60:.1f} min")
if __name__=="__main__":main()
