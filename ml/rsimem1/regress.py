"""ラボ追加でMode=0（全ラボOFF）の挙動が変わっていないことを確かめる。

【なぜ必要か】RSIシグナル記憶ラボは ProcRSI の中核（フラグの set/clear）に手を入れる。
既定値で1取引でもずれれば、以降のFX側の測定がすべて過去の基準と比較できなくなる。

比較対象は ml/fxmult1 の x1 実測（同じ9枠・同じ RefCap=78000・同じ窓）:
    IS   純益 257,817 / 1595取引
    OOS  純益 119,537 / 1375取引
これはラボ追加**前**のEA（SHA 63d549c8a5e9f37a）で測った値。
"""
from __future__ import annotations

import csv
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fxmult1"))
import measure as fx   # BOOK / run() / WINDOWS をそのまま使う

EXPECT = {"IS": (257817.0, 1595), "OOS": (119537.0, 1375)}


def main():
    for d in (fx.RUN_DIR, fx.CONFIG_DIR, fx.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    fx._ea_sha = fx.ea_sha()
    fx.log(f"REGRESS_START EA_SHA {fx._ea_sha[:16]}")

    ok = True
    for win in ("IS", "OOS"):
        r = fx.run(1, win)
        if r.get("status") != "OK":
            print(f"{win}: 測定失敗")
            ok = False
            continue
        net, n = float(r["net"]), int(r["trades"])
        e_net, e_n = EXPECT[win]
        same = abs(net - e_net) < 0.5 and n == e_n
        ok &= same
        print(f"{win}: 純益 {net:,.0f}（期待 {e_net:,.0f}） / "
              f"取引 {n}（期待 {e_n}） -> {'一致' if same else '★不一致'}")
    print("\n" + ("回帰OK: ラボ追加で既定の挙動は変わっていない"
                  if ok else "★回帰NG: 既定の挙動が変わっている。実装を見直すこと"))


if __name__ == "__main__":
    main()
