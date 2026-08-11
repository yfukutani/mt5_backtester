"""Classify round-3 rows against the exact current-production baseline."""
import csv
from pathlib import Path

p=Path(__file__).resolve().parent/"codex500"/"results3.csv"
with p.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f)); fields=list(rows[0])
def row(cid): return next(x for x in rows if x["id"]==cid)
pb=row("R3F02_ATR_SL_Mult-2p0_RR_Ratio-4p0")
rsi=row("R3F06_BB_Deviation-2p0_Range_Slope_Max_ATR-0p2")
sca=row("R3F09_Boost_Mult-4p0_RR_Ratio-2p0")
pair=row("R3F14_Entry_Z-4p0_Exit_Z--1p0")
carry={"is_net":"105817","is_pf":"3.5057","is_dd":"28.536","oos_net":"33912","oos_pf":"2.1952","oos_dd":"23.8033"}
for x in rows:
    n=int(x["family"][-2:])
    b=pb if n in (1,2,3,4,5,15) else rsi if n in (6,7,8) else sca if n in (9,10,11,12) else carry if n==13 else pair
    better=all(float(x[k])>float(b[k]) for k in ("is_net","is_pf","oos_net","oos_pf"))
    dd=all(float(x[k])<=float(b[k]) for k in ("is_dd","oos_dd"))
    x["strict"]="IMPROVEMENT" if better and dd else "TRADEOFF" if better else "NO_IMPROVEMENT"
    if x["strict"]=="TRADEOFF": x["note"]="IS/OOS net+PF improve, but DD worsens in at least one window"
with p.open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
