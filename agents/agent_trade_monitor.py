"""
Agent 1: Trade Monitor
----------------------
Monitors all open positions every 2 minutes.
Checks Stop Loss, Target 1, Target 2, and ATR Trailing Stop.
Posts exit alerts to Telegram with 1-click confirm.
Extracted from main.py for clean orchestration.
"""

import logging
import yfinance as yf
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("TradeMonitorAgent")


@dataclass
class AgentMessage:
    """Standard message format for inter-agent communication."""
    source: str
    type: str           # "EXIT_ALERT" | "NEWS_ALERT" | "CORRELATION_ALERT" | "INFO"
    ticker: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    priority: int = 1   # 1=Low, 2=Medium, 3=High


class TradeMonitorAgent:
    """
    Agent 1: Monitors open positions for SL/Target exits.
    Runs on a 2-minute heartbeat via APScheduler.
    Posts results to the shared message queue for the orchestrator.
    """

    def __init__(self, portfolio, message_queue: List[AgentMessage]):
        self.portfolio = portfolio
        self.message_queue = message_queue
        self.name = "TradeMonitorAgent"
        logger.info(f"[{self.name}] Initialized. Watching {len(portfolio.state.get('active_positions', {}))} positions.")

    def _fetch_live_prices(self, tickers: List[str]) -> Dict[str, float]:
        """Fetch latest price for each ticker using yfinance."""
        prices = {}
        if not tickers:
            return prices
        try:
            data = yf.download(tickers, period="1d", interval="1m", progress=False)
            if len(tickers) == 1:
                ticker = tickers[0]
                if not data.empty and "Close" in data:
                    close_series = data["Close"]
                    prices[ticker] = float(close_series.values[-1])
            else:
                for t in tickers:
                    if "Close" in data and t in data["Close"]:
                        series = data["Close"][t].dropna()
                        if not series.empty:
                            prices[t] = float(series.iloc[-1])
        except Exception as e:
            logger.error(f"[{self.name}] Price fetch error: {e}")
        return prices

    async def run(self, context=None) -> List[AgentMessage]:
        """
        Main heartbeat: check all open positions.
        Returns list of AgentMessage events (exits triggered).
        Also posts to self.message_queue for orchestrator.
        """
        active_positions = self.portfolio.state.get("active_positions", {})
        if not active_positions:
            logger.debug(f"[{self.name}] No open positions to monitor.")
            return []

        tickers = list(active_positions.keys())
        logger.info(f"[{self.name}] Monitoring {len(tickers)} positions: {tickers}")

        current_prices = self._fetch_live_prices(tickers)
        if not current_prices:
            logger.warning(f"[{self.name}] Could not fetch prices. Skipping cycle.")
            return []

        # Run the portfolio exit engine
        closed_trades = self.portfolio.check_exits(current_prices)
        events = []

        for trade in closed_trades:
            pnl = trade.get("pnl", 0)
            is_win = pnl > 0
            msg = AgentMessage(
                source=self.name,
                type="EXIT_ALERT",
                ticker=trade.get("ticker", ""),
                priority=3,
                data={
                    "ticker": trade.get("ticker", ""),
                    "exit_price": trade.get("exit_price", 0),
                    "pnl": pnl,
                    "pnl_pct": trade.get("pnl_pct", 0),
                    "reason": trade.get("reason", "Exit Triggered"),
                    "quantity": trade.get("quantity", 0),
                    "is_win": is_win,
                }
            )
            events.append(msg)
            self.message_queue.append(msg)
            logger.info(f"[{self.name}] EXIT EVENT: {trade['ticker']} | P&L: ₹{pnl:.2f} | {trade['reason']}")

        # Also post current portfolio status as a low-priority heartbeat
        self.message_queue.append(AgentMessage(
            source=self.name,
            type="INFO",
            priority=1,
            data={
                "open_positions": len(active_positions),
                "prices_fetched": current_prices,
                "exits_triggered": len(closed_trades),
            }
        ))

        return events

    def format_exit_telegram_message(self, msg: AgentMessage) -> str:
        """Format an EXIT_ALERT message as a Telegram HTML string."""
        d = msg.data
        pnl = d.get("pnl", 0)
        is_win = d.get("is_win", False)
        icon = "🎯" if "Target" in d.get("reason", "") else ("🛡️" if "Trailing" in d.get("reason", "") else "🛑")
        result_icon = "✅ WIN" if is_win else "❌ LOSS"

        return (
            f"{icon} <b>POSITION EXIT — {result_icon}</b>\n\n"
            f"Stock: <b>{d.get('ticker', '').replace('.NS', '')}</b>\n"
            f"Reason: {d.get('reason', 'Exit')}\n"
            f"Exit Price: ₹{d.get('exit_price', 0):,.2f}\n"
            f"<b>P&L: ₹{pnl:+,.2f} ({d.get('pnl_pct', 0):+.2f}%)</b>\n"
            f"Quantity: {d.get('quantity', 0)} shares\n"
            f"Time: {msg.timestamp}"
        )
