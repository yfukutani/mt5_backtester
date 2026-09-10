"""有限期間・履歴条件付きの目標達成を、3窓と感度全体で比較する。"""
from common import BOOKS, ROOT, WARNINGS, WINDOWS, load_sources, read_csv, sha


def summarize(rows):
    if not rows:
        return '未計算'
    rows = sorted(rows, key=lambda r: float(r['k']))
    qualifying = [r['k'] for r in rows if float(r['p_double']) >= 0.85]
    best = max(rows, key=lambda r: float(r['p_double']))
    # 離散掃引の穴を連続区間と誤解させないため、合格点をすべて列挙する。
    return '{}；最良k={} ({:.2%})'.format(
        'k={' + ', '.join(qualifying) + '}' if qualifying else '該当なし',
        best['k'], float(best['p_double']))


def main():
    manifest = load_sources()
    lines = ['# 2倍到達確率の評価', '',
             '目標: P(2倍) >= 85%。範囲は測定した離散kの集合であり、間の値は保証しない。',
             '最良はP(2倍)最大（同率なら最小k）。DD制約なし。最終資産は初回到達・破綻時点の値。',
             '月数は到達した経路のみの中央値。1か月=365.25/12日、窓の公称月数÷取引数で換算。',
             '未決着は最大期間で打ち切った経路。無期限に破綻より先に2倍になる確率とは異なる。', '']
    lines += ['- ' + w for w in WARNINGS]
    all_rows = {}
    for book in BOOKS:
        for window in WINDOWS:
            key = book + '_' + window
            src = manifest['sources'][key]
            path = ROOT / ('results_' + key + '.csv')
            if src['status'] == 'OK' and path.exists():
                info = manifest['simulations'].get(key, {})
                if sha(path) != info.get('results_sha256') or src['trades_sha256'] != info.get('trades_sha256'):
                    raise ValueError('結果と出典が一致しません: ' + key)
                all_rows[key] = read_csv(path)
    for book in BOOKS:
        lines += ['', '## ' + book, '', '| L | ruin_frac | IS | OOS | FULL |', '|---:|---:|---|---|---|']
        settings = {(length, ruin) for length in (1, 10, 20, 50) for ruin in (.1, .2, .3)} | {(int(r['block_length']), float(r['ruin_frac']))
                   for key, rows in all_rows.items() if key.startswith(book + '_') for r in rows}
        for length, ruin in sorted(settings):
            cells = []
            for window in WINDOWS:
                key = book + '_' + window
                if manifest['sources'][key]['status'] != 'OK':
                    cells.append('データなし')
                else:
                    subset = [r for r in all_rows.get(key, []) if int(r['block_length']) == length
                              and float(r['ruin_frac']) == ruin]
                    cells.append(summarize(subset))
            lines.append('| {} | {} | {} |'.format(length, ruin, ' | '.join(cells)))
        for window in WINDOWS:
            rows = all_rows.get(book + '_' + window, [])
            if not rows:
                continue
            lines += ['', '{}: 試行{}本、最大{}履歴ぶん、seed={}'.format(
                window, rows[0]['n_paths'], rows[0]['max_horizon'], rows[0]['seed'])]
            for k in sorted({float(r['k']) for r in rows}):
                ps = [float(r['p_double']) for r in rows if float(r['k']) == k]
                lines.append('- k={:g}: 感度全体のP(2倍) {:.2%}〜{:.2%}{}'.format(
                    k, min(ps), max(ps), '（85%判定が設定に依存）' if min(ps) < .85 <= max(ps) else ''))
    lines += ['', '1万本でP=85%付近のモンテカルロ標準誤差は約0.36ポイント。履歴推定誤差やレジーム変化は含まない。']
    text = '\n'.join(lines) + '\n'
    with (ROOT / 'report.md').open('w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(text)


if __name__ == '__main__':
    main()
