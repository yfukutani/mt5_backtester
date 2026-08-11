# -*- coding: utf-8 -*-
"""Codex500 remaining-family IS/OOS screen (2026-08-10).

Runs mt5bt strictly sequentially, writes one row after every candidate, and is
safe to resume.  Production YAMLs are copied and only input parameters/dates,
result names, and (for SCA) the required model are changed.
"""
from __future__ import annotations

import argparse, ast, copy, csv, itertools, shutil, subprocess, time
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "ml" / "codex500"
WORK, LOGS, OUT = ROOT / "configs2", ROOT / "logs2", ROOT / "results2.csv"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
FIELDS = ["id","family","base","symbol","overrides","model","is_net","is_pf","is_dd","is_n",
          "oos_net","oos_pf","oos_dd","oos_n","verdict","note"]
C=[]
def add(fam, tag, base, overrides, model=None, oos=True):
    C.append(dict(id=f"F{fam}_{tag}",family=str(fam),base=base,overrides=overrides,
                  model=model,oos=oos,note=""))
def grid(fam, base, axes, prefix="", model=None, fixed=None, oos=True):
    fixed=fixed or {}
    for vals in itertools.product(*(v for _,v in axes)):
        ov={**fixed,**dict(zip((k for k,_ in axes),vals))}
        tag=prefix+"_".join(f"{k}-{str(v).lower()}" for k,v in ov.items())
        add(fam,tag,base,ov,model,oos)

PB_U="configs/pullback_usdjpy_h4.yaml"; PB_G="configs/pullback_gbpjpy_h4.yaml"
RS_E="configs/rsi_robust_eurusd_h1.yaml"; RS_U="configs/rsi_robust_usdjpy_h4.yaml"
SCA="configs/sca_gbpjpy_m15.yaml"; CARRY="configs/carry_audjpy_d1.yaml"; ETH="configs/eth_ea_d1.yaml"

# PB: each family is the requested 16-point design.  F7 is a balanced 16-run
# three-factor design (four ATR periods, with the four SL/RR pairs rotated).
grid(4,PB_U,[("FastEMA_Period",[15,15,20,20]),("SlowEMA_Period",[40,50,40,50])])
# Replace the accidental 16x duplication above with the explicitly requested 4 EMA pairs x 4 flag states.
C[:]=[]
for fast,slow in [(15,40),(15,50),(20,40),(20,50)]:
  for q,m in [(True,False),(False,True),(True,True),(False,False)]:
    add(4,f"ema{fast}-{slow}_q{int(q)}m{int(m)}",PB_U,{"FastEMA_Period":fast,"SlowEMA_Period":slow,"UsePullbackQuality":q,"UseMomentumConfirm":m})
for ma in [160,180,200,220]:
  for fast,slow in [(15,40),(20,40),(20,50),(25,60)]: add(5,f"ma{ma}_ema{fast}-{slow}",PB_G,{"TrendMA_Period":ma,"FastEMA_Period":fast,"SlowEMA_Period":slow})
grid(6,PB_U,[("ADX_Period",[10,12,14,18]),("MA_Slope_Lookback",[12,16,20,28])])
slrr=[(1.5,2.0),(1.5,3.0),(2.0,2.0),(2.0,3.0)]
for ai,atr in enumerate([10,14,20,28]):
  for j,(sl,rr) in enumerate(slrr): add(7,f"atr{atr}_sl{sl:g}_rr{rr:g}",PB_U,{"ATR_Period":atr,"ATR_SL_Mult":sl,"RR_Ratio":rr})
for be,trail,hold in [(False,False,0),(True,False,0),(False,True,0),(True,True,0),
                      (False,False,20),(True,False,20),(False,True,20),(True,True,20),
                      (False,False,40),(True,False,40),(False,True,40),(True,True,40),
                      (True,False,60),(False,True,60),(True,True,60),(False,False,60)]:
  add(8,f"be{int(be)}_tr{int(trail)}_h{hold}",PB_G,{"UseBreakevenR":be,"BE_Trigger_R":1.0,"UseATRTrail":trail,"Trail_Mult_ATR":3.0,"MaxHoldBars":hold})
