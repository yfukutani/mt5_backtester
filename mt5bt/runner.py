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

    def __init__(self, config: BacktestConfig, report_path: Path):
        self.config = config
        self.report_path = report_path

    def run(self, timeout: int = 3600, portable_mode: bool = False) -> bool:
        """バックテストを実行する。

        Args:
            timeout: タイムアウト秒数（デフォルト1時間）
            portable_mode: MT5をポータブルモードで起動するか

        Returns:
            成功した場合True
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ini_path = tmp / "backtest.ini"
            set_path = tmp / f"{self.config.expert}.set"

            self._write_set_file(set_path)
            self._write_ini_file(ini_path, set_path)

            cmd = [self.config.mt5_path, f"/config:{ini_path}"]
            if portable_mode:
                cmd.append("/portable")

            click.echo(f"  MT5ターミナルを起動中: {self.config.mt5_path}")
            click.echo(f"  設定ファイル: {ini_path}")

            proc = subprocess.Popen(cmd)
            return self._wait_for_report(proc, timeout)

    def _write_set_file(self, path: Path) -> None:
        """EAパラメータのSETファイルを書き込む。"""
        cfg = self.config
        lines: list[str] = []

        # 固定パラメータ
        for name, value in cfg.parameters.items():
            if name in cfg.optimize_parameters:
                continue
            lines.append(f"{name}={value}||0||0||0||N")

        # 最適化パラメータ
        for name, opt in cfg.optimize_parameters.items():
            start_val = cfg.parameters.get(name, opt.start)
            lines.append(
                f"{name}={start_val}||{opt.step}||{opt.start}||{opt.stop}||Y"
            )

        path.write_text("\n".join(lines), encoding="utf-16")

    def _write_ini_file(self, ini_path: Path, set_path: Path) -> None:
        """バックテスト用のINIファイルを書き込む。"""
        cfg = self.config
        report_str = str(self.report_path.resolve()).replace("\\", "\\\\")

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

        # SETファイルをEAパラメータとして指定
        if (cfg.parameters or cfg.optimize_parameters) and set_path.exists():
            ini["Tester"]["Inputs"] = str(set_path.resolve())

        with open(ini_path, "w", encoding="utf-8") as f:
            ini.write(f)

    def _wait_for_report(self, proc: subprocess.Popen, timeout: int) -> bool:
        """レポートファイルが生成されるまで待機する。"""
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

                if self.report_path.exists() and self.report_path.stat().st_size > 0:
                    bar.update(timeout - elapsed)
                    click.echo(f"\n  レポート生成完了: {self.report_path}")
                    # MT5が完全に書き込み終わるまで少し待つ
                    time.sleep(2)
                    proc.terminate()
                    return True

                if proc.poll() is not None:
                    click.echo("\n  MT5が終了しました")
                    time.sleep(2)
                    return self.report_path.exists()

                time.sleep(check_interval)

        click.echo(f"\n  タイムアウト ({timeout}秒)")
        proc.terminate()
        return False
