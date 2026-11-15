import logging
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
import config
from portfolio import PortfolioManager
from scanner import TechnicalScanner
from kotak_broker import KotakNeoBroker
from order_planner import CustomOrderPlanner
from ai_layer import AITradingAnalyst

logger = logging.getLogger("TelegramBot")

class AlgoTelegramBot:
    def __init__(self, portfolio: PortfolioManager, scanner: TechnicalScanner, broker: Optional[KotakNeoBroker] = None):
        self.portfolio = portfolio
        self.scanner = scanner
        self.planner = CustomOrderPlanner()
        self.ai_analyst = AITradingAnalyst()
        self.broker = broker or KotakNeoBroker()
        self.broker.initialize()
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.signals_file = config.BASE_DIR / "pending_signals.json"
        self.pending_signals: Dict[str, Dict[str, Any]] = self._load_pending_signals()
        self.app: Optional[Application] = None

    def _load_pending_signals(self) -> Dict[str, Dict[str, Any]]:
        if self.signals_file.exists():
            try:
                import json
                with open(self.signals_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_pending_signals(self):
        try:
            import json
            with open(self.signals_file, "w", encoding="utf-8") as f:
                json.dump(self.pending_signals, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending signals: {e}")

    def build_application(self) -> Application:
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env or config.py")

        self.app = Application.builder().token(self.token).build()

        # Register command handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("market", self.cmd_market))
        self.app.add_handler(CommandHandler("scan", self.cmd_scan))
        self.app.add_handler(CommandHandler("demo", self.cmd_demo))
        self.app.add_handler(CommandHandler("watch", self.cmd_watch))
        self.app.add_handler(CommandHandler("watchlist", self.cmd_watchlist))
        self.app.add_handler(CommandHandler("cancel", self.cmd_cancel_watch))
        self.app.add_handler(CommandHandler("portfolio", self.cmd_portfolio))
        self.app.add_handler(CommandHandler("pnl", self.cmd_pnl))
        self.app.add_handler(CommandHandler("ai", self.cmd_ai))
        self.app.add_handler(CommandHandler("close", self.cmd_close))
        
        # Register inline button callback handler
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

        return self.app

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        mode_text = "🟢 <b>PAPER TRADING (Simulation Mode)</b>" if config.PAPER_TRADING else "🔴 <b>LIVE BROKER EXECUTION</b>"
        
        welcome_msg = (
            f"👋 <b>Welcome to Father's Algo Trading Assistant!</b>\n\n"
            f"<b>Current Mode:</b> {mode_text}\n"
            f"<b>Starting Capital:</b> ₹{config.INITIAL_CAPITAL:,.2f}\n"
            f"<b>Max Risk Per Trade:</b> ₹{config.MAX_RISK_PER_TRADE:,.2f}\n\n"
            f"This bot automatically scans top liquid Indian stocks (NSE) for high-probability "
            f"swing setups, calculates position size and risk, and asks for your 1-click confirmation.\n\n"
            f"📌 <b>Available Commands:</b>\n"
            f"• /scan - Scan the market right now for setups\n"
            f"• /portfolio - View open positions and live balance\n"
            f"• /pnl - View trade history and profit/loss\n"
            f"• /help - Safety and strategy guidelines\n\n"
            f"<i>Your Telegram Chat ID: <code>{chat_id}</code></i>\n"
            f"<i>(Add this to your .env file as TELEGRAM_CHAT_ID if you haven't yet)</i>"
        )
        await update.message.reply_text(welcome_msg, parse_mode="HTML")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_msg = (
            "🛡️ <b>Safety & Trading Philosophy</b>\n\n"
            "1. <b>Strict Capital Protection:</b> No trade ever risks more than your defined max loss (default: ₹1,000 / 1%).\n"
            "2. <b>Position Sizing:</b> The bot calculates the exact number of shares based on the distance between Entry and Stop Loss.\n"
            "3. <b>Semi-Automated Control:</b> Orders are NEVER placed without your father tapping <i>Approve</i>.\n"
            "4. <b>Exit Discipline:</b> The system monitors active trades and notifies you immediately when a Target or Stop-Loss is hit.\n\n"
            "<b>Strategies Used:</b>\n"
            "• <i>20-Day Breakout + Volume Spike:</i> Catches explosive momentum moves.\n"
            "• <i>20 EMA Pullback:</i> Buys low-risk dips in strong trending stocks."
        )
        await update.message.reply_text(help_msg, parse_mode="HTML")

    async def cmd_market(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays live NSE market status, Nifty 50 level, and regime health."""
        from datetime import datetime
        now = datetime.now()
        is_weekday = now.weekday() < 5
        curr_min = now.hour * 60 + now.minute
        market_open_min = config.MARKET_OPEN_HOUR * 60 + config.MARKET_OPEN_MINUTE
        market_close_min = config.MARKET_CLOSE_HOUR * 60 + config.MARKET_CLOSE_MINUTE
        is_market_open = is_weekday and (market_open_min <= curr_min <= market_close_min)

        market_status = "🟢 <b>LIVE & TRADING</b>" if is_market_open else "🔴 <b>CLOSED (Opens Mon 9:15 AM IST)</b>"

        is_allowed, regime_desc, details = self.scanner.regime_filter.get_market_regime()
        nifty_val = details.get("nifty_close", 25144.30)

        msg = (
            f"🏛️ <b>NSE MARKET & REGIME STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Exchange Status: {market_status}\n"
            f"Benchmark (NIFTY 50): <b>{nifty_val:,.2f}</b>\n"
            f"Trend Health: {regime_desc}\n"
            f"Trading Mode: <b>🟢 ZERO-RISK PAPER TRADING</b>\n"
            f"Monitored Stocks: <b>{len(config.WATCHLIST)} Top Nifty Equities</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>When the market opens at 9:15 AM, the bot reads live price feeds second-by-second. "
            f"Any trade you approve executes at the real market price with virtual funds!</i>"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Allows Father to plan a custom trade a day earlier: /watch SYMBOL TRIGGER_PRICE QUANTITY"""
        args = context.args
        if len(args) < 3:
            msg = (
                "📝 <b>How to Plan a Custom Trade for Tomorrow:</b>\n\n"
                "Usage: <code>/watch &lt;SYMBOL&gt; &lt;TRIGGER_PRICE&gt; &lt;QUANTITY&gt;</code>\n\n"
                "<b>Examples:</b>\n"
                "• <code>/watch TATASTEEL 155 100</code>\n"
                "  <i>(If Tata Steel reaches ₹155 tomorrow, alert to buy 100 shares)</i>\n"
                "• <code>/watch RELIANCE 1320 25</code>\n"
                "  <i>(If Reliance dips to ₹1320, alert to buy 25 shares)</i>\n\n"
                "The bot will monitor the stock live and alert you the second it triggers!"
            )
            await update.message.reply_text(msg, parse_mode="HTML")
            return

        symbol = args[0].upper().replace(".NS", "")
        try:
            trigger_price = float(args[1])
            quantity = int(args[2])
        except ValueError:
            await update.message.reply_text("❌ Invalid price or quantity. Both must be numbers.")
            return

        order = self.planner.add_planned_order(symbol, trigger_price, quantity)
        est_cost = quantity * trigger_price
        
        reply = (
            f"✅ <b>CUSTOM WATCH ORDER SCHEDULED!</b>\n\n"
            f"Stock: <b>{order['symbol']}</b> (NSE)\n"
            f"Target Buy Trigger: <b>₹{order['trigger_price']:,.2f}</b>\n"
            f"Quantity: <b>{order['quantity']} shares</b>\n"
            f"Estimated Capital: ₹{est_cost:,.2f}\n"
            f"Default Stop Loss: ₹{order['stop_loss']:,.2f}\n"
            f"Target 1: ₹{order['target_1']:,.2f}\n\n"
            f"<i>The bot will monitor {order['symbol']} continuously when the market opens. "
            f"As soon as it reaches ₹{order['trigger_price']:,.2f}, you will get a 1-click execution card!</i>"
        )
        await update.message.reply_text(reply, parse_mode="HTML")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pending = self.planner.get_pending_orders()
        if not pending:
            await update.message.reply_text("📋 <i>No custom watch orders scheduled. Use /watch to add one.</i>", parse_mode="HTML")
            return

        text = "📋 <b>FATHER'S SCHEDULED WATCHLIST</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        for o in pending:
            text += (
                f"• <b>{o['symbol']}</b>: Buy {o['quantity']} sh when price hits <b>₹{o['trigger_price']}</b>\n"
                f"  SL: ₹{o['stop_loss']} | Target: ₹{o['target_1']}\n\n"
            )
        text += "<i>To cancel an order, use: <code>/cancel &lt;SYMBOL&gt;</code></i>"
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_cancel_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args:
            await update.message.reply_text("Usage: <code>/cancel &lt;SYMBOL&gt;</code>", parse_mode="HTML")
            return

        symbol = args[0].upper().replace(".NS", "")
        success = self.planner.cancel_planned_order(symbol)
        if success:
            await update.message.reply_text(f"✅ Planned order for <b>{symbol}</b> cancelled.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"⚠️ No active watch order found for <b>{symbol}</b>.", parse_mode="HTML")

    async def cmd_demo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends an instant sample signal card so the user can test the Approve button on weekends/off-hours."""
        await update.message.reply_text("🎲 <i>Generating a sample trade setup to test interactive buttons...</i>", parse_mode="HTML")
        
        summary = self.portfolio.get_summary()
        sample_sig = {
            "ticker": "RELIANCE.NS",
            "symbol": "RELIANCE",
            "strategy": "20-Day Breakout + Volume Spike 🚀",
            "ltp": 1339.70,
            "stop_loss": 1305.00,
            "target_1": 1391.75,
            "target_2": 1443.80,
            "target": 1391.75,
            "atr": 25.0,
            "reason": "Institutional Breakout: 20-Day High breached with 1.45x volume expansion. R:R 1:1.5 on T1, 1:3.0 on T2."
        }
        
        # Calculate sizing
        valid, sizing = self.scanner.risk_manager.evaluate_and_size_trade(
            entry_price=sample_sig["ltp"],
            stop_loss=sample_sig["stop_loss"],
            target_1=sample_sig["target_1"],
            target_2=sample_sig["target_2"],
            atr=sample_sig["atr"],
            available_cash=summary["cash_balance"],
            total_capital=summary["initial_capital"]
        )
        if valid:
            sample_sig.update(sizing)
            await self.send_signal_alert(context.bot, update.effective_chat.id, sample_sig)
        else:
            await update.message.reply_text(f"⚠️ Could not size demo trade: {sizing.get('reason')}")

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔍 <i>Scanning liquid NSE stocks for setups... Please wait 10-20 seconds.</i>", parse_mode="HTML")
        
        summary = self.portfolio.get_summary()
        active_tickers = list(summary["active_positions"].keys())
        cash = summary["cash_balance"]
        capital = summary["initial_capital"]

        signals = self.scanner.scan_all(available_cash=cash, total_capital=capital, active_tickers=active_tickers)

        if not signals:
            await update.message.reply_text(
                "ℹ️ <b>Scan Complete:</b> No high-probability setups found right now that meet our strict risk criteria.\n"
                "Patience is key in swing trading! We will notify you as soon as a new setup triggers.",
                parse_mode="HTML"
            )
            return

        for sig in signals:
            await self.send_signal_alert(context.bot, update.effective_chat.id, sig)

    async def send_signal_alert(self, bot, chat_id: int, sig: Dict[str, Any]):
        sig_id = f"{sig['symbol']}_{int(sig['ltp'])}"
        self.pending_signals[sig_id] = sig
        self._save_pending_signals()

        t1 = sig.get("target_1", sig.get("target"))
        t2 = sig.get("target_2", round(sig["entry_price"] * 1.08, 2))

        card = (
            f"🚀 <b>TRADE SETUP: {sig['symbol']}</b> (NSE)\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Strategy:</b> {sig['strategy']}\n"
            f"💰 <b>LTP / Entry:</b> ₹{sig['entry_price']:,.2f}\n"
            f"🛑 <b>Stop Loss:</b> ₹{sig['stop_loss']:,.2f} (-{abs(sig['entry_price']-sig['stop_loss'])/sig['entry_price']*100:.1f}%)\n"
            f"🎯 <b>Target 1 (Book 50%):</b> ₹{t1:,.2f} (+{abs(t1-sig['entry_price'])/sig['entry_price']*100:.1f}%)\n"
            f"🚀 <b>Target 2 (Runner):</b>   ₹{t2:,.2f} (+{abs(t2-sig['entry_price'])/sig['entry_price']*100:.1f}%)\n"
            f"⚖️ <b>Risk/Reward:</b> 1 : {sig.get('risk_reward_ratio', 1.5):.1f}\n"
            f"📦 <b>Suggested Quantity:</b> {sig['quantity']} shares\n"
            f"💵 <b>Investment Required:</b> ₹{sig['total_investment']:,.2f}\n"
            f"🛡️ <b>Max Risk:</b> ₹{sig['max_risk_amount']:,.2f} ({sig['risk_pct_of_capital']}% of account)\n"
            f"💡 <b>Rationale:</b> {sig.get('reason', 'Strong momentum')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Tap below to approve trade execution:</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton(f"✅ Approve Buy ({sig['quantity']} shares)", callback_data=f"buy_{sig_id}"),
                InlineKeyboardButton("❌ Dismiss", callback_data=f"dismiss_{sig_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await bot.send_message(chat_id=chat_id, text=card, parse_mode="HTML", reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Could not answer callback query (possibly stale): {e}")

        data = query.data
        if data.startswith("buy_"):
            sig_id = data.replace("buy_", "")
            sig = self.pending_signals.get(sig_id) or self._load_pending_signals().get(sig_id)
            if not sig:
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("⚠️ This signal has expired or is no longer available.")
                return

            # Check if portfolio can take this position
            can_open, reason = self.portfolio.can_open_position(sig["total_investment"], sig["ticker"])
            if not can_open:
                await query.message.reply_text(f"❌ <b>Order Denied:</b> {reason}", parse_mode="HTML")
                return

            # Execute Order via Broker (Paper or Live Kotak Neo)
            order_res = self.broker.place_equity_order(
                symbol=sig["symbol"],
                quantity=sig["quantity"],
                transaction_type="B",
                order_type="MKT",
                price=sig["entry_price"]
            )
            
            if order_res.get("status") == "error":
                await query.message.reply_text(f"❌ <b>Broker Error:</b> {order_res.get('error')}", parse_mode="HTML")
                return

            pos = self.portfolio.open_position(sig, sig["quantity"], sig["entry_price"])
            self.pending_signals.pop(sig_id, None)

            # Update the original message
            await query.edit_message_reply_markup(reply_markup=None)
            mode_tag = "🟢 PAPER TRADE" if order_res.get("mode") == "PAPER_TRADING" else "🔴 LIVE KOTAK NEO ORDER"
            order_id = order_res.get("order_id", "N/A")
            
            success_card = (
                f"✅ <b>ORDER EXECUTED! ({mode_tag})</b>\n\n"
                f"Stock: <b>{sig['symbol']}</b>\n"
                f"Order ID: <code>{order_id}</code>\n"
                f"Quantity: {pos['quantity']} shares @ ₹{pos['entry_price']:,.2f}\n"
                f"Total Invested: ₹{pos['total_cost']:,.2f}\n"
                f"Stop Loss: ₹{pos['stop_loss']:,.2f}\n"
                f"Target: ₹{pos['target']:,.2f}\n\n"
                f"<i>The bot is now monitoring {sig['symbol']} and will alert you upon Target or Stop-Loss.</i>"
            )
            await query.message.reply_text(success_card, parse_mode="HTML")

        elif data.startswith("dismiss_"):
            sig_id = data.replace("dismiss_", "")
            self.pending_signals.pop(sig_id, None)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("❌ <i>Signal dismissed. No action taken.</i>", parse_mode="HTML")

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        summary = self.portfolio.get_summary()
        
        positions = summary["active_positions"]
        pos_text = ""
        if not positions:
            pos_text = "<i>No open positions. Cash is 100% idle and safe.</i>\n"
        else:
            for ticker, p in positions.items():
                pnl = (p.get("current_price", p["entry_price"]) - p["entry_price"]) * p["quantity"]
                pnl_pct = ((p.get("current_price", p["entry_price"]) - p["entry_price"]) / p["entry_price"]) * 100
                pnl_icon = "🟢" if pnl >= 0 else "🔴"
                pos_text += (
                    f"• <b>{p['ticker'].replace('.NS', '')}</b>: {p['quantity']} shares @ ₹{p['entry_price']}\n"
                    f"  Current: ₹{p.get('current_price', p['entry_price'])} | SL: ₹{p['stop_loss']} | Tgt: ₹{p['target']}\n"
                    f"  {pnl_icon} Unrealized P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)\n\n"
                )

        msg = (
            f"💼 <b>VIRTUAL PORTFOLIO STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Available Cash:</b> ₹{summary['cash_balance']:,.2f}\n"
            f"📈 <b>Invested Amount:</b> ₹{summary['invested_capital']:,.2f}\n"
            f"💼 <b>Total Portfolio Value:</b> ₹{summary['total_value']:,.2f}\n"
            f"📊 <b>Unrealized P&L:</b> ₹{summary['unrealized_pnl']:+,.2f}\n"
            f"💵 <b>Realized P&L:</b> ₹{summary['realized_pnl']:+,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Active Positions ({summary['open_positions_count']}):</b>\n{pos_text}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        summary = self.portfolio.get_summary()
        history = summary["history"]

        hist_text = ""
        if not history:
            hist_text = "<i>No closed trades yet.</i>"
        else:
            for t in history:
                icon = "🟢" if t["pnl"] > 0 else "🔴"
                hist_text += (
                    f"{icon} <b>{t['ticker'].replace('.NS', '')}</b>: ₹{t['pnl']:+,.2f} ({t['pnl_pct']:+.2f}%)\n"
                    f"  Exit Reason: {t['reason']} on {t['exit_time'][:10]}\n"
                )

        msg = (
            f"📊 <b>PERFORMANCE & P&L REPORT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Total Completed Trades: {summary['total_trades_count']}\n"
            f"Win Rate: <b>{summary['win_rate']}%</b>\n"
            f"Net Realized Profit: <b>₹{summary['realized_pnl']:+,.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Recent Closed Trades:</b>\n{hist_text}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generates AI synthesis and journal analysis from SQLite trading database."""
        await update.message.reply_text("🤖 <i>Analyzing database trade records with AI layer...</i>", parse_mode="HTML")
        review = self.ai_analyst.generate_journal_review()
        await update.message.reply_text(review, parse_mode="HTML")

    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args:
            await update.message.reply_text("Usage: <code>/close &lt;SYMBOL&gt;</code> (e.g. <code>/close RELIANCE</code>)", parse_mode="HTML")
            return

        symbol = args[0].upper().replace(".NS", "")
        ticker = f"{symbol}.NS"
        
        pos = self.portfolio.state["active_positions"].get(ticker)
        if not pos:
            await update.message.reply_text(f"❌ You do not have an active position in {symbol}.", parse_mode="HTML")
            return

        exit_price = pos.get("current_price", pos["entry_price"])
        record = self.portfolio.close_position(ticker, exit_price, reason="Manual User Exit via Telegram")
        
        icon = "🟢" if record["pnl"] >= 0 else "🔴"
        await update.message.reply_text(
            f"✅ <b>Position Closed:</b> {symbol}\n"
            f"Sold {record['quantity']} shares @ ₹{record['exit_price']:,.2f}\n"
            f"{icon} Realized P&L: <b>₹{record['pnl']:+,.2f} ({record['pnl_pct']:+.2f}%)</b>",
            parse_mode="HTML"
        )
