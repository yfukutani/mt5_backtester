"""第2セッションのみ（第3なし）を x1 で測る。

【なぜ必要か】ラウンド4（第3セッション）のDD判定は MT5 の最大相対DD% を使っていた。
相対DD%は「その時点の残高」に対する比率なので、利益が増えて残高が育つと
同じ円建ての落ち込みでも%が小さく出る。ml/mult1 の測定で、第2+第3を入れると
IS の相対DD%は 5.457%→5.218% と下がるのに、**円建ての落ち込みは
32,248円→40,563円と25.8%増えている**ことが分かった。

第3セッション単独の寄与を円建てで再判定するには「第2のみ」の円建てDDが要る。
これがラウンド4の採否そのものを左右する。
"""
from pathlib import Path
import csv

import measure as m

OUT = Path(__file__).resolve().parent / "results_sca2only.csv"

SCA2_ONLY = dict(m.SESSIONS_ON)
SCA2_ONLY["Sca3Enable"] = False


def main():
    for d in (m.RUN_DIR, m.CONFIG_DIR, m.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    m._ea_sha = m.ea_sha()
    m.log(f"EA_SHA {m._ea_sha[:16]}")

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    results = []
    try:
        for w in ("IS", "OOS", "FULL"):
            results.append(m.run("SCA2ONLY", SCA2_ONLY, 1, w))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    fields = ["label", "mult", "window", "status", "net", "pf", "dd_pct",
              "monthly_pct", "trades", "deals", "elapsed", "run_id"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})
    m.log(f"SCA2ONLY_END rows={len(results)} -> {OUT}")


if __name__ == "__main__":
    main()
