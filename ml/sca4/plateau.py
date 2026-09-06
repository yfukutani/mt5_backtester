"""窓選択の孤立性を、恣意的な判定閾値を置かずに検査する。"""
import json
from statistics import median

import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WINDOWS = ("IS", "OOS")


def read_rows(path):
    # 追記の途中を完成行と誤認しないよう、取得時点の改行までに固定する。
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    data = data[:data.rfind(b"\n") + 1]
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    rows = []
    try:
        for row in reader:
            if None not in row and all(v is not None for v in row.values()):
                rows.append(row)
    except csv.Error:
        # 引用符内の改行で切れた末尾レコードも、次回の読取りに任せる。
        pass
    return rows





def label(cell, grid):
    start, width = cell
    return f"{grid[cell]}({start}-{start + width}時・幅{width})"


def neighborhood(cell, values, grid):
    start, width = cell
    neighbors = [(start - 1, width), (start + 1, width), (start, width - 1), (start, width + 1)]
    neighbors = [c for c in neighbors if c in grid]
    available = [values[c] for c in neighbors if c in values]
    print("  隣接: " + " / ".join(f"{label(c, grid)}={values[c]:+,.0f}" if c in values else f"{label(c, grid)}=未完了" for c in neighbors))
    if not available:
        print("  隣接の正数・中央値・倍率: 算出不可（比較可能な隣接なし）")
        return
    med = median(available)
    ratio = f"{values[cell] / med:.3f}倍" if med != 0 else "算出不可（中央値0）"
    print(f"  隣接の正 {sum(v > 0 for v in available)}/{len(available)}（予定{len(neighbors)}） / 中央値 {med:+,.0f} / 中心÷中央値 {ratio}")
    if med < 0:
        print("  中央値が負のため、倍率の大小はスパイク度の尺度にできません。")


def main():
    grid = {}
    for r in read_rows(ROOT / 'proposals.csv'):
        if r['family'] == 'U1_window':
            p = json.loads(r['parameter_json'])
            start = int(p['Sca4RangeStart'])
            grid[start, int(p['Sca4RangeEnd']) - start] = r['proposal_id']
    # 掃引はIS全案を終えてからOOSに入るので、両窓が揃うのは後半に入ってから。
    # 両窓成立を条件にすると前半ずっと何も見えないため、窓ごとに独立して評価する。
    # IS/OOSの重なり判定だけは、当然どちらも揃った窓に限って行う。
    rows = {win: {r['proposal_id']: r for r in read_rows(ROOT / 'results.csv')
                  if r['window'] == win and r['status'] == 'OK'
                  and r['family'] == 'U1_window' and r.get('sca4_net') not in (None, '')}
            for win in WINDOWS}
    values = {win: {c: float(rows[win][pid]['sca4_net'])
                    for c, pid in grid.items() if pid in rows[win]}
              for win in WINDOWS}
    print(f"U1_window 台地検査: 全{len(grid)}窓 / "
          + " / ".join(f"{win}済 {len(values[win])}窓" for win in WINDOWS))
    print("第4枠 magic 20261005 / sca4_net は profit由来・円。時刻はサーバー時刻。")
    print("-- = 未完了または数値欠損、対象外 = 提案なし。未完了はゼロに数えません。")
    print("隣接は開始±1・幅固定、および開始固定・幅±1の上下左右（斜めを除く）。")
    for win in WINDOWS:
        for field in ('sca4_net', 'sca4_n'):
            print(f"\n{win} {field} / 開始時刻 × レンジ幅")
            print("開始       幅1h         幅2h         幅3h")
            for start in range(11, 21):
                cells = []
                for width in range(1, 4):
                    pid = grid.get((start, width))
                    cells.append("対象外" if pid is None
                                 else f"{float(rows[win][pid][field]):,.0f}"
                                 if pid in rows[win] else "--")
                print(f"{start:>2}時 " + " ".join(f"{v:>12}" for v in cells))
        v = values[win]
        print(f"{win}: 正のセル {sum(x > 0 for x in v.values())}/{len(grid)}窓（評価済み{len(v)}、未完了{len(grid)-len(v)}）")
        if v:
            # 同率最良を任意に一つ選ぶと、隣接評価が選択順に依存してしまう。
            for c in sorted(c for c in v if v[c] == max(v.values())):
                print(f"{win} 暫定最良 {label(c, grid)} = {v[c]:+,.0f}")
                neighborhood(c, v, grid)
        else:
            print(f"{win} 最良セル・隣接中央値・倍率: 算出不可（当該窓OKなし）")
        c = (12, 1)
        if c in v:
            print(f"{win} 参照 S4001（EA既定の中心点） = {v[c]:+,.0f}")
            neighborhood(c, v, grid)
        else:
            print(f"{win} 参照 S4001（EA既定の中心点）: 比較待ち")
    print("\nIS/OOS 上位窓の重なり（全k、境界同率を含む。kは判定閾値ではありません）:")
    # 重なりは両窓が揃った窓の上でしか意味を持たないので、共通部分の数で頭打ちにする。
    both = set(values['IS']) & set(values['OOS'])
    n = len(both)
    for k in range(1, n + 1):
        tops = []
        for win in WINDOWS:
            v = values[win]
            cutoff = sorted(v.values(), reverse=True)[k-1]
            tops.append({c for c in v if v[c] >= cutoff})
        common = tops[0] & tops[1]
        print(f"上位{k}: IS {len(tops[0])}窓 / OOS {len(tops[1])}窓 / 共通{len(common)}窓: " + ', '.join(grid[c] for c in sorted(common)))
    if not n:
        print("算出不可（両窓が揃った窓がまだ無い）")
    print("\n結論（判断材料）:")
    if len(both) < len(grid):
        print(f"全{len(grid)}窓中、両窓が揃ったのは{len(both)}窓だけで、"
              f"S4001の台地性・孤立性の評価は暫定です。")
    print("隣接にも正の純益が続く点は台地寄り、隣接の非正値や中心からの大幅な低下はスパイク寄りの材料です。")
    print("隣接中央値が正なら中心÷中央値が大きいほどスパイク寄りですが、倍率の判定閾値は置きません。")
    print("IS/OOSの上位窓の不一致は窓選択の過学習を疑う材料です。一致しても過学習を否定できません。")
    print("上記の正数・隣接値・倍率・順位重複を併せて判断し、台地／スパイクとは断定しません。")


if __name__ == '__main__':
    main()
