"""CLIエントリポイント（clickベース）。"""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

# Windowsのコンソールがcp932の場合、Unicode文字（✓等）を出力できないため
# stdout/stderr を UTF-8 でラップする
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import click
from colorama import Fore, Style, init as colorama_init
from tabulate import tabulate

from .config import load_config, BacktestConfig, find_all_mt5_paths
from .parser import parse_report, parse_tester_csv, BacktestResult
from .reporter import generate_html_report, generate_csv_summary
from .runner import MT5Runner
from .visualizer import generate_charts

colorama_init(autoreset=True)


def _ok(msg: str) -> None:
    click.echo(Fore.GREEN + "✓ " + Style.RESET_ALL + msg)


def _info(msg: str) -> None:
    click.echo(Fore.CYAN + "→ " + Style.RESET_ALL + msg)


def _warn(msg: str) -> None:
    click.echo(Fore.YELLOW + "! " + Style.RESET_ALL + msg)


def _error(msg: str) -> None:
    click.echo(Fore.RED + "✗ " + Style.RESET_ALL + msg, err=True)


@click.group()
@click.version_option("1.0.0", prog_name="mt5bt")
def cli() -> None:
    """MT5 EA バックテスト CLI ツール。

    EAのバックテスト実行・最適化・レポート生成を自動化します。
    """


@cli.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--timeout", default=3600, show_default=True, help="タイムアウト秒数")
@click.option("--no-charts", is_flag=True, help="チャート生成をスキップ")
@click.option("--no-html", is_flag=True, help="HTMLレポート生成をスキップ")
@click.option("--no-csv", is_flag=True, help="CSVサマリー生成をスキップ")
@click.option("--open", "open_report", is_flag=True, help="完了後にブラウザで開く")
def run(
    config_file: str,
    timeout: int,
    no_charts: bool,
    no_html: bool,
    no_csv: bool,
    open_report: bool,
) -> None:
    """バックテストを実行してレポートを生成する。

    \b
    例:
      mt5bt run configs/my_ea.yaml
      mt5bt run configs/my_ea.yaml --timeout 7200 --open
    """
    _info(f"設定ファイルを読み込み中: {config_file}")
    try:
        cfg = load_config(config_file)
    except Exception as e:
        _error(f"設定ファイルの読み込みエラー: {e}")
        sys.exit(1)

    _info(f"EA: {cfg.expert} | シンボル: {cfg.symbol} | 期間: {cfg.period}")
    _info(f"テスト期間: {cfg.from_date} ～ {cfg.to_date}")

    # 出力ディレクトリの準備
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = cfg.report_name or f"{cfg.expert}_{cfg.symbol}_{ts}"
    report_dir = Path(cfg.report_dir) / run_name
    report_dir.mkdir(parents=True, exist_ok=True)

    xml_report = report_dir / "report.xml"

    # バックテスト実行
    _info("バックテストを開始します")
    runner = MT5Runner(cfg, xml_report)
    success = runner.run(timeout=timeout)

    if not success:
        _error("バックテストが失敗しました")
        _warn("MT5ターミナルのログを確認してください")
        sys.exit(1)

    _ok("バックテスト完了")

    # OnTester()が書き出した結果CSVがあればそちらを使う
    result_src = runner.result_csv_path if (runner.result_csv_path and runner.result_csv_path.exists()) else None
    _process_and_report(cfg, result_src or xml_report, report_dir, not no_charts, not no_html, not no_csv, open_report)


@cli.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--timeout", default=7200, show_default=True, help="タイムアウト秒数")
@click.option("--top", default=20, show_default=True, help="表示する上位件数")
def optimize(config_file: str, timeout: int, top: int) -> None:
    """パラメータ最適化を実行する。

    \b
    例:
      mt5bt optimize configs/my_ea.yaml --top 30
    """
    _info(f"設定ファイルを読み込み中: {config_file}")
    try:
        cfg = load_config(config_file)
    except Exception as e:
        _error(f"設定ファイルの読み込みエラー: {e}")
        sys.exit(1)

    if not cfg.optimize_parameters:
        _error("最適化パラメータが設定されていません。configのoptimize.parametersを設定してください。")
        sys.exit(1)

    _info(f"最適化対象パラメータ: {list(cfg.optimize_parameters.keys())}")
    _info(f"最適化基準: {cfg.optimize_criterion}")

    # 最適化を有効にする
    cfg.optimize_enabled = True

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = cfg.report_name or f"opt_{cfg.expert}_{cfg.symbol}_{ts}"
    report_dir = Path(cfg.report_dir) / run_name
    report_dir.mkdir(parents=True, exist_ok=True)

    xml_report = report_dir / "report.xml"

    _info("最適化を開始します（時間がかかる場合があります）")
    runner = MT5Runner(cfg, xml_report)
    success = runner.run(timeout=timeout)

    if not success or not xml_report.exists():
        _error("最適化が失敗したか、レポートが生成されませんでした")
        sys.exit(1)

    _ok("最適化完了")
    _process_and_report(cfg, xml_report, report_dir, True, True, True, False, top_n=top)


