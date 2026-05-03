"""
Rich CLI dashboard.
- Interactive terminal (TTY): renders a full live-updating Rich table.
- Headless / cloud deployment (no TTY): prints a compact plain-text
  summary line per scan cycle so Railway/cloud log viewers stay readable.
"""

from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings

# When deployed on Railway/Docker there is no TTY — isatty() returns False.
_IS_TTY = sys.stdout.isatty()

console = Console()


def _pnl_color(value: float) -> str:
    return "green" if value >= 0 else "red"


def _render_headless(paper_trader, portfolio_stats, last_signals, current_prices):
    """Single-line summary per scan cycle — readable in Railway log viewer."""
    summary     = paper_trader.summary(current_prices)
    top_signals = sorted(last_signals, key=lambda x: x["composite_score"], reverse=True)[:5]
    signal_str  = " | ".join(
        f"{s['symbol']} {s['action']} score={s['composite_score']:.0f}"
        for s in top_signals
    ) or "none"

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SCAN COMPLETE"
        f" | mode={settings.MODE.upper()}"
        f" | balance=INR {summary['balance_inr']:,.2f}"
        f" | portfolio=INR {summary['portfolio_value']:,.2f}"
        f" | total_pnl=INR {summary['total_pnl']:+,.2f}"
        f" | daily_pnl=INR {summary['daily_pnl']:+,.2f}"
        f" | open_positions={summary['open_positions']}"
        f" | total_trades={summary['total_trades']}"
        f" | win_rate={portfolio_stats.get('win_rate', 0):.1f}%"
        f" | top_signals=[{signal_str}]",
        flush=True,
    )


def render(
    paper_trader,
    portfolio_stats: dict,
    last_signals: list[dict],
    current_prices: dict[str, float],
):
    """
    Render one frame. Automatically selects rich table (TTY) or plain
    log line (headless / Railway / Docker).
    """
    if not _IS_TTY:
        _render_headless(paper_trader, portfolio_stats, last_signals, current_prices)
        return

    console.clear()

    # ── Header ─────────────────────────────────────────────────────────────
    mode_tag = "[bold red]LIVE[/bold red]" if settings.LIVE else "[bold yellow]PAPER[/bold yellow]"
    console.print(
        Panel(
            f"[bold cyan]CrypSavvy[/bold cyan]  |  Mode: {mode_tag}  |  "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            expand=False,
        )
    )

    # ── Portfolio Summary ───────────────────────────────────────────────────
    summary = paper_trader.summary(current_prices)
    total_pnl_color = _pnl_color(summary["total_pnl"])
    daily_pnl_color = _pnl_color(summary["daily_pnl"])

    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column(style="bold")
    stats_table.add_column()
    stats_table.add_row("Balance",       f"₹{summary['balance_inr']:,.2f}")
    stats_table.add_row("Portfolio",     f"₹{summary['portfolio_value']:,.2f}")
    stats_table.add_row(
        "Total P&L",
        f"[{total_pnl_color}]₹{summary['total_pnl']:+,.2f}[/{total_pnl_color}]",
    )
    stats_table.add_row(
        "Daily P&L",
        f"[{daily_pnl_color}]₹{summary['daily_pnl']:+,.2f}[/{daily_pnl_color}]",
    )
    stats_table.add_row("Open Positions", str(summary["open_positions"]))
    stats_table.add_row("Total Trades",  str(summary["total_trades"]))

    db_stats_table = Table(show_header=False, box=None, padding=(0, 2))
    db_stats_table.add_column(style="bold")
    db_stats_table.add_column()
    db_stats_table.add_row("Wins",        str(portfolio_stats.get("wins", 0)))
    db_stats_table.add_row("Losses",      str(portfolio_stats.get("losses", 0)))
    db_stats_table.add_row("Win Rate",    f"{portfolio_stats.get('win_rate', 0):.1f}%")
    db_stats_table.add_row("Avg P&L%",    f"{portfolio_stats.get('avg_pnl_pct', 0):+.2f}%")
    db_stats_table.add_row("Best Trade",  f"{portfolio_stats.get('best_trade_pct', 0):+.2f}%")
    db_stats_table.add_row("Worst Trade", f"{portfolio_stats.get('worst_trade_pct', 0):+.2f}%")

    console.print(Columns([
        Panel(stats_table,    title="[bold]Portfolio[/bold]"),
        Panel(db_stats_table, title="[bold]Performance[/bold]"),
    ]))

    # ── Open Positions ──────────────────────────────────────────────────────
    if paper_trader.positions:
        pos_table = Table(title="Open Positions", show_lines=True)
        pos_table.add_column("Symbol",       style="cyan")
        pos_table.add_column("Entry Price",  justify="right")
        pos_table.add_column("Current",      justify="right")
        pos_table.add_column("Unrealised P&L", justify="right")
        pos_table.add_column("Stop Loss",    justify="right")
        pos_table.add_column("Take Profit",  justify="right")

        for sym, pos in paper_trader.positions.items():
            cur  = current_prices.get(sym, pos.entry_price)
            upnl = (cur - pos.entry_price) / pos.entry_price * 100
            color = _pnl_color(upnl)
            pos_table.add_row(
                sym,
                f"₹{pos.entry_price:,.4f}",
                f"₹{cur:,.4f}",
                f"[{color}]{upnl:+.2f}%[/{color}]",
                f"₹{pos.stop_loss:,.4f}",
                f"₹{pos.take_profit:,.4f}",
            )
        console.print(pos_table)

    # ── Last Scan Signals ───────────────────────────────────────────────────
    if last_signals:
        sig_table = Table(title="Last Scan — Top Signals", show_lines=True)
        sig_table.add_column("Symbol",    style="cyan")
        sig_table.add_column("Action",    justify="center")
        sig_table.add_column("Score",     justify="right")
        sig_table.add_column("Technical", justify="right")
        sig_table.add_column("Sentiment", justify="right")
        sig_table.add_column("RSI",       justify="right")

        for s in sorted(last_signals, key=lambda x: x["composite_score"], reverse=True):
            action = s["action"]
            action_style = {
                "BUY":  "[bold green]BUY[/bold green]",
                "SELL": "[bold red]SELL[/bold red]",
                "HOLD": "[dim]HOLD[/dim]",
            }.get(action, action)

            sig_table.add_row(
                s["symbol"],
                action_style,
                f"{s['composite_score']:.1f}",
                f"{s['technical_score']:.1f}",
                f"{s['sentiment_score']:.1f}",
                str(s["details"].get("rsi_value", "-")),
            )
        console.print(sig_table)

    console.print()
