"""バックテスト結果の可視化（matplotlib）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd


def _setup_font() -> None:
    """日本語フォントを設定する。Windowsのフォントを優先的に使用。"""
    jp_candidates = [
        "Yu Gothic", "Meiryo", "MS Gothic", "Noto Sans CJK JP",
        "IPAexGothic", "TakaoGothic", "VL Gothic",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in jp_candidates:
        if font in available:
            matplotlib.rcParams["font.family"] = font
            return
    # フォントが見つからない場合は日本語ラベルを英語に切り替えるフラグを立てる
    matplotlib.rcParams["axes.unicode_minus"] = False


_setup_font()

from .parser import BacktestResult


def generate_charts(result: BacktestResult, output_dir: Path) -> list[Path]:
    """全チャートを生成してパスリストを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    if not result.trades.empty:
        p = _plot_balance_curve(result, output_dir)
        if p:
            paths.append(p)
        p = _plot_drawdown(result, output_dir)
        if p:
            paths.append(p)
        p = _plot_profit_distribution(result, output_dir)
        if p:
            paths.append(p)

    if not result.optimization_results.empty:
        p = _plot_optimization_heatmap(result, output_dir)
        if p:
            paths.append(p)

    return paths


def _plot_balance_curve(result: BacktestResult, out: Path) -> Optional[Path]:
    """残高推移チャートを生成する。"""
    df = result.trades
    balance_col = _find_col(df, ["balance", "残高"])
    time_col = _find_col(df, ["time", "time", "日時"])
    if not balance_col:
        return None

    fig, ax = plt.subplots(figsize=(12, 5))
    x = df[time_col] if time_col else range(len(df))
    ax.plot(x, df[balance_col], linewidth=1.5, color="#2196F3", label="残高")
    ax.fill_between(x, df[balance_col], alpha=0.1, color="#2196F3")
    ax.set_title("残高推移", fontsize=14, fontweight="bold")
    ax.set_xlabel("取引")
    ax.set_ylabel("残高")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    path = out / "balance_curve.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_drawdown(result: BacktestResult, out: Path) -> Optional[Path]:
    """ドローダウンチャートを生成する。"""
    df = result.trades
    balance_col = _find_col(df, ["balance", "残高"])
    if not balance_col:
        return None

    balance = pd.to_numeric(df[balance_col], errors="coerce").ffill()
    peak = balance.cummax()
    dd = (balance - peak) / peak * 100

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(range(len(dd)), dd, 0, alpha=0.5, color="#F44336", label="ドローダウン%")
    ax.set_title("ドローダウン推移", fontsize=14, fontweight="bold")
    ax.set_xlabel("取引")
    ax.set_ylabel("ドローダウン (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    path = out / "drawdown.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_profit_distribution(result: BacktestResult, out: Path) -> Optional[Path]:
    """損益分布のヒストグラムを生成する。"""
    df = result.trades
    profit_col = _find_col(df, ["profit", "損益", "Profit"])
    if not profit_col:
        return None

    profits = pd.to_numeric(df[profit_col], errors="coerce").dropna()
    profits = profits[profits != 0]

    if profits.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    bins = min(50, max(10, len(profits) // 5))
    colors = ["#4CAF50" if v >= 0 else "#F44336" for v in profits]
    n, bins_arr, patches = ax.hist(profits, bins=bins, edgecolor="white", linewidth=0.5)
    for patch, color in zip(patches, ["#4CAF50" if b >= 0 else "#F44336" for b in bins_arr[:-1]]):
        patch.set_facecolor(color)

    ax.axvline(0, color="black", linewidth=1.5, linestyle="--")
    ax.axvline(profits.mean(), color="#FF9800", linewidth=1.5, linestyle="-", label=f"平均: {profits.mean():.2f}")
    ax.set_title("損益分布", fontsize=14, fontweight="bold")
    ax.set_xlabel("損益")
    ax.set_ylabel("取引回数")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()

    path = out / "profit_distribution.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_optimization_heatmap(result: BacktestResult, out: Path) -> Optional[Path]:
    """最適化結果のヒートマップを生成する。"""
    df = result.optimization_results
    if df.shape[1] < 3:
        return None

    # 数値列を特定
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 3:
        return None

    param_cols = numeric_cols[:-1]
    metric_col = numeric_cols[-1]

    if len(param_cols) >= 2:
        try:
            pivot = df.pivot_table(
                index=param_cols[0],
                columns=param_cols[1],
                values=metric_col,
                aggfunc="max",
            )
            fig, ax = plt.subplots(figsize=(10, 8))
            im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn")
            ax.set_xticks(range(len(pivot.columns)))
            ax.set_xticklabels([f"{v:.4g}" for v in pivot.columns], rotation=45)
            ax.set_yticks(range(len(pivot.index)))
            ax.set_yticklabels([f"{v:.4g}" for v in pivot.index])
            ax.set_xlabel(param_cols[1])
            ax.set_ylabel(param_cols[0])
            ax.set_title(f"最適化ヒートマップ ({metric_col})", fontsize=14, fontweight="bold")
            plt.colorbar(im, ax=ax)
            plt.tight_layout()

            path = out / "optimization_heatmap.png"
            fig.savefig(path, dpi=120, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception:
            pass

    return None


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """列名の候補リストからDataFrameの列名を探す。"""
    lower_cols = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_cols:
            return lower_cols[c.lower()]
    return None
