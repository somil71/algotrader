import logging
from typing import Dict, Any, Tuple
import yfinance as yf
import pandas as pd

logger = logging.getLogger("MarketRegime")

class MarketRegimeFilter:
    """
    Evaluates broader market health using Nifty 50 Index (^NSEI).
    Rule: Never take aggressive long swing trades when the benchmark index 
    is in a severe downtrend (trading below falling 50 EMA).
    """
    def __init__(self, index_symbol: str = "^NSEI"):
        self.index_symbol = index_symbol
        self.cached_regime: Dict[str, Any] = {}

    def get_market_regime(self) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            nifty = yf.Ticker(self.index_symbol)
            df = nifty.history(period="6mo", interval="1d")
            if df.empty or len(df) < 50:
                return True, "Market data unavailable; proceeding with caution.", {}

            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

            last = df.iloc[-1]
            close = float(last["Close"])
            ema20 = float(last["EMA20"])
            ema50 = float(last["EMA50"])

            details = {
                "nifty_close": round(close, 2),
                "nifty_ema20": round(ema20, 2),
                "nifty_ema50": round(ema50, 2),
                "is_above_ema50": close >= ema50,
                "is_bullish_alignment": ema20 >= ema50
            }

            if close >= ema20 and ema20 >= ema50:
                return True, "🟢 BULL MARKET: Strong upward momentum in Nifty.", details
            elif close >= ema50:
                return True, "🟡 NEUTRAL/PULLBACK: Nifty above 50 EMA. Selective setups allowed.", details
            else:
                return False, "🔴 BEAR MARKET/CORRECTION: Nifty below 50 EMA. Buying is restricted to protect capital.", details

        except Exception as e:
            logger.error(f"Error fetching market regime: {e}")
            return True, f"Error checking regime ({e}); defaulting to permissive.", {}
