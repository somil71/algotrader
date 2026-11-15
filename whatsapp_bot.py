import os
import logging
from typing import Dict, Any, Optional
from twilio.rest import Client
import config
from portfolio import PortfolioManager
from scanner import TechnicalScanner
from kotak_broker import KotakNeoBroker

logger = logging.getLogger("WhatsAppBot")

class WhatsAppTradingBot:
    def __init__(self, portfolio: PortfolioManager, scanner: TechnicalScanner, broker: KotakNeoBroker):
        self.portfolio = portfolio
        self.scanner = scanner
        self.broker = broker
        
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886") # Twilio Sandbox
        self.to_number = os.getenv("FATHER_WHATSAPP_NUMBER", "") # e.g. "whatsapp:+919876543210"
        
        self.client = None
        self.latest_pending_signal: Optional[Dict[str, Any]] = None

        if self.account_sid and self.auth_token:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("Twilio WhatsApp client initialized.")
            except Exception as e:
                logger.error(f"Error initializing Twilio: {e}")

    def send_whatsapp_message(self, body: str) -> bool:
        """Sends a WhatsApp message to Father's phone."""
        if not self.client or not self.to_number:
            logger.warning("WhatsApp credentials missing. Message not sent.")
            return False

        try:
            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=self.to_number
            )
            logger.info(f"WhatsApp sent! SID: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return False

    def send_trade_signal(self, sig: Dict[str, Any]):
        """Formats and sends a high-priority trade card to WhatsApp."""
        self.latest_pending_signal = sig

        t1 = sig.get("target_1", sig.get("target"))
        t2 = sig.get("target_2", round(sig["entry_price"] * 1.08, 2))

        msg = (
            f"🚀 *ALGO TRADE ALERT: {sig['symbol']} (NSE)*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Strategy:* {sig['strategy']}\n"
            f"💰 *Current Price:* ₹{sig['entry_price']:,.2f}\n"
            f"🛑 *Stop Loss:* ₹{sig['stop_loss']:,.2f}\n"
            f"🎯 *Target 1 (Book 50%):* ₹{t1:,.2f}\n"
            f"🚀 *Target 2 (Runner):* ₹{t2:,.2f}\n"
            f"📦 *Suggested Qty:* {sig['quantity']} shares\n"
            f"💵 *Investment:* ₹{sig['total_investment']:,.2f}\n"
            f"🛡️ *Max Risk:* ₹{sig['max_risk_amount']:,.2f} (<1%)\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"👉 *TO APPROVE:* Reply *1* or *BUY*\n"
            f"❌ *TO DISMISS:* Reply *NO*\n"
            f"💼 *TO VIEW BALANCE:* Reply *PORTFOLIO*"
        )
        return self.send_whatsapp_message(msg)

    def handle_incoming_message(self, from_number: str, message_text: str) -> str:
        """
        Processes incoming WhatsApp replies from Father.
        Easy, natural text commands:
        '1' or 'BUY' -> Executes pending trade
        'PORTFOLIO' -> Returns balance & active trades
        'PNL' -> Returns realized profit
        'SCAN' -> Triggers a fresh market scan
        """
        text = message_text.strip().upper()

        if text in ["1", "BUY", "YES", "APPROVE"]:
            if not self.latest_pending_signal:
                return "⚠️ No pending trade signal to approve right now. Send SCAN to find setups."

            sig = self.latest_pending_signal
            can_open, reason = self.portfolio.can_open_position(sig["total_investment"], sig["ticker"])
            if not can_open:
                return f"❌ Order Denied: {reason}"

            # Execute via broker
            order_res = self.broker.place_equity_order(
                symbol=sig["symbol"],
                quantity=sig["quantity"],
                price=sig["entry_price"]
            )
            pos = self.portfolio.open_position(sig, sig["quantity"], sig["entry_price"])
            self.latest_pending_signal = None

            return (
                f"✅ *ORDER EXECUTED ON WHATSAPP!*\n\n"
                f"Stock: *{sig['symbol']}*\n"
                f"Bought: {pos['quantity']} shares @ ₹{pos['entry_price']:,.2f}\n"
                f"Invested: ₹{pos['total_cost']:,.2f}\n"
                f"Stop Loss: ₹{pos['stop_loss']:,.2f}\n"
                f"Target 1: ₹{pos['target_1']:,.2f}\n\n"
                f"The algorithm is actively monitoring and will alert you upon Target or Stop-Loss!"
            )

        elif text in ["NO", "DISMISS", "SKIP", "2"]:
            self.latest_pending_signal = None
            return "❌ Trade signal dismissed. Waiting for the next setup."

        elif "PORTFOLIO" in text or text == "STATUS":
            summary = self.portfolio.get_summary()
            pos_text = ""
            for t, p in summary["active_positions"].items():
                pos_text += f"• {t.replace('.NS', '')}: {p['quantity']} sh @ ₹{p['entry_price']} (SL: ₹{p['stop_loss']})\n"
            if not pos_text:
                pos_text = "No open trades right now.\n"

            return (
                f"💼 *PORTFOLIO SUMMARY*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Available Cash: ₹{summary['cash_balance']:,.2f}\n"
                f"📈 Invested: ₹{summary['invested_capital']:,.2f}\n"
                f"💵 Realized P&L: ₹{summary['realized_pnl']:+,.2f}\n\n"
                f"*Active Trades:*\n{pos_text}"
            )

        elif "PNL" in text or "PROFIT" in text:
            summary = self.portfolio.get_summary()
            return (
                f"📊 *PROFIT & LOSS REPORT*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Total Trades: {summary['total_trades_count']}\n"
                f"Win Rate: {summary['win_rate']}%\n"
                f"Net Profit: *₹{summary['realized_pnl']:+,.2f}*"
            )

        elif "SCAN" in text:
            summary = self.portfolio.get_summary()
            signals = self.scanner.scan_all(
                available_cash=summary["cash_balance"],
                total_capital=summary["initial_capital"],
                active_tickers=list(summary["active_positions"].keys())
            )
            if not signals:
                return "ℹ️ Scan complete: No setups found right now that meet our strict risk criteria."
            
            # Send the first signal
            self.send_trade_signal(signals[0])
            return f"Found {len(signals)} setups! Sent the first setup above."

        return (
            "👋 *Trading Assistant Commands:*\n"
            "• Reply *1* or *BUY* to approve pending trade\n"
            "• Reply *PORTFOLIO* to check active positions & cash\n"
            "• Reply *PNL* to see profit report\n"
            "• Reply *SCAN* to scan the market now"
        )
