"""新枠の両窓純益・サンプル・年依存・ファミリーの再現性を厳しく判定する。"""
import argparse
import csv
import math
from pathlib import Path
from statistics import median

from generate_proposals import ROOT, SYMBOLS, load_proposals, parameters

WINDOWS = ("IS", "OOS")
MAGICS = {20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
          20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
          20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj",
          20261008: "sca_new"}
EXISTING = tuple(k for k in MAGICS.values() if k != "sca_new")
MIN_TRADES = 60


def read_deals(path):
    sleeves = {k: {"net": 0.0, "n": 0} for k in MAGICS.values()}
    rows = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"time", "magic", "entry", "profit"} <= set(reader.fieldnames or []):
            raise ValueError(f"dealログの必須列がありません: {path}")
        for r in reader:
            p = float(r["profit"])
            if not math.isfinite(p):
                raise ValueError(f"有限でない損益: {path}")
            t, magic, entry = int(r["time"]), int(r["magic"]), int(r["entry"])
            if entry not in (0, 1, 2, 3):
                raise ValueError(f"不正なentry: {path}")
            if p != 0:
                rows.append((t, magic, p))
            if magic in MAGICS:
                a = sleeves[MAGICS[magic]]
                # measureと同じ定義を保ち、集計方式の違いを効果と誤認しない。
                if entry == 0:
                    a["n"] += 1
                else:
                    a["net"] += p
    # fxmult1.curveと同じ同時刻順序で、DDの再集計差を避ける。
    rows.sort()
    peak = cum = worst = 0.0
    for _, _, p in rows:
        cum += p
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return dict(sleeves=sleeves, new_net=sleeves["sca_new"]["net"], new_n=sleeves["sca_new"]["n"],
                book_net=cum, dd_yen=worst)


def collect(results, proposals):
    expected = {p["proposal_id"]: p for p in proposals}
    by = {}
    if not results.is_file():
        return by
    with open(results, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"proposal_id", "window", "parameter_json", "status", "deals"} <= set(reader.fieldnames or []):
            raise ValueError("結果CSVの必須列がありません")
        for r in reader:
            pid, win = r["proposal_id"], r["window"]
            if pid not in expected or win not in WINDOWS:
                raise ValueError(f"未知の案または窓: {pid}/{win}")
            if parameters(r["parameter_json"]) != parameters(expected[pid]["parameter_json"]):
                raise ValueError(f"案と結果のパラメータが不一致: {pid}")
            if r["status"] != "OK" or not r["deals"]:
                continue
            path = Path(r["deals"])
            if not path.is_absolute():
                path = results.parent / "run_deals" / path
            if not path.is_file():
                continue
            by[pid, win] = read_deals(path)
            by[pid, win]["path"] = path
    for (pid, win), r in by.items():
        base = by.get(("N001", win))
        if base is None:
            continue
        if base["new_n"] or base["new_net"]:
            raise ValueError("N001に新枠取引が混入しています")
        r["delta_net"] = {k: r["sleeves"][k]["net"] - base["sleeves"][k]["net"] for k in EXISTING}
        r["delta_n"] = {k: r["sleeves"][k]["n"] - base["sleeves"][k]["n"] for k in EXISTING}
        # 枠間の増減相殺で約3,500円の変化を隠さないため、絶対差も残す。
        r["changed"] = sum(abs(n) for n in r["delta_n"].values())
        r["abs_delta_net"] = sum(abs(v) for v in r["delta_net"].values())
    return by


def paired(by, pid):
    return all((pid, w) in by for w in WINDOWS)


def both_positive(by, pid):
    return paired(by, pid) and all(by[pid, w]['new_net'] > 0 for w in WINDOWS)


def rankings(by, proposals):
    eligible = [p['proposal_id'] for p in proposals if p['family'] != 'S0'
                and both_positive(by, p['proposal_id'])
                and by[p['proposal_id'], 'IS']['new_n'] >= MIN_TRADES]
    return sorted(eligible, key=lambda pid: (-min(by[pid, w]['new_net'] for w in WINDOWS), pid))


def family_stats(by, proposals, family):
    members = [p['proposal_id'] for p in proposals if p['family'] == family]
    valid = [pid for pid in members if paired(by, pid)]
    meds = {w: median(by[pid, w]['new_net'] for pid in valid) for w in WINDOWS} if valid else {}
    return members, valid, meds


