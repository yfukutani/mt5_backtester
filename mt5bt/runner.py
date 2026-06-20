"""MT5ターミナルをINI/SETファイルで制御してバックテストを実行する。"""

from __future__ import annotations

import configparser
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import click

from .config import BacktestConfig


class MT5Runner:
    """MT5ストラテジーテスターのランナー。"""

    @staticmethod
    def _find_terminal_hash(mt5_exe: str) -> Optional[str]:
        """origin.txt を照合して MT5 インストールに対応するターミナルハッシュを返す。"""
        import os
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        terminals_dir = Path(appdata) / "MetaQuotes" / "Terminal"
        if not terminals_dir.exists():
            return None
        exe_dir = str(Path(mt5_exe).parent).lower()
        for child in terminals_dir.iterdir():
            origin = child / "origin.txt"
            if not origin.exists():
                continue
            for enc in ("utf-16", "utf-8", "cp932"):
                try:
                    content = origin.read_text(encoding=enc).strip()
                    break
                except (UnicodeDecodeError, ValueError):
                    content = ""
            if content.lower() == exe_dir or content.lower() == str(Path(mt5_exe).parent.parent).lower():
                return child.name
        return None

    @staticmethod
    def find_mql5_files_dir(mt5_exe: str) -> Optional[Path]:
        """ターミナルの MQL5\\Files ディレクトリを返す（SET ファイル配置用）。"""
        import os
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        h = MT5Runner._find_terminal_hash(mt5_exe)
        if not h:
            return None
        files_dir = Path(appdata) / "MetaQuotes" / "Terminal" / h / "MQL5" / "Files"
        files_dir.mkdir(parents=True, exist_ok=True)
        return files_dir

    @staticmethod
    def find_tester_files_dirs(mt5_exe: str) -> list[Path]:
        """Tester エージェントが OnTester() で書き出す MQL5\\Files ディレクトリを探す。

        MT5 はバックテスト時にファイルをターミナルではなく Tester エージェントの
        MQL5\\Files へ書き出す。ハッシュは Terminal と同じ値が Tester 配下にも使われる。
        """
        import os
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return []
        h = MT5Runner._find_terminal_hash(mt5_exe)
        if not h:
            return []
        tester_root = Path(appdata) / "MetaQuotes" / "Tester" / h
        dirs: list[Path] = []
        if tester_root.exists():
            for agent_dir in sorted(tester_root.iterdir()):
                files_dir = agent_dir / "MQL5" / "Files"
                if files_dir.exists():
                    dirs.append(files_dir)
        return dirs

    def __init__(self, config: BacktestConfig, report_path: Path):
        self.config = config
        self.report_path = report_path
        self.mql5_files_dir: Optional[Path] = self.find_mql5_files_dir(config.mt5_path)
        self._tester_files_dirs: list[Path] = self.find_tester_files_dirs(config.mt5_path)

    def run(self, timeout: int = 3600, portable_mode: bool = False) -> bool:
        """バックテストを実行する。

        Returns:
            成功した場合True（結果CSVはself.result_csv_pathに設定）
        """
        self.result_csv_path: Optional[Path] = None

        # OnTester() が書き出す CSV の候補パスを収集
        # 実際にはターミナルではなく Tester エージェントの MQL5\Files に書かれる
        result_file_name = self.config.parameters.get("ResultFileName", "")
        self._result_csv_candidates: list[Path] = []
        if result_file_name:
            for d in self._tester_files_dirs:
                self._result_csv_candidates.append(d / str(result_file_name))
            if self.mql5_files_dir:
                self._result_csv_candidates.append(self.mql5_files_dir / str(result_file_name))

        # SETファイルはMT5の標準パス Profiles\Tester\ に書き込む
        set_path: Optional[Path] = None
        if self.mql5_files_dir:
            tester_dir = self.mql5_files_dir.parent / "Profiles" / "Tester"
            tester_dir.mkdir(parents=True, exist_ok=True)
            set_path = tester_dir / f"{self.config.expert}.set"
            self._write_set_file(set_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ini_path = tmp / "backtest.ini"

            # Inputs不要（Profiles\Testerに自動配置済み）
            self._write_ini_file(ini_path, set_path)

            cmd = [self.config.mt5_path, f"/config:{ini_path}"]
            if portable_mode:
                cmd.append("/portable")

            click.echo(f"  MT5ターミナルを起動中: {self.config.mt5_path}")
            click.echo(f"  設定ファイル: {ini_path}")
            if set_path:
                click.echo(f"  SETファイル: {set_path}")

            proc = subprocess.Popen(cmd)
            return self._wait_for_completion(proc, timeout)

    def _write_set_file(self, path: Path) -> None:
        """EAパラメータのSETファイルを書き込む（Profiles/Tester形式）。

        MT5標準形式: ParamName=value||default||min||max||N
        文字列型:    ParamName=value
        """
        cfg = self.config
        lines: list[str] = [
            "; generated by mt5bt",
        ]

        # 固定パラメータ
        for name, value in cfg.parameters.items():
            if name in cfg.optimize_parameters:
                continue
            if isinstance(value, str):
                # 文字列パラメータ: value のみ
                lines.append(f"{name}={value}")
            elif isinstance(value, bool):
                v = 1 if value else 0
                lines.append(f"{name}={v}||{v}||0||1||N")
            elif isinstance(value, int):
                lines.append(f"{name}={value}||{value}||{value}||{value}||N")
            else:
                lines.append(f"{name}={value}||{value}||{value}||{value}||N")

        # 最適化パラメータ
        for name, opt in cfg.optimize_parameters.items():
            start_val = cfg.parameters.get(name, opt.start)
            lines.append(
                f"{name}={start_val}||{start_val}||{opt.start}||{opt.stop}||Y"
            )

        path.write_text("\n".join(lines), encoding="utf-16")

    def _write_ini_file(self, ini_path: Path, set_path: Path) -> None:
        """バックテスト用のINIファイルを書き込む。"""
        cfg = self.config
        # MT5はレポートパスに拡張子なしを推奨（.htmを自動付与）
        # バックスラッシュを使用（フォワードスラッシュも動作するが念のため）
        report_no_ext = self.report_path.with_suffix("")
        report_str = str(report_no_ext.resolve())

        opt_mode = 0
        if cfg.optimize_enabled and cfg.optimize_parameters:
            opt_mode = 1  # 遅い最適化（全結果）

        ini = configparser.RawConfigParser()
        ini.optionxform = str  # キーの大文字小文字を保持（MT5は大文字キーを期待）
        ini["Tester"] = {
            "Expert": cfg.expert,
            "Symbol": cfg.symbol,
            "Period": str(cfg.period_value),
            "Deposit": str(int(cfg.deposit)),
            "Currency": cfg.currency,
            "Leverage": str(cfg.leverage),
            "Model": str(cfg.model_value),
            "FromDate": cfg.from_date,
            "ToDate": cfg.to_date,
            "Optimization": str(opt_mode),
            "OptimizationCriterion": str(cfg.criterion_value),
            "Report": report_str,
            "ReplaceReport": "1",
            "ShutdownTerminal": "1",
            "UseLocal": "1",
        }

        # SETファイルが Profiles\Tester\ 以外の場所にある場合のみ Inputs を指定
        # (Profiles\Tester\ にあれば MT5 が自動で読み込む)
        if set_path and set_path.exists():
            tester_profiles = Path(self.config.mt5_path).parent  # dummy check
            try:
                # Profiles\Tester 配下なら Inputs 不要
                from pathlib import PurePath
                if "Profiles" not in str(set_path) or "Tester" not in str(set_path):
                    ini["Tester"]["Inputs"] = str(set_path.resolve())
            except Exception:
                pass

        # MT5はスペースなしの key=value 形式を期待する
        with open(ini_path, "w", encoding="utf-8") as f:
            ini.write(f, space_around_delimiters=False)

    def _find_result_csv(self) -> Optional[Path]:
        """候補パスを順に調べて存在するCSVを返す。"""
        for p in self._result_csv_candidates:
            if p.exists() and p.stat().st_size > 0:
                return p
        return None

    def _wait_for_completion(self, proc: subprocess.Popen, timeout: int) -> bool:
        """バックテスト終了（または結果CSV生成）まで待機する。"""
        start = time.time()
        check_interval = 5

        with click.progressbar(
            length=timeout,
            label="  バックテスト実行中",
            show_pos=True,
            show_percent=True,
        ) as bar:
            last_elapsed = 0
            while time.time() - start < timeout:
                elapsed = int(time.time() - start)
                bar.update(elapsed - last_elapsed)
                last_elapsed = elapsed

                # Tester/Terminal 両方の候補パスを監視
                found = self._find_result_csv()
                if found:
                    bar.update(timeout - elapsed)
                    self.result_csv_path = found
                    click.echo(f"\n  結果CSV生成完了: {found}")
                    time.sleep(1)
                    proc.terminate()
                    return True

                if proc.poll() is not None:
                    click.echo("\n  MT5が終了しました")
                    time.sleep(2)
                    found = self._find_result_csv()
                    if found:
                        self.result_csv_path = found
                        return True
                    return proc.returncode == 0

                time.sleep(check_interval)

        click.echo(f"\n  タイムアウト ({timeout}秒)")
        proc.terminate()
        return False
