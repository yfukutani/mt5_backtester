"""比例サイジングの初回到達を、有限期間の移動ブロック・ブートストラップで推定する。

過去の優位が将来も続く仮定に限って意味を持ち、85%は将来が過去に似る条件付きの値。
連敗の塊を消す独立抽出は破綻を過小評価しうるためブロックを用いるが、
レジーム変化（相場環境の構造的変化）は再現できない。
最小ロット0.01で比例縮小できない経路を無視するので、実際の破綻確率はより高い。
破綻閾値は運用上の打ち切り水準であり、証拠金の強制ロスカットの正確な再現ではない。
"""
import argparse
import math
import platform
import subprocess
import os
from statistics import median

from common import BOOKS, KS, ROOT, WARNINGS, WINDOWS, load_sources, read_csv, sha, write_csv, write_json


class PathRandom:
    """処理系間で同じ乱数列を得るため、32bit xorshiftの演算を明示する。"""
    def __init__(self, seed, path):
        self.state = ((seed & 0xffffffff) + (path + 1) * 2654435769) & 0xffffffff
        if not self.state:
            self.state = 1

    def randrange(self, n):
        # 剰余の偏りを避け、すべてのブロック開始点を等確率にする。
        limit = 0xffffffff - (0xffffffff % n)
        while True:
            x = self.state
            x ^= (x << 13) & 0xffffffff
            x ^= x >> 17
            x ^= (x << 5) & 0xffffffff
            self.state = x
            if x <= limit:
                return (x - 1) % n


