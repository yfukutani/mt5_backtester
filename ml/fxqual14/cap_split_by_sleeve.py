# -*- coding: utf-8 -*-
"""cap の cut/deny を枠別に割る。

⚠️ **Pair の件数は注文数ではない。** `ProcPair()` は EA 2905-2906 行で
`LotComplex()` を**シグナル・保有に関係なく毎評価バーで2回**呼ぶ（発注の判定は 2935行）。
つまり Pair の `calls` は評価回数であって発注機会ではない。
（第13報で Codex が指摘し、`rejected_strategies` 系の記録に残っている罠。）
"""
import csv, glob, os, re

NAME = {"20260622": "pb_uj", "20260627": "pb_gj", "20260610": "rsi_uj",
        "20260605": "rsi_eu", "20260774": "rsi_gu", "20260629": "PAIR",
        "20260650": "carry", "20261000": "sca_uj", "20261001": "sca_gj"}

for root in ("ml/fxqual14", "ml/fxqualexec"):
    for f in sorted(glob.glob(os.path.join(
            r"C:\Users\f\source\repos\mt5_backtester", root, "run_deals", "*_cap.csv"))):
        m = re.search(r"mc_(oos|is)_([A-Z]\d+)_", os.path.basename(f))
        if not m:
            continue
        win, pid = m.group(1).upper(), m.group(2)
        rows = [l.split(",") for l in open(f, encoding="utf-8") if l.startswith("sleeve,")]
        if not rows:
            continue
        tot_c = tot_d = pc = pd_ = 0
        detail = []
        for r in rows:
            mg, calls, cut, deny = r[1], int(r[2]), int(r[3]), int(r[4])
            tot_c += cut; tot_d += deny
            if mg == "20260629":
                pc, pd_ = cut, deny
            elif cut or deny:
                detail.append(f"{NAME.get(mg, mg)} {cut}/{deny}")
        npc, npd = tot_c - pc, tot_d - pd_
        if tot_c or tot_d:
            print(f"{root.split('/')[-1]:12s} {pid} {win:4s} "
                  f"cut={tot_c:5d} deny={tot_d:5d} | "
                  f"**Pair {pc}/{pd_}（評価回数・発注ではない）** | "
                  f"**Pair以外 {npc}/{npd}** | " + " ".join(detail))
