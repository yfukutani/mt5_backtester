"""指定runの非ゼロ決済約定を保存する。ポジション単位への集約は行わない。"""
import argparse
import ast
import math
from datetime import datetime, timezone
from pathlib import PureWindowsPath

from common import BOOKS, REPO, ROOT, SEED, WARNINGS, WINDOWS, read_csv, sha, write_csv, write_json


def constants(path):
    # 測定モジュールのimportは副作用を招くため、必要なリテラルだけを読む。
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    return {node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ('MAGICS', 'WINDOWS', 'DEPOSIT')}


def select_rows(rows, book, window):
    selected = [r for r in rows if r['window'] == window and float(r['mult']) == 1
                and (book == 'fx' or r['proposal_id'] == 'G001')]
    if len(selected) > 1:
        raise ValueError('runが複数あり自動選択できません: {} {}'.format(book, window))
    if selected and selected[0]['status'] != 'OK':
        raise ValueError('成功runではありません: {} {}'.format(book, window))
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=SEED)
    args = parser.parse_args()
    if not 0 <= args.seed <= 0xffffffff:
        parser.error('seedは0〜4294967295で指定してください')
    (ROOT / 'trades').mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': 1, 'seed': args.seed, 'warnings': WARNINGS,
                'trade_unit': '指定magicかつprofit非ゼロの1約定。分割決済は別取引。同時刻は元行順。',
                'sources': {}, 'simulations': {}}
    for book, folder in BOOKS.items():
        base = REPO / 'ml' / folder
        cfg = constants(base / 'measure.py')
        rows = read_csv(base / 'results.csv')
        for window in WINDOWS:
            key = '{}_{}'.format(book, window)
            chosen = select_rows(rows, book, window)
            if not chosen:
                manifest['sources'][key] = {'status': 'データなし'}
                print(key + ': データなし')
                continue
            row = chosen[0]
            path = base / 'run_deals' / PureWindowsPath(row['deals']).name
            deals = read_csv(path)
            trades = []
            for d in deals:
                if int(d['magic']) not in cfg['MAGICS']:
                    continue
                p = float(d['profit'])
                if not math.isfinite(p):
                    raise ValueError('有限でない損益: ' + str(path))
                # ゼロ決済も指定どおり除外し、入金・IN約定で頻度を水増ししない。
                if p != 0:
                    trades.append({'time': int(d['time']), 'profit': p})
            trades.sort(key=lambda d: d['time'])
            if not trades:
                raise ValueError('有効取引なし: ' + key)
            start, end, months = cfg['WINDOWS'][window]
            a = datetime.strptime(start, '%Y.%m.%d').replace(tzinfo=timezone.utc)
            b = datetime.strptime(end, '%Y.%m.%d').replace(tzinfo=timezone.utc)
            if not all(a.timestamp() <= t['time'] < b.timestamp() + 86400 for t in trades):
                raise ValueError('窓外の約定: ' + key)
            out = ROOT / 'trades' / (key + '.csv')
            write_csv(out, trades, ['time', 'profit'])
            manifest['sources'][key] = {
                'status': 'OK', 'book': book, 'window': window,
                'run_id': row['run_id'], 'result_row': row,
                'deals': path.relative_to(REPO).as_posix(), 'deals_sha256': sha(path),
                'results_sha256': sha(base / 'results.csv'),
                'measure_sha256': sha(base / 'measure.py'), 'magics': cfg['MAGICS'],
                'initial': cfg['DEPOSIT'], 'window_start': start, 'window_end': end,
                'window_months': months, 'days_per_month': 365.25 / 12,
                'average_days_per_trade': months * (365.25 / 12) / len(trades),
                'n_trades': len(trades), 'profit_sum': math.fsum(t['profit'] for t in trades),
                'trades': out.relative_to(ROOT).as_posix(), 'trades_sha256': sha(out),
            }
            print('{}: {}取引 / 損益{:.2f} / {}か月'.format(
                key, len(trades), manifest['sources'][key]['profit_sum'], months))
    write_json(ROOT / 'sources.json', manifest)


if __name__ == '__main__':
    main()
