"""履歴条件と出力規約を共有し、抽出と再計算の食い違いを防ぐ。"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
WINDOWS = ('IS', 'OOS', 'FULL')
BOOKS = {'fx': 'fxmult1', 'gold': 'goldcomp1'}
SEED = 20260911
KS = [0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32]
WARNINGS = (
    'この確率は過去の優位が将来も続き、将来が過去に似ている条件付きの値です。',
    'ブロック抽出は連敗の塊をある程度保存しますが、レジーム変化は再現できません。',
    '最小ロット0.01による縮小制約を無視するため、実際の破綻確率はここで出る値より高いです。',
    '破綻閾値は運用上の打ち切り水準であり、証拠金による強制ロスカットの正確な再現ではありません。',
    '決済損益だけの近似であり、含み損、証拠金、数量丸め、追加費用を再現しません。',
    'P(2倍)は最大期間内に破綻より先に到達する確率です。未決着を除いた条件付き確率ではありません。',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    with Path(path).open('w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def load_sources():
    return json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
