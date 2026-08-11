"""Round-3 interaction screen. MT5 invocations are deliberately sequential."""
from __future__ import annotations

import argparse, copy, csv, itertools, shutil, subprocess, time
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "ml" / "codex500"
WORK, LOGS, OUT = ROOT / "configs3", ROOT / "logs3", ROOT / "results3.csv"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}
FIELDS = ["id","family","priority","base","symbol","overrides","model","is_net","is_pf","is_dd","is_n",
          "oos_net","oos_pf","oos_dd","oos_n","verdict","strict","note"]
C=[]
def add(fam, tag, base, ov, priority, model=None):
    C.append(dict(id=f"R3F{fam:02d}_{tag}",family=f"R3F{fam:02d}",priority=priority,base=base,
                  overrides=ov,model=model,note=""))
def grid(fam, base, axes, priority, fixed=None, model=None):
    for vals in itertools.product(*(v for _,v in axes)):
        ov={**(fixed or {}),**dict(zip((k for k,_ in axes),vals))}
        tag="_".join(f"{k}-{str(v).lower()}" for k,v in ov.items())
        add(fam,tag.replace(".","p"),base,ov,priority,model)

PB="configs/pullback_gbpjpy_h4.yaml"; RSI="configs/rsi_robust_gbpusd_h4.yaml"
SCA="configs/sca_gbpjpy_m15.yaml"; CARRY="configs/carry_audjpy_d1.yaml"; PAIR="configs/pairtrade_eurusd_gbpusd.yaml"

# Each 16-point family is an interaction surface on top of all currently adopted values.
grid(1,PB,[("MA_Slope_Min_ATR",[1.25,1.5,1.75,2.0]),("ADX_Threshold",[18.0,20.0,22.5,25.0])],1)
grid(2,PB,[("ATR_SL_Mult",[1.5,1.75,2.0,2.25]),("RR_Ratio",[3.5,4.0,4.5,5.0])],2)
grid(3,PB,[("ADX_Threshold",[18.0,20.0,22.5,25.0]),("MA_Slope_Lookback",[12,16,20,24])],5)
for q,m,b,h in itertools.product([False,True],repeat=4):
    add(4,f"q{int(q)}_m{int(m)}_b{int(b)}_h{int(h)}",PB,{"UsePullbackQuality":q,"UseMomentumConfirm":m,"RequireBullishCandle":b,"UseHigherTFFilter":h},11)
grid(5,PB,[("BE_Trigger_R",[0.75,1.0,1.25,1.5]),("Trail_Mult_ATR",[2.0,2.5,3.0,3.5])],10,
     {"UseBreakevenR":True,"UseATRTrail":True})
grid(6,RSI,[("BB_Deviation",[1.75,2.0,2.25,2.5]),("Range_Slope_Max_ATR",[0.15,0.2,0.25,0.3])],3)
for ext,(sl,tp) in itertools.product([72.5,75.0,77.5,80.0],[(40,90),(50,110),(60,130),(70,150)]):
    add(7,f"ext{ext:g}_sl{sl}_tp{tp}",RSI,{"RSI_OverboughtExtreme":ext,"RSI_Overbought":ext-2.5,
        "RSI_OversoldExtreme":100-ext,"RSI_Oversold":102.5-ext,"StopLoss_Pips":sl,"TakeProfit_Pips":tp},8)
grid(8,RSI,[("MaxHoldBars",[12,24,36,48]),("BE_Trigger_ATR",[0.75,1.0,1.25,1.5])],12,
     {"UseBreakevenATR":True})
grid(9,SCA,[("Boost_Mult",[4.0,4.5,5.0,6.0]),("RR_Ratio",[1.5,1.75,2.0,2.25])],4,model="every_tick")
for boost,mode,mult in itertools.product([4.0,4.5,5.0,6.0],[0,1],[0.4,0.6]):
    add(10,f"boost{boost:g}_mode{mode}_sl{mult:g}",SCA,{"Boost_Mult":boost,"SL_Mode":mode,"SL_ATRd_Mult":mult},6,"every_tick")
