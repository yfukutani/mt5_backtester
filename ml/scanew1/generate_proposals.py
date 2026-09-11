"""横展開の成功を仮定せず、全5銘柄に同じ事前固定の格子を適用する。"""
import csv
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["proposal_id", "family", "description", "parameter_json"]
SYMBOLS = ("EURJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY")
# EAのSCANEW入力を全指定し、後日の既定値変更による比較条件の混在を防ぐ。
DEFAULTS = dict(GlobalLotMult=1, ScaNewEnable=False, ScaNewSymbol="EURJPY",
                ScaNewRangeStart=0, ScaNewRangeEnd=9, ScaNewTradeEnd=12,
                ScaNewForceClose=22, ScaNewMinRange=0.30, ScaNewMaxRange=1.00,
                ScaNewBuffer=0.10, ScaNewRR=2.0, ScaNewSkipFriday=False,
                ScaNewRevBoost=True, ScaNewBoostMult=2.0, ScaNewLot=0.01)


def parameters(raw):
    p = json.loads(raw)
    if not isinstance(p, dict) or set(p) != set(DEFAULTS):
        raise ValueError("固定倍率・SCANEW入力に過不足があります")
    for k, default in DEFAULTS.items():
        if isinstance(default, bool):
            valid = type(p[k]) is bool
        elif isinstance(default, str):
            valid = p[k] in SYMBOLS
        else:
            valid = type(p[k]) in (int, float) and math.isfinite(p[k])
            if type(default) is int:
                valid = valid and type(p[k]) is int
        if not valid:
            raise ValueError("入力型または値が不正: " + k)
    if p['GlobalLotMult'] != 1 or p['ScaNewLot'] != DEFAULTS['ScaNewLot']:
        raise ValueError("倍率1・ロット0.01に固定してください")
    if not (0 <= p['ScaNewRangeStart'] < p['ScaNewRangeEnd'] <
            p['ScaNewTradeEnd'] < p['ScaNewForceClose'] <= 24):
        raise ValueError("レンジ・締切・強制決済の時刻順が不正です")
    if not (0 <= p['ScaNewMinRange'] < p['ScaNewMaxRange'] and
            p['ScaNewBuffer'] >= 0 and p['ScaNewRR'] > 0 and p['ScaNewBoostMult'] > 0):
        raise ValueError("レンジ幅・RR・バッファ・Boostが不正です")
    return p


def canonical(p):
    # 無効枠の銘柄名だけを変えても別の実験にはならない。
    return json.dumps(p if p['ScaNewEnable'] else DEFAULTS, sort_keys=True, separators=(',', ':'))


def generate():
    rows, seen = [], set()
    duplicates = 0

    def add(family, description, **changes):
        nonlocal duplicates
        p = dict(DEFAULTS, **changes)
        raw = json.dumps(p, sort_keys=True, separators=(',', ':'))
        key = canonical(parameters(raw))
        if key in seen:
            duplicates += 1
            return
        seen.add(key)
        rows.append(dict(proposal_id=f'N{len(rows)+1:03d}', family=family,
                         description=description, parameter_json=raw))

    add('S0', 'EURJPY（設定のみ・新枠OFF）／既存9枠基準')
    variants = [('S1', [{}]),
                ('S2', [dict(ScaNewRangeEnd=v) for v in (7, 11)]),
                ('S3', [dict(ScaNewTradeEnd=v) for v in (15, 18)]),
                ('S4', [dict(ScaNewRR=v) for v in (1.5, 3.0)]),
                ('S5', [dict(ScaNewMinRange=a, ScaNewMaxRange=b)
                        for a, b in ((0.20, 1.00), (0.40, 1.40))]),
                ('S6', [dict(ScaNewBuffer=0.0), dict(ScaNewBoostMult=4.0)])]
    for family, changes in variants:
        for symbol in SYMBOLS:
            for change in changes:
                label = 'USDJPY親枠の既定形' if not change else '・'.join(f'{k}={v}' for k, v in change.items())
                add(family, f'{symbol}／{label}', ScaNewEnable=True, ScaNewSymbol=symbol, **change)
    return rows, duplicates


def load_proposals(path=ROOT / 'proposals.csv'):
    with open(path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError('提案CSVの列が一致しません')
        rows = list(reader)
    expected, _ = generate()
    if len(rows) != len(expected):
        raise ValueError('事前固定の56案が必要です')
    for row, target in zip(rows, expected):
        if (any(row[k] != target[k] for k in ('proposal_id', 'family', 'description')) or
                parameters(row['parameter_json']) != parameters(target['parameter_json'])):
            raise ValueError('事前固定の案と一致しません: ' + row['proposal_id'])
    return rows


def main():
    rows, duplicates = generate()
    with open(ROOT / 'proposals.csv', 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(f'総数={len(rows)} / ファミリー={dict(Counter(r["family"] for r in rows))} / 重複除外={duplicates}')
    print('有効案の銘柄別=' + str(dict(Counter(parameters(r['parameter_json'])['ScaNewSymbol']
          for r in rows if parameters(r['parameter_json'])['ScaNewEnable']))))


if __name__ == '__main__':
    main()
