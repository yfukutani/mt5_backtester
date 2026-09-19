"""第19報 — ゲートで止めた発注が「消えた」のか「後ろへずれた」のかを数える。

【なぜ要るか】
第5ラウンド（`ml/fxqual5`）で、SCA の時間帯ゲートは**止めた発注の 89〜94% が
後ろの足へずれていた**ことが分かった。切り直しは「269件が消える」と言ったが、
実際に消えたのは30件だった。**取引ログの差分は「消えた数」ではない。**

第9ラウンドの2軸は、どちらも**構造的に「ずれる」側**である:

- PB の armed の寿命: 期限切れになっても、押し目条件が一度消えて再成立すれば
  **新しい arm になる。** トレンドが続いていれば押し目は何度も来る。
- Pair の Z 転換待ち: 今日 turning しなくても、`|z|>=entryZ` が続いていれば
  **明日 turning した足で入る。**

**だから損益の差だけを見ても、何が起きたかは分からない。**
入口 deal を時刻と方向で突き合わせて、**消滅・ずれ・新規**に分けて数える。

【使い方】
    python ml/fxqual9/shift.py                     （既定は全案）
    python ml/fxqual9/shift.py A001 A002
    python ml/fxqual9/shift.py --root ml/fxqual8 RV01

【ずれの定義】
対照にあって案に無い入口 deal を「止められた発注」とし、
**同じ枠・同じ方向で、その時刻より後の窓の中に、対照に無い入口 deal がある**
ものを「ずれた」と数える。1対1で貪欲に対応付ける（同じ行き先を2度使わない）。

**窓は2段階で出す。** 狭い窓（4バー）だけだと取りこぼす——
`ml/fxqual5` の SCA 時間帯ゲートは 09時→10・11時のずれなので、
M15 では 4〜8バー先になり、4バーの窓では 78% しか拾えなかった（実際は 89〜94%）。

⚠️ `profit_jpy` 列は使わない。円口座では `profit × usdjpy` の二重換算になっている
（第14報で踏んだ罠）。純益は `profit` で取る。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# magic -> (枠名, 足の秒数)
SLEEVES = {
    20260622: ("PB USDJPY", 4 * 3600),
    20260627: ("PB GBPJPY", 4 * 3600),
    20260610: ("RSI USDJPY", 4 * 3600),
    20260605: ("RSI EURUSD", 1 * 3600),
    20260774: ("RSI GBPUSD", 4 * 3600),
    20260629: ("Pair EU/GU", 1 * 3600),
    20260650: ("Carry AUDJPY", 24 * 3600),
    20261000: ("SCA USDJPY", 15 * 60),
    20261001: ("SCA GBPJPY", 15 * 60),
}
WINDOWS_BARS = (4, 24)      # ずれと見なす窓（バー数）。狭い順


def load(path: Path):
    """入口 deal の一覧と、枠別の純益（position_id から建玉時 magic に引き直す）。

    ⚠️ 窓末の強制決済 deal は magic=0 で記録される（第16報）。position_id で
    引き直さないと枠別の和がブック純益に合わない。
    """
    entries = defaultdict(list)      # magic -> [(time, type)]
    pid_magic: dict[int, int] = {}
    net: dict[int, float] = defaultdict(float)
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            t = int(r["time"])
            pid = int(r["position_id"])
            mg = int(r["magic"])
            if r["entry"] == "0":
                pid_magic[pid] = mg
                entries[mg].append((t, int(r["type"])))
            net[pid_magic.get(pid, mg)] += float(r["profit"])
    return entries, net


def deals_for(root: Path, pid: str, window: str) -> Path | None:
    hits = sorted((root / "run_deals").glob(f"*_{window.lower()}_{pid}_*_deals.csv"))
    return hits[-1] if hits else None


def compare(ctrl_e, prop_e, magic: int):
    """(対照件数, 案件数, 止められた数, [窓ごとのずれ数]) を返す。"""
    c = sorted(ctrl_e.get(magic, []))
    p = sorted(prop_e.get(magic, []))
    common = set(c) & set(p)
    stopped = [x for x in c if x not in common]
    added = [x for x in p if x not in common]
    bar = SLEEVES[magic][1]
    shifts = []
    for nb in WINDOWS_BARS:
        used: set[int] = set()
        n = 0
        for (t, ty) in stopped:
            for j, (t2, ty2) in enumerate(added):
                if j in used or ty2 != ty:
                    continue
                if 0 < t2 - t <= bar * nb:
                    used.add(j)
                    n += 1
                    break
        shifts.append(n)
    return len(c), len(p), len(stopped), shifts


def main() -> None:
    args = list(sys.argv[1:])
    root = REPO / "ml" / "fxqual9"
    if "--root" in args:
        i = args.index("--root")
        a = args[i + 1]
        root = Path(a) if Path(a).is_absolute() else REPO / a
        del args[i:i + 2]
    rows = list(csv.DictReader((root / "results.csv").open(encoding="utf-8")))
    ids = []
    for r in rows:
        if r["proposal_id"] not in ids:
            ids.append(r["proposal_id"])
    ctrl = ids[0]
    props = args or [x for x in ids if x != ctrl]

    w1, w2 = WINDOWS_BARS
    print(f"# {root.name} — 止められた発注は消えたのか、ずれたのか\n")
    print(f"対照: {ctrl}／純益は `profit` 列（`profit_jpy` は二重換算なので使わない）\n")
    for pid in props:
        print(f"## {pid}\n")
        print(f"| 窓 | 枠 | 対照 | 案 | 差 | 止められた | ずれ({w1}バー) "
              f"| **ずれ({w2}バー)** | **ずれ率** | 枠純益Δ |")
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        any_row = False
        for window in ("OOS", "IS"):
            cp = deals_for(root, ctrl, window)
            pp = deals_for(root, pid, window)
            if not cp or not pp:
                print(f"| {window} | — | — | — | — | — | — | — | — | deal ログ無し |")
                continue
            ce, cn = load(cp)
            pe, pn = load(pp)
            for mg, (name, _) in SLEEVES.items():
                nc, np_, stopped, sh = compare(ce, pe, mg)
                d = pn.get(mg, 0.0) - cn.get(mg, 0.0)
                if nc == np_ and stopped == 0 and abs(d) < 0.5:
                    continue        # 完全に同一の枠は出さない
                any_row = True
                rate = f"{sh[1] / stopped * 100:.0f}%" if stopped else "—"
                print(f"| {window} | {name} | {nc} | {np_} | {np_ - nc:+d} "
                      f"| {stopped} | {sh[0]} | **{sh[1]}** | **{rate}** | {d:+,.0f} |")
        if not any_row:
            print("| — | **全枠で完全同一** | | | | | | | | |")
        print()


if __name__ == "__main__":
    main()
