import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TradingDatabase")
DB_PATH = Path("E:/TRADING/trading_journal.db")

class TradingDatabase:
    """
    SQLite Trading Database & Quantitative Journal.
    Logs every trade with rich technical metadata (RSI, Volume Surge, Nifty Trend)
    to build an institutional dataset for AI Analysis (Gemini/Claude).
    """
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Trades Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                ticker TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                total_cost REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target_1 REAL NOT NULL,
                target_2 REAL,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                status TEXT NOT NULL, -- 'OPEN', 'PARTIAL_CLOSED', 'CLOSED'
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                
                -- Quantitative Metadata for AI Training
                rsi_at_entry REAL,
                vol_surge_ratio REAL,
                nifty_regime TEXT,
                risk_reward_ratio REAL,
                max_risk_amount REAL,
                ai_confidence_rating TEXT,
                notes TEXT
            )
            """)

            # Market Daily Log Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_market_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT UNIQUE,
                nifty_close REAL,
                market_regime TEXT,
                scanned_setups_count INTEGER,
                executed_trades_count INTEGER
            )
            """)
            conn.commit()
            logger.info("Trading SQLite Database initialized.")

    def log_trade_entry(self, signal: Dict[str, Any], quantity: int, execution_price: float) -> str:
        trade_id = f"TRD_{signal['symbol']}_{int(datetime.now().timestamp())}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO trades (
                trade_id, ticker, symbol, strategy, quantity, entry_price, total_cost,
                stop_loss, target_1, target_2, status, entry_time,
                rsi_at_entry, vol_surge_ratio, nifty_regime, risk_reward_ratio, max_risk_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                signal["ticker"],
                signal["symbol"],
                signal.get("strategy", "Technical Setup"),
                quantity,
                execution_price,
                round(quantity * execution_price, 2),
                signal.get("stop_loss", 0.0),
                signal.get("target_1", signal.get("target", 0.0)),
                signal.get("target_2", 0.0),
                "OPEN",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                signal.get("rsi", 50.0),
                signal.get("volume_surge", 1.0),
                signal.get("nifty_regime", "BULL"),
                signal.get("risk_reward_ratio", 1.5),
                signal.get("max_risk_amount", 1000.0)
            ))
            conn.commit()
        logger.info(f"Database: Logged Entry for {signal['symbol']} (Trade ID: {trade_id})")
        return trade_id

    def log_trade_exit(self, ticker: str, exit_price: float, reason: str, pnl: float, pnl_pct: float, is_full_exit: bool = True):
        clean_symbol = ticker.replace(".NS", "")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Find the latest open trade for this symbol
            cursor.execute("""
            SELECT id, quantity, total_cost, entry_price FROM trades 
            WHERE symbol = ? AND status IN ('OPEN', 'PARTIAL_CLOSED')
            ORDER BY id DESC LIMIT 1
            """, (clean_symbol,))
            row = cursor.fetchone()
            
            if row:
                record_id, qty, cost, entry_p = row
                new_status = "CLOSED" if is_full_exit else "PARTIAL_CLOSED"
                cursor.execute("""
                UPDATE trades SET
                    exit_price = ?,
                    pnl = ?,
                    pnl_pct = ?,
                    exit_reason = ?,
                    status = ?,
                    exit_time = ?
                WHERE id = ?
                """, (
                    exit_price,
                    round(pnl, 2),
                    round(pnl_pct, 2),
                    reason,
                    new_status,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    record_id
                ))
                conn.commit()
                logger.info(f"Database: Logged Exit for {clean_symbol}. P&L: ₹{pnl:.2f}")

    def get_all_trades_for_ai(self) -> List[Dict[str, Any]]:
        """Exports all completed trades as structured JSON for Gemini / Claude analysis."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY id ASC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_database_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM trades")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'CLOSED' AND pnl > 0")
            wins = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'CLOSED' AND pnl <= 0")
            losses = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(pnl) FROM trades WHERE status = 'CLOSED'")
            net_pnl = cursor.fetchone()[0] or 0.0

            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

            return {
                "total_logged": total,
                "closed_trades": wins + losses,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
                "net_pnl": round(net_pnl, 2)
            }
