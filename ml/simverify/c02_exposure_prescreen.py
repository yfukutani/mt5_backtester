"""C02: position-ID付きdealからentry時点の通貨方向重複と後続損益を検定する。"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

OUT = Path(__file__).resolve().parent
SRC = OUT / "deals/c02_full_positions.csv"

MAGIC_SYMBOL = {
    20260622:"USDJPY", 20260627:"GBPJPY", 20260628:"AUDJPY", 20260640:"GOLD",
    20260610:"USDJPY", 20260605:"EURUSD", 20260774:"GBPUSD", 20260629:"EURUSD",
    20260650:"AUDJPY", 20260710:"ETHUSD", 20260720:"BTCUSD", 20260724:"BTCUSD",
    20261002:"GOLD", 20261000:"USDJPY", 20261001:"GBPJPY",
}

def vector(symbol: str, deal_type: int) -> dict[str,float]:
    sign = 1.0 if deal_type == 0 else -1.0  # BUY base+, quote-
    if symbol in {"GOLD","BTCUSD","ETHUSD"}:
        return {"USD": -sign}
    return {symbol[:3]: sign, symbol[3:6]: -sign}

def main() -> None:
    d = pd.read_csv(SRC).sort_values(["time","position_id","entry"]).reset_index(drop=True)
    d = d[d.magic.isin(MAGIC_SYMBOL)].copy()
    outcomes = d.groupby("position_id").profit.sum().to_dict()
    active: dict[int,dict[str,float]] = {}
    rows=[]
    for r in d.itertuples(index=False):
        pid=int(r.position_id); ent=int(r.entry)
        if ent == 0:
            v=vector(MAGIC_SYMBOL[int(r.magic)],int(r.type))
            agg={}
            for av in active.values():
                for c,x in av.items(): agg[c]=agg.get(c,0.0)+x
            overlap=sum(max(0.0, x*agg.get(c,0.0)) for c,x in v.items())
            concentration=max([abs(agg.get(c,0.0)+x) for c,x in v.items()] or [0.0])
            rows.append({"position_id":pid,"time":int(r.time),"magic":int(r.magic),
                         "symbol":MAGIC_SYMBOL[int(r.magic)],"overlap":overlap,
                         "concentration":concentration,"profit":float(outcomes.get(pid,0.0))})
            active[pid]=v
        else:
            active.pop(pid,None)
    x=pd.DataFrame(rows).drop_duplicates("position_id")
    # 10案 = overlap分布の50%～95%点を5%刻みでgate候補にする。
    results=[]
    for i,q in enumerate(np.arange(.50,1.00,.05),1):
        thr=float(x.overlap.quantile(q))
        hi=x.loc[x.overlap>thr,"profit"].to_numpy()
        lo=x.loc[x.overlap<=thr,"profit"].to_numpy()
        t,p=(np.nan,np.nan) if min(len(hi),len(lo))<2 else ttest_ind(hi,lo,equal_var=False,nan_policy="omit")
        results.append({"proposal_id":f"C02-{i:02d}","quantile":q,"threshold":thr,
                        "high_n":len(hi),"low_n":len(lo),"high_mean":np.mean(hi) if len(hi) else np.nan,
                        "low_mean":np.mean(lo) if len(lo) else np.nan,"t":float(t),"p":float(p),
                        "pass_abs_t_ge_2":bool(abs(t)>=2) if np.isfinite(t) else False})
    x.to_csv(OUT/"c02_position_features.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(results).to_csv(OUT/"c02_prescreen_results.csv",index=False,encoding="utf-8-sig")
    print(pd.DataFrame(results).to_string(index=False))

if __name__ == "__main__": main()