grid(9,PB_G,[("StructureLookback",[20,30,40,60]),("StructureMinRR",[1.5,2.0,2.5,3.0])],fixed={"UseStructureTP":True})

# RSI
for base,pfx in [(RS_E,"eu_"),(RS_U,"uj_")]: grid(10,base,[("RSI_Period",[10,12,14,18]),("BB_Period",[16,20,24,30])],prefix=pfx)
for ext,ret in itertools.product([72.5,75,77.5,80],[2.5,5,7.5,10]):
  add(11,f"ext{ext:g}_ret{ret:g}",RS_E,{"RSI_OverboughtExtreme":ext,"RSI_Overbought":ext-ret,"RSI_OversoldExtreme":100-ext,"RSI_Oversold":100-ext+ret})
grid(12,RS_E,[("Range_Slope_Lookback",[10,20,30,40]),("BB_Deviation",[2.0,2.25,2.5,3.0])])
fixed_points={RS_E:[(30,75),(35,80),(40,90),(45,105),(50,110),(55,120),(60,135),(70,150)],
              RS_U:[(35,80),(40,90),(45,100),(50,110),(55,120),(60,135),(70,150),(80,170)]}
for base,pts in fixed_points.items():
  pfx="eu" if base==RS_E else "uj"
  for sl,tp in pts: add(13,f"{pfx}_sl{sl}_tp{tp}",base,{"UseATRStopLoss":False,"StopLoss_Pips":sl,"TakeProfit_Pips":tp})
grid(14,RS_U,[("Swing_Lookback",[2,3,4,5]),("DP_Pattern_Bars",[40,60,80,100])],fixed={"UseDoublePattern":True,"DP_Tolerance_ATR":0.5})
grid(15,RS_E,[("ATR_SL_Multiplier",[1.0,1.5,2.0,2.5]),("ATR_RR_Ratio",[1.5,2.0,2.5,3.0])],fixed={"UseATRStopLoss":True})
for hold,be in itertools.product([0,12,24,48],[0,0.75,1.0,1.5]):
  add(16,f"hold{hold}_be{be:g}",RS_U,{"MaxHoldBars":hold,"UseBreakevenATR":be>0,"BE_Trigger_ATR":be if be else 1.0})

# SCA (all every_tick)
for start,end in [(0,8),(0,9),(1,8),(1,9)]:
  for mn in [.20,.25,.30,.35]: add(17,f"win{start}-{end}_min{mn:g}",SCA,{"RangeStartHour":start,"RangeEndHour":end,"MinRange_ATRd":mn},"every_tick")
grid(18,SCA,[("MaxRange_ATRd",[.75,1.0,1.25,1.5]),("TradeEndHour",[11,12,13,15])],model="every_tick")
grid(19,SCA,[("Break_Buffer_ATRd",[0,.01,.02,.04]),("RangeMode",[0,1,2,3])],model="every_tick")
for boost,mode in itertools.product([1.5,2,3,4],[0,1]):
  for slm in ([.4,.6] if mode==1 else [.5,1.0]): add(21,f"boost{boost:g}_mode{mode}_sl{slm:g}",SCA,{"UseReversalBoost":True,"Boost_Mult":boost,"SL_Mode":mode,"SL_ATRd_Mult":slm},"every_tick")
for wick,buf,opp in itertools.product([False,True],[0,.02],[False,True]):
  for decay in [0,.005]: add(22,f"wick{int(wick)}_buf{buf:g}_opp{int(opp)}_dec{decay:g}",SCA,{"BreakOnWick":wick,"Break_Buffer_ATRd":buf,"RequireOppTouch":opp,"Buf_DecayPerHour":decay},"every_tick")

grid(24,CARRY,[("ExitMA_Period",[20,40,60,80]),("ReentryCooldown",[0,3,5,10])])
eth_points=[(180,30,3),(180,40,5),(180,50,7),(180,60,10),(200,30,3),(200,40,5),(200,50,7),(200,60,10),(220,30,3),(220,40,5),(220,50,7),(220,60,10),(240,30,3),(240,40,5),(240,50,7),(240,60,10)]
for ent,ex,cd in eth_points: add(29,f"entry{ent}_exit{ex}_cd{cd}",ETH,{"TrendMA_Period":ent,"ExitMA_Period":ex,"ReentryCooldown":cd})