grid(11,SCA,[("Boost_Mult",[4.0,4.5,5.0,6.0]),("MaxRange_ATRd",[0.75,1.0,1.25,1.5])],7,model="every_tick")
grid(12,SCA,[("Boost_Mult",[4.0,4.5,5.0,6.0]),("Break_Buffer_ATRd",[0.0,0.01,0.02,0.04])],9,model="every_tick")
grid(13,CARRY,[("Hyst_ATR_Mult",[0.5,0.75,1.0,1.25]),("ExitMA_Period",[20,40,60,80])],13)
grid(14,PAIR,[("Entry_Z",[3.5,4.0,4.5,5.0]),("Exit_Z",[-1.5,-1.0,-0.5,0.0])],14)
for fast,slow in [(22,55),(25,55),(25,60),(28,65)]:
    for rr in [3.5,4.0,4.5,5.0]: add(15,f"ema{fast}-{slow}_rr{rr:g}",PB,{"FastEMA_Period":fast,"SlowEMA_Period":slow,"RR_Ratio":rr},15)

def mt5bt():
    x=shutil.which("mt5bt") or str(Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"))
    if not Path(x).exists(): raise FileNotFoundError("mt5bt not found")
    return x
def load(rel):
    with (REPO/rel).open(encoding="utf-8") as f:return yaml.safe_load(f)
def name(c,w): return ("codex5003_"+c["id"]+"_"+w).replace("-","m")
def build(c,w):
    cfg=copy.deepcopy(load(c["base"])); cfg["parameters"].update(c["overrides"]); n=name(c,w)
    cfg["parameters"]["ResultFileName"]=n+"_r.csv"; cfg["from_date"],cfg["to_date"]=WINDOWS[w]
    if c["model"]:cfg["model"]=c["model"]
    cfg["report_dir"]="results";cfg["report_name"]=n;WORK.mkdir(parents=True,exist_ok=True);p=WORK/(n+".yaml")
    with p.open("w",encoding="utf-8",newline="") as f:yaml.safe_dump(cfg,f,allow_unicode=True,sort_keys=False)
    return p
def summary(n):
    p=REPO/"results"/n/"summary.csv"
    if not p.exists():return None
    with p.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.reader(f))
    data={r[0]:r[1] for r in rows if len(r)>1}
    def key(k,cast=float):
        try:return cast(float(data[k]))
        except (KeyError,ValueError):return None
    vals=dict(net=key("純利益"),pf=key("プロフィットファクター"),dd=key("最大相対DD%"),n=key("総取引数",int))
    return None if None in vals.values() else vals
def run(c,w):
    n=name(c,w); old=summary(n)
    if old:return old
    p=build(c,w);LOGS.mkdir(parents=True,exist_ok=True)
    try:
        q=subprocess.run([mt5bt(),"run",str(p)],cwd=REPO,capture_output=True,text=True,timeout=1800)
        (LOGS/(n+".log")).write_text(f"returncode={q.returncode}\n--- stdout ---\n{q.stdout}\n--- stderr ---\n{q.stderr}",encoding="utf-8")
    except subprocess.TimeoutExpired as e:(LOGS/(n+".log")).write_text("TIMEOUT\n"+str(e),encoding="utf-8")
    return summary(n)
def rows_read():
    if not OUT.exists():return []
    with OUT.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def rows_write(rows):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,FIELDS);w.writeheader();w.writerows({k:r.get(k,"") for k in FIELDS} for r in rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--family",action="append");ap.add_argument("--limit",type=int);ap.add_argument("--list",action="store_true");a=ap.parse_args()
    selected=sorted((c for c in C if not a.family or c["family"] in a.family),key=lambda x:(x["priority"],x["id"]))
    if a.limit:selected=selected[:a.limit]
    if a.list:
        from collections import Counter;print(len(C),Counter(c["family"] for c in C));return
    rows=rows_read();done={r["id"] for r in rows if r.get("verdict") != "UNVERIFIABLE"};t=time.time()
    for i,c in enumerate(selected,1):
        if c["id"] in done:continue
        base=load(c["base"]);c["symbol"]=base["symbol"];ir=run(c,"IS");orr=run(c,"OOS")
        row={**c,"overrides":repr(c["overrides"]),"model":c["model"] or base.get("model","")}
        for px,r in (("is",ir),("oos",orr)):
            if r:
                for k,v in r.items():row[f"{px}_{k}"]=v
        row["verdict"]="UNVERIFIABLE" if not ir or not orr else ("PASS" if ir["net"]>0 and orr["net"]>0 else "reject")
        rows=[r for r in rows if r.get("id") != c["id"]];rows.append(row);rows_write(rows);print(f"[{i}/{len(selected)}] {c['id']} {row['verdict']}",flush=True)
    print(f"done {(time.time()-t)/60:.1f} min -> {OUT}")
if __name__=="__main__":main()