def build_engine():
    compiler = os.path.join(os.environ.get('WINDIR', 'C:/Windows'),
                            'Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    exe = ROOT / '_engine.exe'
    subprocess.run([compiler, '/nologo', '/optimize+', '/out:' + str(exe),
                    str(ROOT / 'engine.cs')], check=True, stdout=subprocess.PIPE)
    return exe


def fast_simulate(exe, profits, k, initial, ruin, length, horizon, paths, seed):
    payload = '\n'.join([','.join(map(str, [k, initial, ruin, length, horizon, paths, seed])),
                         ','.join(map(str, profits))])
    output = subprocess.check_output([str(exe)], input=payload.encode('ascii')).decode('ascii')
    values = output.strip().split(',')
    nw, nr, nu, steps = map(int, values[:4])
    medians = [float(v) if v else '' for v in values[4:]]
    return dict(p_double=nw / paths, p_ruin=nr / paths, p_unresolved=nu / paths,
                n_double=nw, n_ruin=nr, n_unresolved=nu, max_trades=steps,
                median_trades_double=medians[0], median_final_double=medians[1],
                median_final_ruin=medians[2])


def prepare_blocks(profits, k, initial, length):
    blocks = []
    for start in range(len(profits) - length + 1):
        eq = 1.0
        values = []
        for p in profits[start:start + length]:
            eq *= 1 + p * k / initial
            values.append(eq)
            # 非正資産からの架空の復活を防ぐため、この先は必ず逐次判定に渡す。
            if eq <= 0:
                break
        blocks.append((eq, min(values), max(values), values))
    return blocks


def simulate(profits, k, initial=500000, ruin_frac=0.2, length=20,
             max_horizon=3, n_paths=10000, seed=20260911):
    if (not profits or not all(math.isfinite(p) for p in profits)
            or not math.isfinite(k) or k <= 0 or not math.isfinite(initial) or initial <= 0
            or not 0 < ruin_frac < 1 or not 1 <= length <= len(profits)
            or int(length) != length or int(n_paths) != n_paths or n_paths < 1
            or not math.isfinite(max_horizon) or max_horizon <= 0):
        raise ValueError('損益・係数・破綻水準・ブロック長・試行回数・期間の指定が不正です')
    steps = math.floor(len(profits) * max_horizon)
    if steps < 1:
        raise ValueError('最大期間は1取引以上必要です')
    blocks = prepare_blocks(profits, k, initial, length)
    wins, losses, times = [], [], []
    # 経路ごとに乱数を固定し、kや閾値による早期停止が別経路の乱数をずらすのを防ぐ。
    count = (steps + length - 1) // length
    for path in range(n_paths):
        rng = PathRandom(seed, path)
        equity, used = 1.0, 0
        for _ in range(count):
            start = rng.randrange(len(blocks))
            product, low, high, values = blocks[start]
            take = min(length, steps - used)
            # ブロック内部の極値で無到達が保証できる場合だけ飛ばし、計算量を抑える。
            if take == length and equity * low > ruin_frac and equity * high < 2:
                equity *= product
                used += length
                continue
            before = equity
            for v in values[:take]:
                equity = before * v
                used += 1
                if equity >= 2 or equity <= ruin_frac:
                    break
            if equity >= 2 or equity <= ruin_frac:
                break
        if equity >= 2:
            wins.append(equity * initial)
            times.append(used)
        elif equity <= ruin_frac:
            losses.append(equity * initial)
    nw, nr = len(wins), len(losses)
    return dict(p_double=nw / n_paths, p_ruin=nr / n_paths,
                p_unresolved=(n_paths - nw - nr) / n_paths,
                n_double=nw, n_ruin=nr, n_unresolved=n_paths - nw - nr,
                median_trades_double=median(times) if times else '',
                median_final_double=median(wins) if wins else '',
                median_final_ruin=median(losses) if losses else '', max_trades=steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', choices=list(BOOKS), nargs='+', default=list(BOOKS))
    parser.add_argument('--window', choices=WINDOWS, nargs='+', default=list(WINDOWS))
    parser.add_argument('--k', type=float, nargs='+', default=KS)
    parser.add_argument('--block-lengths', type=int, nargs='+', default=[20])
    parser.add_argument('--ruin-fracs', type=float, nargs='+', default=[0.2])
    parser.add_argument('--sensitivity', action='store_true', help='L=1/10/20/50と破綻水準0.1/0.2/0.3の全組合せ')
    parser.add_argument('--max-horizon', type=float, default=3)
    parser.add_argument('--n-paths', type=int, default=10000)
    parser.add_argument('--engine', choices=['python', 'dotnet'], default='python',
                        help='dotnetはWindows標準C#コンパイラで同じ計算を高速化')
    args = parser.parse_args()
    if args.sensitivity:
        args.block_lengths, args.ruin_fracs = [1, 10, 20, 50], [0.1, 0.2, 0.3]
    manifest = load_sources()
    exe = build_engine() if args.engine == 'dotnet' else None
    for warning in WARNINGS:
        print('注意: ' + warning, flush=True)
    for book in args.book:
        for window in args.window:
            key = book + '_' + window
            source = manifest['sources'][key]
            if source['status'] != 'OK':
                print(key + ': データなし', flush=True)
                continue
            path = ROOT / source['trades']
            if sha(path) != source['trades_sha256']:
                raise ValueError('抽出系列のハッシュ不一致: ' + key)
            profits = [float(r['profit']) for r in read_csv(path)]
            rows = []
            for length in args.block_lengths:
                for ruin in args.ruin_fracs:
                    print('\n{} L={} ruin_frac={}\nk | P(2倍) | P(破綻) | P(未決着) | 中央取引数 | 中央月数 | 到達資産中央値 | 破綻資産中央値'.format(key, length, ruin), flush=True)
                    for k in args.k:
                        parameters = (profits, k, source['initial'], ruin, length,
                                      args.max_horizon, args.n_paths, manifest['seed'])
                        # 両実装に同じ検証を適用し、高速版だけ不正入力が通るのを防ぐ。
                        simulate(*(parameters[:6] + (1, parameters[7])))
                        if args.n_paths < 1:
                            raise ValueError('試行回数は1以上必要です')
                        result = fast_simulate(exe, *parameters) if exe else simulate(*parameters)
                        t = result['median_trades_double']
                        months = t * source['window_months'] / len(profits) if t != '' else ''
                        row = dict(book=book, window=window, k=k, block_length=length,
                                   ruin_frac=ruin, initial=source['initial'], n_paths=args.n_paths,
                                   max_horizon=args.max_horizon, seed=manifest['seed'],
                                   n_trades=len(profits), window_months=source['window_months'],
                                   median_months_double=months, **result)
                        rows.append(row)
                        print('{} | {:.2%} | {:.2%} | {:.2%} | {} | {} | {} | {}'.format(
                            k, result['p_double'], result['p_ruin'], result['p_unresolved'],
                            t, round(months, 3) if months != '' else '該当なし',
                            result['median_final_double'], result['median_final_ruin']), flush=True)
            out = ROOT / ('results_' + key + '.csv')
            write_csv(out, rows)
            manifest['simulations'][key] = dict(seed=manifest['seed'], python=platform.python_version(),
                rng='経路別32bit xorshift13/17/5、棄却法で等確率抽出', engine=args.engine,
                block_method='非循環・重複可の移動ブロック',
                k=args.k, block_lengths=args.block_lengths, ruin_fracs=args.ruin_fracs,
                n_paths=args.n_paths, max_horizon=args.max_horizon,
                trades_sha256=sha(path), results_sha256=sha(out),
                code_sha256={n: sha(ROOT / n) for n in ('simulate.py', 'common.py', 'engine.cs')})
            write_json(ROOT / 'sources.json', manifest)


if __name__ == '__main__':
    main()
