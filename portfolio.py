import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import config
from database import TradingDatabase

logger = logging.getLogger("Portfolio")
BASE_DIR = Path(__file__).resolve().parent
PORTFOLIO_FILE = BASE_DIR / "paper_portfolio.json"

class PortfolioManager:
    def __init__(self, filepath: Path = PORTFOLIO_FILE, db: Optional[TradingDatabase] = None):
        self.filepath = filepath
        self.db = db or TradingDatabase()
        self.state = self._load_or_init()

    def _load_or_init(self) -> Dict[str, Any]:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading portfolio file, resetting: {e}")
        
        initial_state = {
            "initial_capital": config.INITIAL_CAPITAL,
            "cash_balance": config.INITIAL_CAPITAL,
            "realized_pnl": 0.0,
            "active_positions": {},
            "trade_history": []
        }
        self._save(initial_state)
        return initial_state

    def _save(self, state: Optional[Dict[str, Any]] = None):
        if state is not None:
            self.state = state
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)

    def can_open_position(self, required_cash: float, ticker: str) -> tuple[bool, str]:
        if ticker in self.state["active_positions"]:
            return False, f"Already have an open position in {ticker}."
        
        if len(self.state["active_positions"]) >= config.MAX_OPEN_POSITIONS:
            return False, f"Maximum open positions limit ({config.MAX_OPEN_POSITIONS}) reached."
        
        if self.state["cash_balance"] < required_cash:
            return False, f"Insufficient cash (Available: ₹{self.state['cash_balance']:,.2f}, Required: ₹{required_cash:,.2f})."
        
        return True, "OK"

    def open_position(self, signal: Dict[str, Any], quantity: int, execution_price: float) -> Dict[str, Any]:
        cost = quantity * execution_price
        self.state["cash_balance"] -= cost
        
        ticker = signal["ticker"]
        t1 = signal.get("target_1", signal.get("target", execution_price * 1.05))
        t2 = signal.get("target_2", execution_price * 1.10)
        atr = signal.get("atr", execution_price * 0.02)

        position = {
            "ticker": ticker,
            "strategy": signal.get("strategy", "Technical Setup"),
            "initial_quantity": quantity,
            "quantity": quantity,
            "entry_price": round(execution_price, 2),
            "total_cost": round(cost, 2),
            "stop_loss": round(signal["stop_loss"], 2),
            "initial_stop_loss": round(signal["stop_loss"], 2),
            "target_1": round(t1, 2),
            "target_2": round(t2, 2),
            "target": round(t1, 2),
            "atr": round(atr, 2),
            "t1_hit": False,
            "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_price": round(execution_price, 2),
            "highest_price": round(execution_price, 2)
        }
        
        self.state["active_positions"][ticker] = position
        self._save()
        
        # Log to SQLite Trading Journal
        try:
            self.db.log_trade_entry(signal, quantity, execution_price)
        except Exception as e:
            logger.error(f"Error logging trade entry to DB: {e}")

        logger.info(f"Opened position: {ticker} x {quantity} @ ₹{execution_price}")
        return position

    def close_position(self, ticker: str, exit_price: float, reason: str = "Manual Exit", partial_qty: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if ticker not in self.state["active_positions"]:
            return None
        
        pos = self.state["active_positions"][ticker]
        qty_to_close = partial_qty if partial_qty and partial_qty < pos["quantity"] else pos["quantity"]
        entry_price = pos["entry_price"]
        proceeds = qty_to_close * exit_price
        cost_basis = qty_to_close * entry_price
        pnl = proceeds - cost_basis
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        
        self.state["cash_balance"] += proceeds
        self.state["realized_pnl"] += pnl
        
        trade_record = {
            "ticker": ticker,
            "strategy": pos["strategy"],
            "quantity": qty_to_close,
            "entry_price": entry_price,
            "exit_price": round(exit_price, 2),
            "entry_time": pos["entry_time"],
            "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "reason": reason
        }
        
        self.state["trade_history"].append(trade_record)
        
        is_full = True
        if qty_to_close < pos["quantity"]:
            # Remaining runner
            pos["quantity"] -= qty_to_close
            pos["total_cost"] -= cost_basis
            is_full = False
        else:
            self.state["active_positions"].pop(ticker)

        self._save()

        # Log Exit to SQLite Trading Journal
        try:
            self.db.log_trade_exit(
                ticker=ticker,
                exit_price=exit_price,
                reason=reason,
                pnl=pnl,
                pnl_pct=pnl_pct,
                is_full_exit=is_full
            )
        except Exception as e:
            logger.error(f"Error logging trade exit to DB: {e}")

        logger.info(f"Closed {qty_to_close} of {ticker} @ ₹{exit_price}. P&L: ₹{pnl:.2f} ({pnl_pct:.2f}%) - {reason}")
        return trade_record

    def check_exits(self, current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Institutional Multi-Stage Exit Engine:
        1. Target 1 Reached: Sell 50% shares, Lock Profit, Move SL to Breakeven (Risk = 0)
        2. Dynamic ATR Trailing Stop: Stop loss ratchets upward on runners
        3. Target 2 or Trailing Stop Triggered: Sell remaining 50% shares
        """
        exit_events = []
        for ticker, pos in list(self.state["active_positions"].items()):
            ltp = current_prices.get(ticker)
            if not ltp:
                continue
            
            pos["current_price"] = round(ltp, 2)
            if ltp > pos.get("highest_price", pos["entry_price"]):
                pos["highest_price"] = round(ltp, 2)
            
            atr = pos.get("atr", pos["entry_price"] * 0.02)

            t1 = pos.get("target_1", pos.get("target", pos["entry_price"] * 1.05))
            t2 = pos.get("target_2", pos["entry_price"] * 1.10)

            # Stage 1: Target 1 Hit (Book 50% and move SL to Entry Price)
            if not pos.get("t1_hit", False) and ltp >= t1:
                pos["t1_hit"] = True
                half_qty = pos["quantity"] // 2
                if half_qty > 0:
                    closed = self.close_position(
                        ticker, ltp, 
                        reason="🎯 Target 1 Hit (50% Booked) - SL moved to Breakeven", 
                        partial_qty=half_qty
                    )
                    if closed:
                        exit_events.append(closed)
                
                # Move Stop Loss to Breakeven!
                pos["stop_loss"] = pos["entry_price"]
                logger.info(f"{ticker} Target 1 Hit! Stop Loss moved to Breakeven ₹{pos['entry_price']}.")

            # Stage 2: Dynamic Trailing Stop for Runner
            elif pos.get("t1_hit", False):
                # Trail by 1.8x ATR from peak
                new_trailing_sl = round(pos["highest_price"] - (1.8 * atr), 2)
                if new_trailing_sl > pos["stop_loss"]:
                    pos["stop_loss"] = new_trailing_sl
                    logger.info(f"{ticker} Trailing Stop Loss ratcheted up to ₹{pos['stop_loss']}")

            # Check Stop Loss / Trailing Stop Trigger
            if ltp <= pos["stop_loss"]:
                reason = "🛡️ Trailing Stop Hit (Profits Protected)" if pos.get("t1_hit", False) else "🛑 Stop Loss Hit"
                closed = self.close_position(ticker, ltp, reason=reason)
                if closed:
                    exit_events.append(closed)

            # Check Target 2 Trigger (Full Trend Captured)
            elif ltp >= t2:
                closed = self.close_position(ticker, ltp, reason="🚀 Target 2 Achieved (Full Trend Winner)")
                if closed:
                    exit_events.append(closed)
                    
        self._save()
        return exit_events

    def get_summary(self, current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        cash = self.state["cash_balance"]
        invested = 0.0
        unrealized_pnl = 0.0
        
        for ticker, pos in self.state["active_positions"].items():
            ltp = current_prices.get(ticker, pos["entry_price"]) if current_prices else pos.get("current_price", pos["entry_price"])
            market_val = pos["quantity"] * ltp
            invested += pos["total_cost"]
            unrealized_pnl += (market_val - pos["total_cost"])
            
        total_portfolio_value = cash + invested + unrealized_pnl
        net_return_pct = ((total_portfolio_value - self.state["initial_capital"]) / self.state["initial_capital"]) * 100
        
        trades = self.state["trade_history"]
        winning_trades = [t for t in trades if t["pnl"] > 0]
        win_rate = (len(winning_trades) / len(trades) * 100) if trades else 0.0
        
        return {
            "initial_capital": self.state["initial_capital"],
            "cash_balance": round(cash, 2),
            "invested_capital": round(invested, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(self.state["realized_pnl"], 2),
            "total_value": round(total_portfolio_value, 2),
            "net_return_pct": round(net_return_pct, 2),
            "open_positions_count": len(self.state["active_positions"]),
            "total_trades_count": len(trades),
            "win_rate": round(win_rate, 1),
            "active_positions": self.state["active_positions"],
            "history": self.state["trade_history"][-5:]
        }
