# -*- coding: utf-8 -*-
"""走査中だけPCのスリープを抑止する。

【背景】OAFX0192のフルブックISが65,006秒(18時間)かかって失敗した。原因はコードの
不具合ではなく、開始直後にPCがスリープしたこと（イベントログで確認）。
  08-24 10:50:49 スリープ開始 / 08-25 04:53:28 復帰
復帰直後に期限判定が正しく発火して停止させている。ハートビートが18時間途絶えていたのも
プロセスごと凍結していたためである。

【方針】システムの電源設定（保存される設定）は変更しない。SetThreadExecutionStateで
このプロセスが生きている間だけスリープを抑止し、終了時に自動で元へ戻す。
ディスプレイは消えてよいので ES_DISPLAY_REQUIRED は立てない。
"""
import ctypes
import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方: python keepawake.py <実行するコマンド...>")
        return 2
    k32 = ctypes.windll.kernel32
    prev = k32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    if prev == 0:
        print("⚠️スリープ抑止の設定に失敗しました。スリープで走査が止まる可能性があります。",
              flush=True)
    else:
        print("スリープ抑止を有効化しました（このプロセス終了で自動解除）", flush=True)
    try:
        return subprocess.run(sys.argv[1:]).returncode
    finally:
        k32.SetThreadExecutionState(ES_CONTINUOUS)
        print("スリープ抑止を解除しました", flush=True)


if __name__ == "__main__":
    sys.exit(main())
