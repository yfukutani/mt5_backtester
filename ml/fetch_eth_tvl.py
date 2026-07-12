# -*- coding: utf-8 -*-
"""ETHチェーンTVL履歴の取得（DefiLlama・無料/認証不要）→ ml/eth_tvl.csv"""
import csv
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent
url = "https://api.llama.fi/v2/historicalChainTvl/Ethereum"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
with urllib.request.urlopen(req, timeout=60) as r:
    data = json.loads(r.read().decode())
rows = [(int(d["date"]), float(d["tvl"])) for d in data if d.get("tvl")]
rows.sort()
with open(OUT / "eth_tvl.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["time", "tvl"])
    w.writerows(rows)
t0 = datetime.fromtimestamp(rows[0][0], timezone.utc)
t1 = datetime.fromtimestamp(rows[-1][0], timezone.utc)
print(f"{len(rows)}件 {t0.date()}..{t1.date()} 現在${rows[-1][1]/1e9:.1f}B -> eth_tvl.csv")
