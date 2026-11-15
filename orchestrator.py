"""
Master Orchestrator
--------------------
Coordinates all 3 agents:
  - Agent 1: TradeMonitorAgent   → SL/Target exits, position tracking
  - Agent 2: NewsGlobalAgent     → Macro news, global market trends
  - Agent 3: CorrelationResearchAgent → Sector peer validation

The orchestrator:
  1. Runs all agents in parallel using asyncio.gather()
  2. Manages a shared message queue for cross-agent communication
  3. Routes alerts to Telegram
  4. Runs at different intervals based on job type:
     - Position monitor: every 2 minutes (market hours only)
     - News check: every 2 hours + morning briefing at 9 AM IST
     - Correlation: on-demand when new signal arrives
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pytz

import config
from agents.agent_trade_monitor import TradeMonitorAgent, AgentMessage
from agents.agent_news_global import NewsGlobalAgent
from agents.agent_stock_research import CorrelationResearchAgent

logger = logging.getLogger("Orchestrator")

IST = pytz.timezone("Asia/Kolkata")


class MultiAgentOrchestrator:
    """
    Master coordinator for the 3-agent AlgoTrader system.
    Each agent runs independently but communicates via a shared message queue.
    """

    def __init__(self, portfolio, scanner=None, bot=None):
        self.portfolio = portfolio
        self.scanner = scanner
        self.bot = bot  # AlgoTelegramBot instance (set after build)

        # Shared message queue — all agents post here
        self.message_queue: List[AgentMessage] = []

        # Initialize the 3 agents
        self.trade_monitor = TradeMonitorAgent(portfolio, self.message_queue)
        self.news_agent = NewsGlobalAgent(self.message_queue)
        self.research_agent = CorrelationResearchAgent(self.message_queue)

        self._morning_briefing_sent_today = False
        self._last_news_check_hour = -1

        logger.info("🚀 Multi-Agent Orchestrator initialized. All 3 agents ready.")
        logger.info("   Agent 1: TradeMonitorAgent  → Position SL/Target monitor")
        logger.info("   Agent 2: NewsGlobalAgent    → Macro news + global markets")
        logger.info("   Agent 3: CorrelationAgent   → Sector peer validation")

    def set_bot(self, bot):
        """Set the Telegram bot reference after initialization."""
        self.bot = bot

    def _is_market_hours(self) -> bool:
        """Check if current IST time is within NSE market hours."""
        now = datetime.now(IST)
        market_open = now.replace(hour=config.MARKET_OPEN_HOUR, minute=config.MARKET_OPEN_MINUTE, second=0)
        market_close = now.replace(hour=config.MARKET_CLOSE_HOUR, minute=config.MARKET_CLOSE_MINUTE, second=0)
        return market_open <= now <= market_close

    def _should_send_morning_briefing(self) -> bool:
        """Send morning briefing once per day at 9:00 AM IST."""
        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        if not hasattr(self, "_briefing_date"):
            self._briefing_date = ""
        if now.hour == 9 and now.minute < 5 and self._briefing_date != today_str:
            self._briefing_date = today_str
            return True
        return False

    # ─────────────────────────────────────────────
    #  JOB 1: Position Monitor (every 2 minutes)
    # ─────────────────────────────────────────────

    async def job_monitor_positions(self, context=None):
        """
        APScheduler job: Run TradeMonitorAgent.
        Runs every 2 minutes. Posts exit alerts to Telegram.
        """
        try:
            exit_events = await self.trade_monitor.run(context)

            if exit_events and config.TELEGRAM_CHAT_ID:
                for msg in exit_events:
                    alert_text = self.trade_monitor.format_exit_telegram_message(msg)
                    await context.bot.send_message(
                        chat_id=int(config.TELEGRAM_CHAT_ID),
                        text=alert_text,
                        parse_mode="HTML"
                    )
                    logger.info(f"[Orchestrator] Sent exit alert for {msg.ticker} to Telegram.")

        except Exception as e:
            logger.error(f"[Orchestrator] job_monitor_positions error: {e}")

    # ─────────────────────────────────────────────
    #  JOB 2: News & Global Market (morning + 2h)
    # ─────────────────────────────────────────────

    async def job_news_global(self, context=None):
        """
        APScheduler job: Run NewsGlobalAgent.
        - 9:00 AM IST: Full morning briefing (news + global markets)
        - Every 2 hours: Quick intraday alert check (no news fetch)
        """
        try:
            if self._should_send_morning_briefing():
                logger.info("[Orchestrator] Sending morning briefing...")
                message, alerts = await self.news_agent.run_morning_briefing()
                if config.TELEGRAM_CHAT_ID:
                    await context.bot.send_message(
                        chat_id=int(config.TELEGRAM_CHAT_ID),
                        text=message,
                        parse_mode="HTML"
                    )
                    logger.info("[Orchestrator] Morning briefing sent.")

            else:
                # Intraday: only alert on big moves
                alert_msg, should_send = await self.news_agent.run_intraday_check()
                if should_send and config.TELEGRAM_CHAT_ID:
                    await context.bot.send_message(
                        chat_id=int(config.TELEGRAM_CHAT_ID),
                        text=alert_msg,
                        parse_mode="HTML"
                    )
                    logger.info("[Orchestrator] Intraday global alert sent.")

        except Exception as e:
            logger.error(f"[Orchestrator] job_news_global error: {e}")

    # ─────────────────────────────────────────────
    #  JOB 3: Market Scanner (every 30 minutes)
    # ─────────────────────────────────────────────

    async def job_market_scan(self, context=None):
        """
        APScheduler job: Run market scanner, then run correlation agent
        on each new signal to validate it before sending to Telegram.
        """
        if not self._is_market_hours():
            logger.info("[Orchestrator] Outside market hours. Skipping scan.")
            return

        if not self.scanner:
            logger.warning("[Orchestrator] No scanner configured.")
            return

        try:
            summary = self.portfolio.get_summary()
            signals = self.scanner.scan_all(
                available_cash=summary["cash_balance"],
                total_capital=summary["initial_capital"],
                active_tickers=list(summary["active_positions"].keys())
            )

            if not signals:
                logger.info("[Orchestrator] Scan complete. No new setups found.")
                return

            logger.info(f"[Orchestrator] Scanner found {len(signals)} signals. Running correlation validation...")

            # Run correlation agent on all signals in parallel
            correlation_tasks = [
                self.research_agent.run_for_signal(sig["ticker"])
                for sig in signals
            ]
            correlation_results = await asyncio.gather(*correlation_tasks, return_exceptions=True)

            # Send enriched signals to Telegram
            if config.TELEGRAM_CHAT_ID:
                for sig, corr_result in zip(signals, correlation_results):
                    if isinstance(corr_result, Exception):
                        logger.warning(f"[Orchestrator] Correlation failed for {sig['ticker']}: {corr_result}")
                        corr_result = None

                    # Enrich the signal with correlation verdict
                    if corr_result and isinstance(corr_result, dict):
                        sig["correlation_verdict"] = corr_result.get("verdict", "UNKNOWN")
                        sig["correlation_text"] = corr_result.get("verdict_text", "")

                    # Send via the bot's existing signal alert function
                    algo_bot = context.application.bot_data.get("algo_bot") if context else None
                    if algo_bot:
                        await algo_bot.send_signal_alert(
                            context.bot,
                            int(config.TELEGRAM_CHAT_ID),
                            sig,
                            corr_result=corr_result
                        )

        except Exception as e:
            logger.error(f"[Orchestrator] job_market_scan error: {e}")

    # ─────────────────────────────────────────────
    #  ON-DEMAND: /news command
    # ─────────────────────────────────────────────

    async def handle_news_command(self) -> str:
        """Called when user sends /news. Returns formatted Telegram message."""
        return await self.news_agent.run_on_demand()

    # ─────────────────────────────────────────────
    #  ON-DEMAND: /correlate <SYMBOL>
    # ─────────────────────────────────────────────

    async def handle_correlate_command(self, symbol: str) -> str:
        """Called when user sends /correlate INFY. Returns formatted Telegram message."""
        # Normalize ticker
        ticker = symbol.upper()
        if not ticker.endswith(".NS"):
            ticker = ticker + ".NS"
        return await self.research_agent.run_on_demand(ticker)

    # ─────────────────────────────────────────────
    #  STATUS: summary of all agents
    # ─────────────────────────────────────────────

    def get_status_report(self) -> str:
        """Returns a text status of all agents for /status command."""
        open_positions = len(self.portfolio.state.get("active_positions", {}))
        queue_size = len(self.message_queue)
        ist_now = datetime.now(IST).strftime("%d %b %Y %H:%M:%S IST")

        return (
            f"🤖 <b>Multi-Agent Orchestrator Status</b>\n\n"
            f"🕐 Time: {ist_now}\n"
            f"📊 Market Hours: {'YES ✅' if self._is_market_hours() else 'NO ⏸️'}\n\n"
            f"<b>Agent Status:</b>\n"
            f"  🔵 Agent 1 — Trade Monitor: ACTIVE (2m heartbeat)\n"
            f"  🔵 Agent 2 — News & Global: ACTIVE (morning + 2h)\n"
            f"  🔵 Agent 3 — Correlation: ACTIVE (on-demand)\n\n"
            f"<b>System Stats:</b>\n"
            f"  Open Positions: {open_positions}\n"
            f"  Message Queue: {queue_size} events\n"
            f"\n💡 <i>Use /news, /correlate SYMBOL, /scan, /portfolio</i>"
        )
