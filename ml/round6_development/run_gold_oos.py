"""OOS confirmation for promising GOLD exit points; sequential MT5 only."""
from __future__ import annotations
import copy,csv,subprocess
from pathlib import Path
import yaml
from run_gold import REPO,ROOT,CFG,LOG,EXE,BASE,summary

POINTS=(.20,.25,.30,.35,.40)
OUT=ROOT/"gold_oos_results.csv"

def main():
 rows=[]
 for th in POINTS:
  run=f"r6gold_oos_exit_a{str(th).replace('.','p')}"
  x=copy.deepcopy(BASE);x.update({"from_date":"2016.06.21","to_date":"2021.06.20","report_name":run})
  x["parameters"].update({"R6GoldMode":2,"R6GoldAdverseATR":th,"ResultFileName":run+"_result.csv","EquityLogFile":run+"_deals.csv"})
  cp=CFG/(run+".yaml")
  with cp.open("w",encoding="utf-8",newline="") as f:yaml.safe_dump(x,f,sort_keys=False)
  s=summary(run)
  if s is None:
   q=subprocess.run([str(EXE),"run",str(cp),"--no-charts","--no-html"],cwd=REPO,capture_output=True,text=True,timeout=1800)
   (LOG/(run+".log")).write_text(f"returncode={q.returncode}\n{q.stdout}\n{q.stderr}",encoding="utf-8");s=summary(run)
  rows.append({"id":f"EXIT_A{th}","adverse_atr":th,"status":"UNVERIFIABLE_GOLD_OOS" if not s else "OK",**(s or {})})
  with OUT.open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
  print(rows[-1],flush=True)
if __name__=="__main__":main()