@cli.command()
@click.argument("report_file", type=click.Path(exists=True))
@click.option("--open", "open_report", is_flag=True, help="完了後にブラウザで開く")
@click.option("--no-charts", is_flag=True, help="チャート生成をスキップ")
def report(report_file: str, open_report: bool, no_charts: bool) -> None:
    """既存のMT5レポートファイルからレポートを再生成する。

    \b
    例:
      mt5bt report results/MyEA/report.xml --open
    """
    path = Path(report_file)
    report_dir = path.parent

    _info(f"レポートを解析中: {report_file}")
    try:
        result = parse_report(path)
    except Exception as e:
        _error(f"レポートの解析エラー: {e}")
        sys.exit(1)

    _ok("解析完了")
    _print_summary(result)

    chart_paths: list[Path] = []
    if not no_charts:
        _info("チャートを生成中...")
        chart_paths = generate_charts(result, report_dir / "charts")
        _ok(f"{len(chart_paths)}個のチャートを生成")

    html_path = report_dir / "report.html"
    _info(f"HTMLレポートを生成中: {html_path}")
    generate_html_report(result, html_path, chart_paths)
    _ok(f"HTMLレポート: {html_path}")

    csv_path = report_dir / "summary.csv"
    generate_csv_summary(result, csv_path)
    _ok(f"CSVサマリー: {csv_path}")

    if open_report:
        import webbrowser
        webbrowser.open(html_path.as_uri())


