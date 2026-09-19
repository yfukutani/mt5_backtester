"""fxoanda4 の結果を、報告にそのまま使える形にまとめる（第17報）。

【この集計が守る規約】
`CLAUDE.md` の「報告に必ず含める数値」に合わせる:

- **損益・想定月利・最大DD を、IS 窓と OOS 窓の両方で併記する**
- 複利前提なので **月利は幾何平均** `(最終残高/入金)^(1/月数) − 1`
  （`results.csv` の `monthly_pct` 列は **単利**なので使わない。そのまま報告すると倍近く盛る）
- DD は**直近ピーク比**。テスターの `最大相対DD%` は**確定損益ベース**なので、
  **含み損込みの equity DD を必ず併記する**（OOS で 11〜16pt 違う）
- **最優先の合否は口座破綻の有無**

【さらに第17報で足した列】
**最小証拠金維持率**。`MarginCapPct` は発注時にしか効かないので、
「発注制約を満たす」と「生き残る」は別の性質である。
**100% を割っていたら、その構成は OANDA では死んでいる**（XM は 20%）。

使い方:
    python ml/fxoanda4/summarize.py
    python ml/fxoanda4/summarize.py ml/fxqual17     # 他ラウンドにも使える
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPOSIT = 500_000.0
MONTHS = {"OOS": 55.0, "IS": 60.0, "FULL": 115.0,
          "W1": 24.0, "W2": 24.0, "W3": 24.0}

sys.path.insert(0, str(Path(__file__).resolve().parent))
from margin_level import read_cap  # noqa: E402


def geo_monthly(final_balance: float, months: float) -> float:
    """幾何平均の月利%。複利なのでこれが正しい。"""
    if final_balance <= 0 or months <= 0:
        return float("nan")
    return ((final_balance / DEPOSIT) ** (1.0 / months) - 1.0) * 100.0


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(root: Path) -> list[dict]:
    out_csv = root / "results.csv"
    if not out_csv.exists():
        return []
    rows = list(csv.DictReader(io.open(out_csv, encoding="utf-8", errors="replace")))
    deal_dir = root / "run_deals"
    agent_dir = root / "agent_results"
    for r in rows:
        rid = r.get("run_id", "")
        cap = read_cap(deal_dir / f"{rid}_cap.csv") or {}
        r["_cap"] = cap
        # equity DD は cap ログ側にある（results.csv の dd_pct は残高ベース）
        if "eq_dd" not in cap:
            af = agent_dir / f"{rid}_result.csv"
            if af.exists():
                for line in io.open(af, encoding="utf-8", errors="replace"):
                    if "equity_dd" in line:
                        parts = [p.strip() for p in line.split(",")]
                        for p in parts:
                            v = f(p)
                            if v is not None and 0 < v < 100:
                                cap["eq_dd"] = v
                                break
                        break
    return rows


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    if not root.is_absolute():
        root = REPO / root
    rows = load(root)
    if not rows:
        print(f"{root / 'results.csv'} がまだありません（走行前か、1本も完了していない）")
        return

    print(f"# {root.name} — 損益・想定月利（幾何）・最大DD・最小維持率")
    print()
    hdr = (f"{'案':7}{'窓':5}{'状態':7} {'純益':>12} {'最終残高':>12} "
           f"{'幾何月利':>9} {'残高DD':>8} {'eqDD':>8} {'最小維持率':>10} {'取引':>6}")
    print(hdr)
    print("-" * len(hdr))

    by_id: dict[str, dict[str, dict]] = {}
    for r in rows:
        pid, win = r["proposal_id"], r["window"]
        st = r.get("status", "")
        net, fb, dd = f(r.get("net")), f(r.get("final_balance")), f(r.get("dd_pct"))
        cap = r.get("_cap") or {}
        eqdd = cap.get("eq_dd")
        if cap.get("not_measured"):
            ml = "NOT_MEAS"
        elif "ml_min" in cap:
            ml = f"{cap['ml_min']:.1f}%"
        else:
            ml = "—"
        if st != "OK" or fb is None:
            print(f"{pid:7}{win:5}{st:7} {'FAILED（完走していない。数字は読まない）':>12}")
            continue
        g = geo_monthly(fb, MONTHS.get(win, 0))
        by_id.setdefault(pid, {})[win] = {"g": g, "net": net, "dd": dd,
                                          "eqdd": eqdd, "ml": cap.get("ml_min")}
        print(f"{pid:7}{win:5}{st:7} {net:12,.0f} {fb:12,.0f} "
              f"{g:8.3f}% {dd:7.2f}% "
              f"{(f'{eqdd:.2f}%' if eqdd is not None else '—'):>8} {ml:>10} "
              f"{r.get('trades',''):>6}")

    # --- 対照との差分（IS/OOS 併記）-----------------------------------------
    base = "O000"
    print()
    print(f"## 対照 {base} との差（pt = 幾何月利の差。**IS と OOS を必ず併記する**）")
    print()
    print(f"{'案':7} {'OOS pt':>9} {'IS pt':>9}  判定の材料")
    for pid, wins in by_id.items():
        if pid == base:
            continue
        cells = []
        for w in ("OOS", "IS"):
            b = by_id.get(base, {}).get(w)
            c = wins.get(w)
            cells.append(f"{c['g'] - b['g']:+8.3f}" if (b and c) else "       —")
        mls = [v["ml"] for v in wins.values() if v.get("ml") is not None]
        note = ""
        if mls and min(mls) < 100.0:
            note = f"🔴 最小維持率 {min(mls):.1f}% ＝ OANDA なら切られている"
        print(f"{pid:7} {cells[0]:>9} {cells[1]:>9}  {note}")

    print()
    print("⚠️ `results.csv` の `monthly_pct` 列は**単利**なので報告に使わない"
          "（幾何より倍近く大きく出る）。上表はすべて幾何平均。")
    print("⚠️ 残高DD は確定損益ベース。**含み損込みは eqDD 列**を見ること。")
    print("🔴 最優先の合否は**口座破綻の有無**。FAILED 行の数字は読まない。")


if __name__ == "__main__":
    main()
