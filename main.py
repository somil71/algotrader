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
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Main")

portfolio = PortfolioManager()
scanner = TechnicalScanner()
planner = CustomOrderPlanner()
broker = KotakNeoBroker()
broker.initialize()

async def monitor_positions_job(context):
    """Checks open positions for SL/Target AND monitors Father's planned watch orders."""
    active_positions = portfolio.state.get("active_positions", {})
    pending_planned = planner.get_pending_orders()

    tickers_to_check = set(active_positions.keys())
    for p in pending_planned:
        tickers_to_check.add(p["ticker"])

    if not tickers_to_check:
        return

    tickers = list(tickers_to_check)
    try:
        data = yf.download(tickers, period="1d", interval="1m", progress=False)
        current_prices = {}
        if len(tickers) == 1:
            ticker = tickers[0]
            if not data.empty and "Close" in data:
                close_val = data["Close"]
                current_prices[ticker] = float(close_val.values[-1]) if hasattr(close_val, 'values') else float(close_val.iloc[-1])
        else:
            for t in tickers:
                if t in data["Close"]:
                    series = data["Close"][t].dropna()
                    if not series.empty:
                        current_prices[t] = float(series.iloc[-1])

        # 1. Check Exit Triggers for open positions
        closed_trades = portfolio.check_exits(current_prices)
        if closed_trades and config.TELEGRAM_CHAT_ID:
            for trade in closed_trades:
                pnl = trade["pnl"]
                icon = "🎯" if "Target" in trade["reason"] else "🛑"
                alert_text = (
                    f"{icon} <b>TRADE EXIT NOTIFICATION</b>\n\n"
                    f"Stock: <b>{trade['ticker'].replace('.NS', '')}</b>\n"
                    f"Result: <b>{trade['reason']}</b>\n"
                    f"Exit Price: ₹{trade['exit_price']:,.2f}\n"
                    f"Profit/Loss: <b>₹{pnl:+,.2f} ({trade['pnl_pct']:+.2f}%)</b>\n"
                    f"Quantity: {trade['quantity']} shares"
                )
                await context.bot.send_message(
                    chat_id=int(config.TELEGRAM_CHAT_ID),
                    text=alert_text,
                    parse_mode="HTML"
                )

        # 2. Check Custom Planned Orders
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
                    "risk_pct_of_capital": round((plan["quantity"] * (plan["triggered_price"] - plan["stop_loss"]) / config.INITIAL_CAPITAL) * 100, 2),
                    "reason": f"Stock reached your planned trigger price of ₹{plan['trigger_price']}!"
                }
                if algo_bot:
                    await algo_bot.send_signal_alert(context.bot, int(config.TELEGRAM_CHAT_ID), sig)

    except Exception as e:
        logger.error(f"Error in monitor_positions_job: {e}")

async def scheduled_scanner_job(context):
    """Runs periodic scan during trading hours."""
    now = datetime.now()
    current_time_val = now.hour * 60 + now.minute
    market_start = config.MARKET_OPEN_HOUR * 60 + config.MARKET_OPEN_MINUTE
    market_end = config.MARKET_CLOSE_HOUR * 60 + config.MARKET_CLOSE_MINUTE

    if not (market_start <= current_time_val <= market_end):
        logger.info("Outside market hours. Skipping scheduled scan.")
        return

    logger.info("Starting scheduled market scan...")
    summary = portfolio.get_summary()
    signals = scanner.scan_all(
        available_cash=summary["cash_balance"],
        total_capital=summary["initial_capital"],
        active_tickers=list(summary["active_positions"].keys())
    )

    if signals and config.TELEGRAM_CHAT_ID:
        for sig in signals:
            # Send signal card via bot
            algo_bot = context.application.bot_data.get("algo_bot")
            if algo_bot:
                await algo_bot.send_signal_alert(context.bot, int(config.TELEGRAM_CHAT_ID), sig)

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

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        print("\n" + "="*60)
        print("⚠️  TELEGRAM_BOT_TOKEN NOT CONFIGURED!")
        print("Please check your .env file.")
        print("="*60 + "\n")
        return

    algo_bot = AlgoTelegramBot(portfolio, scanner, broker)
    app = algo_bot.build_application()
    app.bot_data["algo_bot"] = algo_bot

    # Set up background jobs
    if app.job_queue:
        app.job_queue.run_repeating(monitor_positions_job, interval=120, first=10)
        app.job_queue.run_repeating(scheduled_scanner_job, interval=1800, first=60)
        logger.info("JobQueue scheduled: position monitor (2m) and market scanner (30m).")

    # Start background cloud health-check server if deployed to cloud (Render, Railway, etc.)
    threading.Thread(target=start_health_server, daemon=True).start()

    logger.info("🚀 AlgoTrader Bot is online and listening for Telegram commands!")
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
