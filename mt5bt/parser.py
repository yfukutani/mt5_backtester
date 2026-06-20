"""MT5バックテストレポート（XML/HTML）のパーサー。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree
import pandas as pd


@dataclass
class BacktestResult:
    """バックテスト結果のデータクラス。"""

    # サマリー統計
    expert: str = ""
    symbol: str = ""
    period: str = ""
    from_date: str = ""
    to_date: str = ""
    deposit: float = 0.0

    # 収益指標
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    expected_payoff: float = 0.0
    sharpe_ratio: float = 0.0

    # ドローダウン
    max_dd_abs: float = 0.0
    max_dd_pct: float = 0.0
    relative_dd_abs: float = 0.0
    relative_dd_pct: float = 0.0

    # 取引統計
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 最終残高
    final_balance: float = 0.0

    # 取引履歴（DataFrame）
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)

    # 最適化結果（複数パスの場合）
    optimization_results: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def recovery_factor(self) -> float:
        if self.max_dd_abs == 0:
            return 0.0
        return self.net_profit / self.max_dd_abs


def parse_report(report_path: Path) -> BacktestResult:
    """MT5レポートファイルを解析する。XMLとHTMLの両方に対応。"""
    suffix = report_path.suffix.lower()
    content = report_path.read_bytes()

    # UTF-16でも検索できるようにデコードして判定
    decoded = ""
    for enc in ("utf-16", "utf-8", "cp1252"):
        try:
            decoded = content.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            pass

    is_xml = (
        suffix == ".xml"
        or "<?xml" in decoded[:200]
        or "<Report>" in decoded
        or "<optimization>" in decoded.lower()
        or "<results>" in decoded.lower()
    )

    if is_xml:
        return _parse_xml(report_path)

    return _parse_html(content)


def _parse_xml(path: Path) -> BacktestResult:
    """XMLフォーマットのレポートを解析する。"""
    result = BacktestResult()

    # MT5は UTF-16 / UTF-8 両方出力するため、バイト列として読み込む
    raw = path.read_bytes()
    # lxmlはencoding宣言とバイト列が食い違う場合があるので strip
    parser = etree.XMLParser(recover=True, encoding=None)
    try:
        tree = etree.fromstring(raw, parser=parser)
        tree = tree.getroottree()
    except Exception:
        tree = etree.parse(str(path))
    root = tree.getroot()

    # サマリーセクション
    summary = root.find(".//summary")
    if summary is None:
        summary = root.find(".//Report")
    if summary is not None:
        _extract_summary_xml(summary, result)

    # 取引履歴
    trades_data = []
    for deal in root.findall(".//Deal") or root.findall(".//deal"):
        trade = {
            "time": deal.get("time", ""),
            "symbol": deal.get("symbol", ""),
            "type": deal.get("type", ""),
            "volume": _safe_float(deal.get("volume", "0")),
            "price": _safe_float(deal.get("price", "0")),
            "profit": _safe_float(deal.get("profit", "0")),
            "balance": _safe_float(deal.get("balance", "0")),
            "comment": deal.get("comment", ""),
        }
        trades_data.append(trade)

    if trades_data:
        result.trades = pd.DataFrame(trades_data)

    # 最適化結果
    opt_rows = []
    for row in root.findall(".//Row") or root.findall(".//row"):
        opt_rows.append({attr: row.get(attr, "") for attr in row.keys()})

    if opt_rows:
        result.optimization_results = pd.DataFrame(opt_rows)

    return result


def _extract_summary_xml(node: etree._Element, result: BacktestResult) -> None:
    """XMLサマリーノードから統計値を抽出する。"""
    mapping = {
        "NetProfit": ("net_profit", float),
        "GrossProfit": ("gross_profit", float),
        "GrossLoss": ("gross_loss", float),
        "ProfitFactor": ("profit_factor", float),
        "ExpectedPayoff": ("expected_payoff", float),
        "SharpeRatio": ("sharpe_ratio", float),
        "MaxDrawdown": ("max_dd_abs", float),
        "MaxDrawdownPercent": ("max_dd_pct", float),
        "TotalTrades": ("total_trades", int),
        "WinTrades": ("win_trades", int),
        "LossTrades": ("loss_trades", int),
        "FinalBalance": ("final_balance", float),
    }
    for xml_key, (attr, conv) in mapping.items():
        el = node.find(xml_key)
        if el is not None and el.text:
            try:
                setattr(result, attr, conv(el.text.replace(",", "").replace(" ", "")))
            except (ValueError, TypeError):
                pass

    if result.total_trades > 0:
        result.win_rate = result.win_trades / result.total_trades * 100


def _parse_html(content: bytes) -> BacktestResult:
    """HTMLフォーマットのレポートを解析する。"""
    result = BacktestResult()

    # エンコーディング検出（MT5は通常UTF-16）
    for enc in ("utf-16", "utf-8", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            text = ""

    if not text:
        return result

    # 正規表現でキー・バリューペアを抽出
    patterns = {
        "net_profit": r"Net profit[:\s]+(-?[\d,\.]+)",
        "gross_profit": r"Gross profit[:\s]+(-?[\d,\.]+)",
        "gross_loss": r"Gross loss[:\s]+(-?[\d,\.]+)",
        "profit_factor": r"Profit factor[:\s]+([\d,\.]+)",
        "expected_payoff": r"Expected payoff[:\s]+(-?[\d,\.]+)",
        "sharpe_ratio": r"Sharpe Ratio[:\s]+([\d,\.]+)",
        "max_dd_abs": r"Maximal drawdown[:\s]+([\d,\.]+)",
        "max_dd_pct": r"Maximal drawdown[:\s]+[\d,\.]+ \(([\d,\.]+)%\)",
        "total_trades": r"Total trades[:\s]+(\d+)",
        "win_trades": r"Short positions \(won %\)[:\s]+\d+ \([\d\.]+%\).*?(\d+) \(",
        "final_balance": r"Balance[:\s]+([\d,\.]+)",
    }

    for attr, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                if attr in ("total_trades", "win_trades", "loss_trades"):
                    setattr(result, attr, int(raw))
                else:
                    setattr(result, attr, float(raw))
            except ValueError:
                pass

    # pandasでテーブル抽出
    try:
        tables = pd.read_html(text)
        for tbl in tables:
            cols = [str(c).lower() for c in tbl.columns]
            if any("profit" in c or "balance" in c for c in cols):
                result.trades = tbl
                break
    except Exception:
        pass

    if result.total_trades > 0 and result.win_trades > 0:
        result.win_rate = result.win_trades / result.total_trades * 100

    return result


def _safe_float(value: str) -> float:
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0