def mt5bt():
    x=shutil.which("mt5bt")
    if not x:
        fallback=Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
        x=str(fallback) if fallback.exists() else None
    if not x: raise FileNotFoundError("mt5bt not found on PATH or known fallback")
    return x
def load(rel):
    with (REPO/rel).open(encoding="utf-8") as f:return yaml.safe_load(f)
def name(c,w): return "codex5002_"+c["id"].replace(".","p")+"_"+w
def build(c,w):
    cfg=copy.deepcopy(load(c["base"])); cfg["parameters"].update(c["overrides"])
    n=name(c,w); cfg["parameters"]["ResultFileName"]=n+"_r.csv"
    cfg["from_date"],cfg["to_date"]=WINDOWS[w]
    if c["model"]: cfg["model"]=c["model"]
    cfg["report_dir"]="results"; cfg["report_name"]=n
    WORK.mkdir(parents=True,exist_ok=True); p=WORK/(n+".yaml")
    with p.open("w",encoding="utf-8",newline="") as f: yaml.safe_dump(cfg,f,allow_unicode=True,sort_keys=False)
    return p
def summary(n):
    p=REPO/"results"/n/"summary.csv"
    if not p.exists(): return None
    with p.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.reader(f))
    vals={r[0]:r[1] for r in rows if len(r)>1}
    def pick(words,idx,cast=float):
        for k,v in vals.items():
            if any(x in k for x in words):
                try:return cast(float(v))
                except ValueError:pass
        try:return cast(float(rows[idx][1]))
        except (IndexError,ValueError):return None
    net=pick(["純利益"],1); pf=pick(["プロフィットファクター"],2); dd=pick(["最大相対DD"],4); ntr=pick(["総取引数"],8,int)
    return None if None in (net,pf,dd,ntr) else dict(net=net,pf=pf,dd=dd,n=ntr)
def run(c,w):
    n=name(c,w); old=summary(n)
    if old:return old
    p=build(c,w); LOGS.mkdir(parents=True,exist_ok=True)
    try:
        q=subprocess.run([mt5bt(),"run",str(p)],cwd=REPO,capture_output=True,text=True,timeout=1800)
        (LOGS/(n+".log")).write_text(f"returncode={q.returncode}\n--- stdout ---\n{q.stdout}\n--- stderr ---\n{q.stderr}",encoding="utf-8")
    except subprocess.TimeoutExpired as e: (LOGS/(n+".log")).write_text("TIMEOUT\n"+str(e),encoding="utf-8")
    return summary(n)
def readrows():
    if not OUT.exists():return []
    with OUT.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def writerows(rows):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,FIELDS);w.writeheader();w.writerows({k:r.get(k,"") for k in FIELDS} for r in rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--family",action="append");ap.add_argument("--limit",type=int);ap.add_argument("--list",action="store_true");a=ap.parse_args()
    selected=[c for c in C if not a.family or c["family"] in a.family]
    if a.limit:selected=selected[:a.limit]
    if a.list:
        from collections import Counter;print(Counter(x["family"] for x in selected));return
    rows=readrows();done={r["id"] for r in rows};t=time.time()
    for i,c in enumerate(selected,1):
        if c["id"] in done: print(f"[{i}/{len(selected)}] {c['id']} cached",flush=True);continue
        base=load(c["base"]); c["symbol"]=base["symbol"]
        ir=run(c,"IS"); orr=run(c,"OOS") if c["oos"] else None
        row={**c,"overrides":repr(c["overrides"]),"model":c["model"] or base.get("model","")}
        for px,r in [("is",ir),("oos",orr)]:
            if r:
                for k,v in r.items():row[f"{px}_{k}"]=v
        row["verdict"]="UNVERIFIABLE" if not ir or (c["oos"] and not orr) else ("PASS" if ir["net"]>0 and (not c["oos"] or orr["net"]>0) else "reject")
        rows.append(row);writerows(rows)
        print(f"[{i}/{len(selected)}] {c['id']} IS={ir and ir['net']} OOS={orr and orr['net']} {row['verdict']}",flush=True)
    print(f"done {(time.time()-t)/60:.1f} min -> {OUT}")
if __name__=="__main__":main()
