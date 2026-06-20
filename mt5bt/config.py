"""設定ファイルの読み込みとバリデーション。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


PERIOD_MAP = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200,
}

MODEL_MAP = {
    "every_tick": 0,
    "control_points": 1,
    "open_prices": 2,
    "math_calculations": 3,
    "every_tick_real": 4,
}

CRITERION_MAP = {
    "balance": 0,
    "balance_maxdd": 1,
    "profit_factor": 2,
    "expected_payoff": 3,
    "drawdown_pct": 4,
    "sharpe": 5,
    "custom": 6,
}


@dataclass
class OptimizeParam:
    start: float
    stop: float
    step: float


@dataclass
class BacktestConfig:
    # MT5設定
    mt5_path: str
    expert: str
    symbol: str
    period: str
    from_date: str
    to_date: str

    # 口座設定
    deposit: float = 10000.0
    currency: str = "USD"
    leverage: int = 100

    # テストモデル
    model: str = "open_prices"

    # EAパラメータ（固定値）
    parameters: dict[str, Any] = field(default_factory=dict)

    # 最適化設定
    optimize_enabled: bool = False
    optimize_criterion: str = "profit_factor"
    optimize_parameters: dict[str, OptimizeParam] = field(default_factory=dict)

    # 出力設定
    report_dir: str = "results"
    report_name: str = ""

    @property
    def period_value(self) -> int:
        key = self.period.upper()
        if key not in PERIOD_MAP:
            raise ValueError(f"不正な期間: {self.period}. 使用可能: {list(PERIOD_MAP.keys())}")
        return PERIOD_MAP[key]

    @property
    def model_value(self) -> int:
        key = self.model.lower()
        if key not in MODEL_MAP:
            raise ValueError(f"不正なモデル: {self.model}. 使用可能: {list(MODEL_MAP.keys())}")
        return MODEL_MAP[key]

    @property
    def criterion_value(self) -> int:
        key = self.optimize_criterion.lower()
        if key not in CRITERION_MAP:
            raise ValueError(f"不正な最適化基準: {self.optimize_criterion}. 使用可能: {list(CRITERION_MAP.keys())}")
        return CRITERION_MAP[key]


def load_config(config_path: str | Path) -> BacktestConfig:
    """YAMLコンフィグファイルを読み込む。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 最適化パラメータのパース
    opt_params: dict[str, OptimizeParam] = {}
    optimize_section = data.get("optimize", {})
    for param_name, param_data in optimize_section.get("parameters", {}).items():
        opt_params[param_name] = OptimizeParam(
            start=float(param_data["from"]),
            stop=float(param_data["to"]),
            step=float(param_data["step"]),
        )

    mt5_path = data.get("mt5_path", _find_mt5_path())

    return BacktestConfig(
        mt5_path=mt5_path,
        expert=data["expert"],
        symbol=data["symbol"],
        period=data.get("period", "H1"),
        from_date=data["from_date"],
        to_date=data["to_date"],
        deposit=float(data.get("deposit", 10000)),
        currency=data.get("currency", "USD"),
        leverage=int(data.get("leverage", 100)),
        model=data.get("model", "open_prices"),
        parameters=data.get("parameters", {}),
        optimize_enabled=optimize_section.get("enabled", False),
        optimize_criterion=optimize_section.get("criterion", "profit_factor"),
        optimize_parameters=opt_params,
        report_dir=data.get("report_dir", "results"),
        report_name=data.get("report_name", ""),
    )


def _find_mt5_path() -> str:
    """MT5のデフォルトインストールパスを探す。"""
    candidates = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    ]
    # AppData\Roaming 配下のブローカーフォルダを再帰的に検索
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        roaming = Path(appdata)
        if roaming.exists():
            for child in roaming.iterdir():
                if not child.is_dir():
                    continue
                exe = child / "terminal64.exe"
                if exe.exists():
                    candidates.insert(0, str(exe))

    # Program Files配下も検索
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        base_path = Path(base)
        if base_path.exists():
            for child in base_path.iterdir():
                if not child.is_dir():
                    continue
                if "metatrader" in child.name.lower() or "mt5" in child.name.lower():
                    exe = child / "terminal64.exe"
                    if exe.exists():
                        candidates.append(str(exe))

    for path in candidates:
        if os.path.exists(path):
            return path

    return r"C:\Program Files\MetaTrader 5\terminal64.exe"


def find_all_mt5_paths() -> list[str]:
    """インストール済みのMT5ターミナルを全て検索して返す。"""
    found: list[str] = []

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        roaming = Path(appdata)
        if roaming.exists():
            for child in roaming.iterdir():
                if not child.is_dir():
                    continue
                exe = child / "terminal64.exe"
                if exe.exists():
                    found.append(str(exe))

    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        base_path = Path(base)
        if base_path.exists():
            for child in base_path.iterdir():
                if not child.is_dir():
                    continue
                if "metatrader" in child.name.lower() or "mt5" in child.name.lower():
                    exe = child / "terminal64.exe"
                    if exe.exists() and str(exe) not in found:
                        found.append(str(exe))

    return found