def report(by, proposals):
    print('銘柄別の要約（新枠純益・両窓完了案のみ、S0除外）')
    for symbol in SYMBOLS:
        members = [p['proposal_id'] for p in proposals if p['family'] != 'S0'
                   and parameters(p['parameter_json'])['ScaNewSymbol'] == symbol]
        valid = [pid for pid in members if paired(by, pid)]
        parts = []
        for w in WINDOWS:
            vals = [by[pid, w]['new_net'] for pid in valid]
            parts.append(f'{w}: 中央値={median(vals):+,.2f}円 最大={max(vals):+,.2f}円 最小={min(vals):+,.2f}円'
                         if vals else f'{w}: 未算出')
        print(f'{symbol}: 完了={len(valid)}/{len(members)} 両窓正={sum(both_positive(by, pid) for pid in valid)} / ' + ' / '.join(parts))
    s1 = [p['proposal_id'] for p in proposals if p['family'] == 'S1']
    s1_ok = any(both_positive(by, pid) for pid in s1)
    s1_complete = all(paired(by, pid) for pid in s1)
    print('\n第一判定S1: ' + ('両窓正の銘柄あり' if s1_ok else
          '横展開不成立（S1全銘柄で両窓正なし）' if s1_complete else '未完了・結論保留'))
    print('PB横展開・SCA第2セッションの棄却実績を踏まえ、単発の黒字を採用根拠にしない。')
    print('最大DDは合否に使わない。円建てDDはdeal確定損益の累積から計算し、含み損を含まない。')
    print('全案・両窓完了' if all(paired(by, p['proposal_id']) for p in proposals) else '暫定結果：未完了が残るため最終採用は保留')
    print('\n両窓正かつIS 60取引以上（弱い窓の新枠純益で降順・最終合格とは別）')
    ranked = rankings(by, proposals)
    for pid in ranked:
        print(f'{pid}: IS={by[pid,"IS"]["new_net"]:+,.2f}円 / OOS={by[pid,"OOS"]["new_net"]:+,.2f}円')
    if not ranked:
        print('該当なし（未完了は不合格と断定しない）')

    print('\nファミリー別の中央値（黒字案・サンプル十分な案だけに絞らない）')
    family_pass = {}
    for family in dict.fromkeys(p['family'] for p in proposals):
        members, valid, meds = family_stats(by, proposals, family)
        family_pass[family] = len(valid) == len(members) and bool(meds) and all(v > 0 for v in meds.values())
        values = ' / '.join(f'{w}中央値={v:+,.2f}円' for w, v in meds.items()) or '未算出'
        state = '対象外' if family == 'S0' else ('保留' if len(valid) < len(members) else '合格' if family_pass[family] else '不合格')
        print(f'{family}: 完了={len(valid)}/{len(members)} / {values} / 中央値ゲート={state}')

    from robustness import evaluate
    print('\n全案詳細（既存9枠差はN001比。過去の約3,500円変動と規模を比較）')
    print('取引数絶対差は変更規模の代理指標。同数の取引入替は検出できず、差0でも取引集合の不変は保証しない。')
    print('比較：既存SCA第1の最良年除外後実測 IS +81,175円 / OOS +16,257円')
    for p in proposals:
        pid = p['proposal_id']
        print(f'{pid} [{p["family"]}] {p["description"]}')
        robust_ok = True
        for w in WINDOWS:
            r = by.get((pid, w))
            if r is None:
                print(f'  {w}: 未完了')
                robust_ok = False
                continue
            year = evaluate(r['path'])
            if abs(year['total'] - r['new_net']) > 0.000001:
                raise ValueError('年次集計と新枠純益が不一致: ' + pid)
            robust_ok = robust_ok and year['ex_best'] > 0
            print(f'  {w}: 新枠純益={r["new_net"]:+,.2f}円 / 取引数={r["new_n"]} / '
                  f'最良年={year["best_year"]}・除外後={year["ex_best"]:+,.2f}円')
            if 'delta_net' in r:
                unchanged = all(abs(v) < 0.000001 for v in r['delta_net'].values()) and r['changed'] == 0
                print(f'    既存9枠集計不変={unchanged} / 純益差合計={sum(r["delta_net"].values()):+,.2f}円 / '
                      f'絶対差合計={r["abs_delta_net"]:,.2f}円（3,500円の{r["abs_delta_net"]/3500:.2f}倍） / '
                      f'最大枠差={max(abs(v) for v in r["delta_net"].values()):,.2f}円 / 取引数絶対差={r["changed"]}')
                for k in EXISTING:
                    print(f'      {k}: 純益差={r["delta_net"][k]:+,.2f}円 / 取引数差={r["delta_n"][k]:+d}')
            else:
                print('    N001未完了・既存9枠不変は未確認')
            print(f'    参考のみ：ブック純益={r["book_net"]:+,.2f}円 / 円建てDD={r["dd_yen"]:,.2f}円')
        sample = by.get((pid, 'IS'))
        print('  ISサンプルゲート: ' + ('対象外（S0）' if p['family'] == 'S0' else
              '未完了' if sample is None else '合格' if sample['new_n'] >= MIN_TRADES else '不合格'))
        members, valid, _ = family_stats(by, proposals, p['family'])
        if p['family'] == 'S0':
            verdict = '基準・判定対象外'
        elif not paired(by, pid) or not s1_complete or len(valid) < len(members) or not paired(by, 'N001'):
            verdict = '判定保留（必要な案・基準・ファミリーが未完了）'
        else:
            passed = s1_ok and both_positive(by, pid) and sample['new_n'] >= MIN_TRADES and robust_ok and family_pass[p['family']]
            verdict = '条件合格候補（既存枠変動の規模も要確認）' if passed else '不合格'
        print('  総合: ' + verdict)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'results.csv')
    parser.add_argument('--proposals', type=Path, default=ROOT / 'proposals.csv')
    args = parser.parse_args()
    proposals = load_proposals(args.proposals)
    report(collect(args.results, proposals), proposals)


if __name__ == '__main__':
    main()