@cli.command("list-results")
@click.option("--dir", "results_dir", default="results", show_default=True, help="結果ディレクトリ")
def list_results(results_dir: str) -> None:
    """保存済みバックテスト結果の一覧を表示する。

    \b
    例:
      mt5bt list-results
      mt5bt list-results --dir /path/to/results
    """
    base = Path(results_dir)
    if not base.exists():
        _warn(f"ディレクトリが見つかりません: {results_dir}")
        return

    rows = []
    for run_dir in sorted(base.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        xml = run_dir / "report.xml"
        html = run_dir / "report.html"
        if xml.exists():
            try:
                result = parse_report(xml)
                rows.append([
                    run_dir.name,
                    result.expert or "-",
                    result.symbol or "-",
                    f"{result.net_profit:,.2f}",
                    f"{result.profit_factor:.2f}",
                    f"{result.max_dd_pct:.1f}%",
                    f"{result.win_rate:.1f}%",
                    str(result.total_trades),
                    "✓" if html.exists() else "-",
                ])
            except Exception:
                rows.append([run_dir.name, "解析エラー", "-", "-", "-", "-", "-", "-", "-"])

    if not rows:
        _warn("結果が見つかりません")
        return

    headers = ["実行名", "EA", "シンボル", "純利益", "PF", "最大DD", "勝率", "取引数", "HTML"]
    click.echo(tabulate(rows, headers=headers, tablefmt="rounded_outline"))


@cli.command("list-terminals")
def list_terminals() -> None:
    """インストール済みのMT5ターミナルを一覧表示する。

    \b
    例:
      mt5bt list-terminals
    """
    paths = find_all_mt5_paths()
    if not paths:
        _warn("MT5ターミナルが見つかりませんでした")
        return

    _ok(f"{len(paths)}個のMT5ターミナルを検出:")
    for i, p in enumerate(paths, 1):
        click.echo(f"  {i}. {p}")


@cli.command("compare")
@click.argument("report_files", nargs=-1, type=click.Path(exists=True), required=True)
def compare(report_files: tuple[str, ...]) -> None:
    """複数のバックテスト結果を比較する。

    \b
    例:
      mt5bt compare results/run1/report.xml results/run2/report.xml
    """
    rows = []
    for rf in report_files:
        path = Path(rf)
        try:
            r = parse_report(path)
            rows.append([
                path.parent.name,
                r.expert or "-",
                r.symbol or "-",
                f"{r.net_profit:,.2f}",
                f"{r.profit_factor:.2f}",
                f"{r.max_dd_pct:.1f}%",
                f"{r.win_rate:.1f}%",
                str(r.total_trades),
                f"{r.sharpe_ratio:.2f}",
                f"{r.recovery_factor:.2f}",
            ])
        except Exception as e:
            _warn(f"{rf}: 解析失敗 ({e})")

    if not rows:
        _error("比較できる結果がありません")
        sys.exit(1)

    headers = ["実行名", "EA", "シンボル", "純利益", "PF", "最大DD", "勝率", "取引数", "シャープ", "RF"]
    click.echo(tabulate(rows, headers=headers, tablefmt="rounded_outline"))


@cli.command("portfolio")
@click.argument("config_files", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--timeout", default=1800, show_default=True, help="各バックテストのタイムアウト秒数")
def portfolio(config_files: tuple[str, ...], timeout: int) -> None:
    """複数EA configを実行し、合算エクイティカーブから真のポートフォリオDDを算出する。

    各EAの全dealの損益を時系列で合算し、ポートフォリオ全体の最大ドローダウン・
    純利益を計算する。各EAは自前の配分資金（deposit）を持つ独立サブ口座として扱い、
    合計資金に対するDDを出す。低相関なEAほどポートフォリオDDが単独DDの和より小さくなる。

    \b
    例:
      mt5bt portfolio configs/pullback_usdjpy_h4.yaml configs/pullback_gbpjpy_h4.yaml \\
                      configs/pairtrade_eurusd_gbpusd.yaml
    """
    import pandas as pd

    def _curve_dd(deposit: float, df: "pd.DataFrame") -> tuple[float, float]:
        s = df.sort_values("time")["profit"].cumsum() + deposit
        eq = pd.concat([pd.Series([deposit]), s], ignore_index=True)
        rm = eq.cummax()
        d = rm - eq
        return float(d.max()), float((d / rm).max() * 100)

    legs: list[tuple[str, float, "pd.DataFrame"]] = []
    total_deposit = 0.0

    for i, cf in enumerate(config_files):
        try:
            cfg = load_config(cf)
        except Exception as e:
            _error(f"設定読み込みエラー {cf}: {e}")
            sys.exit(1)

        eq_name = f"pf_eq_{i}.csv"
        cfg.parameters["EquityLogFile"] = eq_name
        name = cfg.report_name or f"{cfg.expert}_{cfg.symbol}_{i}"
        _info(f"[{i + 1}/{len(config_files)}] {name} を実行中...")

        report_dir = Path(cfg.report_dir) / f"_portfolio_{i}"
        report_dir.mkdir(parents=True, exist_ok=True)
        runner = MT5Runner(cfg, report_dir / "report.xml")

        eq_candidates = [d / eq_name for d in runner._tester_files_dirs]
        if runner.mql5_files_dir:
            eq_candidates.append(runner.mql5_files_dir / eq_name)
        for p in eq_candidates:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

        if not runner.run(timeout=timeout):
            _error(f"{name} のバックテストが失敗しました")
            sys.exit(1)

        eq_path = next((p for p in eq_candidates if p.exists() and p.stat().st_size > 0), None)
        if eq_path is None:
            _error(f"{name} のエクイティログが見つかりません。EAが最新版（EquityLogFile対応）か確認してください。")
            sys.exit(1)

        df = pd.read_csv(eq_path)
        df.columns = [c.strip().lower() for c in df.columns]
        df["time"] = pd.to_numeric(df["time"], errors="coerce")
        df["profit"] = pd.to_numeric(df["profit"], errors="coerce")
        df = df.dropna(subset=["time", "profit"])
        legs.append((name, cfg.deposit, df))
        total_deposit += cfg.deposit
        _ok(f"{name}: {len(df)} deals / 純利益 {df['profit'].sum():,.0f}")

    if not legs:
        _error("有効なEAがありません")
        sys.exit(1)

    # 合算エクイティカーブ（全dealを時系列でプール）
    all_deals = pd.concat([leg[2][["time", "profit"]] for leg in legs], ignore_index=True)
    all_deals = all_deals.sort_values("time").reset_index(drop=True)
    equity = pd.concat([pd.Series([total_deposit]),
                        total_deposit + all_deals["profit"].cumsum()], ignore_index=True)
    running_max = equity.cummax()
    dd_series = running_max - equity
    max_dd_abs = float(dd_series.max())
    max_dd_pct = float((dd_series / running_max).max() * 100)
    net = float(all_deals["profit"].sum())

    # 各EA単独のDD（分散効果の比較用）
    single_dds = [_curve_dd(dep, df)[0] for (_, dep, df) in legs]
    sum_single_dd = sum(single_dds)

    click.echo("")
    click.echo(Fore.CYAN + Style.BRIGHT + "━━━━━━ ポートフォリオ合算結果 ━━━━━━" + Style.RESET_ALL)
    leg_rows = []
    for (n, dep, df), sdd in zip(legs, single_dds):
        leg_rows.append([n, f"{dep:,.0f}", len(df), f"{df['profit'].sum():,.0f}", f"{sdd:,.0f}"])
    click.echo(tabulate(leg_rows, headers=["EA", "配分資金", "取引数", "純利益", "単独DD(額)"],
                        tablefmt="rounded_outline"))
    click.echo("")

    net_color = (Fore.GREEN if net >= 0 else Fore.RED) + f"{net:,.0f}" + Style.RESET_ALL
    div_effect = "-"
    if sum_single_dd > 0:
        div_effect = (Fore.GREEN + f"-{sum_single_dd - max_dd_abs:,.0f}"
                      f"（{(1 - max_dd_abs / sum_single_dd) * 100:.0f}%減）" + Style.RESET_ALL)
    summary = [
        ["合計配分資金",        f"{total_deposit:,.0f}"],
        ["ポートフォリオ純利益", net_color],
        ["最大DD（額）",        Fore.RED + f"{max_dd_abs:,.0f}" + Style.RESET_ALL],
        ["最大DD（%）",         Fore.RED + f"{max_dd_pct:.2f}%" + Style.RESET_ALL],
        ["リターン/最大DD",     f"{(net / max_dd_abs):.2f}" if max_dd_abs else "-"],
        ["単独DDの単純和",      f"{sum_single_dd:,.0f}"],
        ["分散効果（DD削減）",   div_effect],
    ]
    click.echo(tabulate(summary, tablefmt="plain"))
    click.echo("")


def _process_and_report(
    cfg: BacktestConfig,
    source_path: Path,
    report_dir: Path,
    make_charts: bool,
    make_html: bool,
    make_csv: bool,
    open_report: bool,
    top_n: int = 20,
) -> None:
    """レポート解析・チャート生成・HTML出力をまとめて行う。"""
    _info(f"結果を解析中: {source_path.name}")
    try:
        # OnTester CSVとXML/HTMLを自動判別
        if source_path.suffix.lower() == ".csv":
            result = parse_tester_csv(source_path)
        else:
            result = parse_report(source_path)
        result.expert    = result.expert    or cfg.expert
        result.symbol    = result.symbol    or cfg.symbol
        result.period    = result.period    or cfg.period
        result.from_date = result.from_date or cfg.from_date
        result.to_date   = result.to_date   or cfg.to_date
        result.deposit   = result.deposit   or cfg.deposit
    except Exception as e:
        _error(f"結果解析エラー: {e}")
        return

    _print_summary(result)

    chart_paths: list[Path] = []
    if make_charts:
        _info("チャートを生成中...")
        chart_paths = generate_charts(result, report_dir / "charts")
        if chart_paths:
            _ok(f"{len(chart_paths)}個のチャートを生成")

    if make_html:
        html_path = report_dir / "report.html"
        generate_html_report(result, html_path, chart_paths)
        _ok(f"HTMLレポート: {html_path}")
        if open_report:
            import webbrowser
            webbrowser.open(html_path.as_uri())

    if make_csv:
        csv_path = report_dir / "summary.csv"
        generate_csv_summary(result, csv_path)
        _ok(f"CSVサマリー: {csv_path}")

    if not result.optimization_results.empty:
        _info(f"最適化結果 上位{top_n}件:")
        df = result.optimization_results
        numeric = df.select_dtypes(include="number").columns
        if len(numeric) > 0:
            df = df.sort_values(by=numeric[-1], ascending=False)
        click.echo(tabulate(df.head(top_n).values, headers=list(df.columns), tablefmt="rounded_outline", floatfmt=".4f"))


def _print_summary(result: BacktestResult) -> None:
    """コンソールにサマリーを表示する。"""
    click.echo("")
    click.echo(Fore.CYAN + Style.BRIGHT + "━━━━━━ バックテスト結果サマリー ━━━━━━" + Style.RESET_ALL)

    def color_val(v: float, positive_good: bool = True) -> str:
        if positive_good:
            c = Fore.GREEN if v >= 0 else Fore.RED
        else:
            c = Fore.GREEN if v <= 0 else Fore.RED
        return c + f"{v:,.2f}" + Style.RESET_ALL

    rows = [
        ["純利益",              color_val(result.net_profit)],
        ["プロフィットファクター", Fore.GREEN + f"{result.profit_factor:.2f}" + Style.RESET_ALL if result.profit_factor >= 1.5 else f"{result.profit_factor:.2f}"],
        ["最大DD%",             Fore.RED + f"{result.max_dd_pct:.2f}%" + Style.RESET_ALL],
        ["勝率",                f"{result.win_rate:.1f}%"],
        ["総取引数",             str(result.total_trades)],
        ["シャープレシオ",       f"{result.sharpe_ratio:.2f}"],
        ["リカバリーファクター",  f"{result.recovery_factor:.2f}"],
    ]
    click.echo(tabulate(rows, tablefmt="plain"))
    click.echo("")
