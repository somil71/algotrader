import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import config
from portfolio import PortfolioManager
from scanner import TechnicalScanner
from telegram_bot import AlgoTelegramBot
from kotak_broker import KotakNeoBroker
from order_planner import CustomOrderPlanner
from orchestrator import MultiAgentOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Main")

# ─── Core System Initialization ───────────────────────────────────────────────
portfolio = PortfolioManager()
scanner = TechnicalScanner()
planner = CustomOrderPlanner()
broker = KotakNeoBroker()
broker.initialize()

# ─── Multi-Agent Orchestrator ─────────────────────────────────────────────────
orchestrator = MultiAgentOrchestrator(portfolio=portfolio, scanner=scanner)


# ─── APScheduler Jobs (delegated to Orchestrator) ─────────────────────────────
async def monitor_positions_job(context):
    """Agent 1: Monitor open positions + planned orders every 2 minutes."""
    # Run orchestrator position monitor (Trade Monitor Agent)
    await orchestrator.job_monitor_positions(context)

    # Also check Father's custom planned orders
    active_positions = portfolio.state.get("active_positions", {})
    pending_planned = planner.get_pending_orders()
    tickers_to_check = set(active_positions.keys())
    for p in pending_planned:
        tickers_to_check.add(p["ticker"])

    if not tickers_to_check:
        return

    import yfinance as yf
    tickers = list(tickers_to_check)
    try:
        data = yf.download(tickers, period="1d", interval="1m", progress=False)
        current_prices = {}
        if len(tickers) == 1:
            ticker = tickers[0]
            if not data.empty and "Close" in data:
                close_val = data["Close"]
                current_prices[ticker] = float(close_val.values[-1])
        else:
            for t in tickers:
                if "Close" in data and t in data["Close"]:
                    series = data["Close"][t].dropna()
                    if not series.empty:
                        current_prices[t] = float(series.iloc[-1])

        # Check Father's planned trigger orders
        triggered_plans = planner.check_triggers(current_prices)
        if triggered_plans and config.TELEGRAM_CHAT_ID:
            algo_bot = context.application.bot_data.get("algo_bot")
            for plan in triggered_plans:
                sig = {
                    "ticker": plan["ticker"],
                    "symbol": plan["symbol"],
                    "strategy": "🎯 Father's Planned Watch Trigger",
                    "ltp": plan["triggered_price"],
                    "entry_price": plan["triggered_price"],
                    "stop_loss": plan["stop_loss"],
                    "target_1": plan["target_1"],
                    "target_2": plan["target_2"],
                    "target": plan["target_1"],
                    "quantity": plan["quantity"],
                    "total_investment": round(plan["quantity"] * plan["triggered_price"], 2),
                    "max_risk_amount": round(plan["quantity"] * (plan["triggered_price"] - plan["stop_loss"]), 2),
                    "risk_pct_of_capital": round(
                        (plan["quantity"] * (plan["triggered_price"] - plan["stop_loss"]) / config.INITIAL_CAPITAL) * 100, 2
                    ),
                    "reason": f"Stock reached your planned trigger price of ₹{plan['trigger_price']}!"
                }
                if algo_bot:
                    await algo_bot.send_signal_alert(context.bot, int(config.TELEGRAM_CHAT_ID), sig)

    except Exception as e:
        logger.error(f"Error in monitor_positions_job (planned orders): {e}")


async def news_global_job(context):
    """Agent 2: Morning briefing at 9 AM IST + intraday alerts every 2 hours."""
    await orchestrator.job_news_global(context)


async def scheduled_scanner_job(context):
    """Agent 3: Scan + correlation validation every 30 minutes during market hours."""
    await orchestrator.job_market_scan(context)


# ─── Cloud Health Server ───────────────────────────────────────────────────────
class CloudHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AlgoTrader Cloud Bot is Online 24/7!")

    def log_message(self, format, *args):
        return  # Suppress health check spam in console


def start_health_server():
    port = int(os.environ.get("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), CloudHealthHandler)
        logger.info(f"Cloud health-check server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Could not bind health-check server: {e}")


# ─── Main Entry Point ──────────────────────────────────────────────────────────
def main():
    if not config.TELEGRAM_BOT_TOKEN:
        print("\n" + "="*60)
        print("⚠️  TELEGRAM_BOT_TOKEN NOT CONFIGURED!")
        print("Please check your .env file.")
        print("="*60 + "\n")
        return

    algo_bot = AlgoTelegramBot(portfolio, scanner, broker, orchestrator=orchestrator)
    app = algo_bot.build_application()
    app.bot_data["algo_bot"] = algo_bot

    # Wire orchestrator → bot reference for correlation-enriched signal alerts
    orchestrator.set_bot(algo_bot)

    # ─── Schedule all 3 agent jobs ───
    if app.job_queue:
        # Agent 1: Position Monitor — every 2 minutes
        app.job_queue.run_repeating(monitor_positions_job, interval=120, first=15)

        # Agent 2: News & Global — every 2 hours (also checks for 9 AM morning briefing)
        app.job_queue.run_repeating(news_global_job, interval=7200, first=30)

        # Agent 3: Scanner + Correlation — every 30 minutes
        app.job_queue.run_repeating(scheduled_scanner_job, interval=1800, first=60)

        logger.info("✅ APScheduler: All 3 agent jobs registered.")
        logger.info("   Agent 1 — Trade Monitor:   every 2 min (starts in 15s)")
        logger.info("   Agent 2 — News & Global:   every 2 hours (starts in 30s)")
        logger.info("   Agent 3 — Scanner+Correl:  every 30 min (starts in 60s)")

    # Start background cloud health-check server
    threading.Thread(target=start_health_server, daemon=True).start()

    logger.info("🚀 AlgoTrader Multi-Agent Bot is LIVE!")
    app.run_polling()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
