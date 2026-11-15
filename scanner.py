import logging
from typing import List, Dict, Any, Optional
import yfinance as yf
import pandas as pd
import numpy as np
import config
from risk_manager import RiskManager
from regime_filter import MarketRegimeFilter

logger = logging.getLogger("Scanner")

class TechnicalScanner:
    def __init__(self, watchlist: List[str] = config.WATCHLIST):
        self.watchlist = watchlist
        self.risk_manager = RiskManager()
        self.regime_filter = MarketRegimeFilter()

    def fetch_stock_data(self, ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval)
            if df.empty or len(df) < 50:
                return None
            return df
        except Exception as e:
            logger.warning(f"Error fetching data for {ticker}: {e}")
            return None

    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
        
        df["High20"] = df["High"].rolling(window=20).max()
        df["Vol20Avg"] = df["Volume"].rolling(window=20).mean()

        # RSI 14
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["RSI"] = 100 - (100 / (1 + rs))
        df["RSI"] = df["RSI"].fillna(50)

        # Average True Range (ATR 14) for dynamic volatility stops
        high_low = df["High"] - df["Low"]
        high_cp = np.abs(df["High"] - df["Close"].shift())
        low_cp = np.abs(df["Low"] - df["Close"].shift())
        df["TR"] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df["ATR14"] = df["TR"].rolling(window=14).mean()

        return df

    def scan_ticker(self, ticker: str, available_cash: float, total_capital: float) -> Optional[Dict[str, Any]]:
        df = self.fetch_stock_data(ticker)
        if df is None:
            return None

        df = self.calculate_indicators(df)
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        ltp = float(last_row["Close"])
        ema20 = float(last_row["EMA20"])
        ema50 = float(last_row["EMA50"])
        ema200 = float(last_row["EMA200"])
        vol_avg = float(last_row["Vol20Avg"])
        cur_vol = float(last_row["Volume"])
        rsi = float(last_row["RSI"])
        rsi_prev = float(prev_row["RSI"])
        atr = float(last_row["ATR14"])
        high20_prev = float(prev_row["High20"])

        clean_symbol = ticker.replace(".NS", "")
        signal = None

        # Strategy 1: Volume Breakout at 20-Day High (Momentum Expansion)
        if ltp >= high20_prev and cur_vol >= (1.2 * vol_avg) and ema20 > ema50:
            stop_loss = round(max(ltp - (1.6 * atr), ltp * 0.97), 2)
            risk = ltp - stop_loss
            target_1 = round(ltp + (1.5 * risk), 2)
            target_2 = round(ltp + (3.0 * risk), 2)
            
            signal = {
                "ticker": ticker,
                "symbol": clean_symbol,
                "strategy": "20-Day Breakout + Volume Surge 🚀",
                "ltp": round(ltp, 2),
                "stop_loss": stop_loss,
                "target_1": target_1,
                "target_2": target_2,
                "target": target_1,
                "atr": round(atr, 2),
                "rsi": round(rsi, 1),
                "volume_surge": round(cur_vol / vol_avg, 2),
                "reason": f"Breaks 20-day high with {cur_vol / vol_avg:.1f}x volume surge. Strong bullish institutional momentum."
            }

        # Strategy 2: Bullish Pullback to 20 EMA
        elif ema20 > ema50 and abs(ltp - ema20) / ema20 <= 0.015 and 40 <= rsi <= 62 and ltp > ema50:
            stop_loss = round(max(ema50 * 0.99, ltp - (1.5 * atr)), 2)
            risk = ltp - stop_loss
            target_1 = round(ltp + (1.5 * risk), 2)
            target_2 = round(ltp + (3.0 * risk), 2)
            
            signal = {
                "ticker": ticker,
                "symbol": clean_symbol,
                "strategy": "Bullish 20 EMA Pullback 📈",
                "ltp": round(ltp, 2),
                "stop_loss": stop_loss,
                "target_1": target_1,
                "target_2": target_2,
                "target": target_1,
                "atr": round(atr, 2),
                "rsi": round(rsi, 1),
                "volume_surge": round(cur_vol / vol_avg, 2),
                "reason": f"Healthy pullback to rising 20 EMA in an established uptrend. RSI ({rsi:.1f}) reset."
            }

        # Strategy 3: RSI Dip Recovery in Bullish Trend
        elif ema50 > ema200 and ltp > ema200 and rsi_prev <= 42 and rsi > 42:
            stop_loss = round(max(ltp * 0.97, ltp - (1.6 * atr)), 2)
            risk = ltp - stop_loss
            target_1 = round(ltp + (1.5 * risk), 2)
            target_2 = round(ltp + (3.0 * risk), 2)

            signal = {
                "ticker": ticker,
                "symbol": clean_symbol,
                "strategy": "RSI Trend Dip Reversal 🔄",
                "ltp": round(ltp, 2),
                "stop_loss": stop_loss,
                "target_1": target_1,
                "target_2": target_2,
                "target": target_1,
                "atr": round(atr, 2),
                "rsi": round(rsi, 1),
                "volume_surge": round(cur_vol / vol_avg, 2),
                "reason": f"Bullish trend confirmed (50 EMA > 200 EMA). RSI turning up from oversold ({rsi:.1f})."
            }

        if signal:
            valid, sizing = self.risk_manager.evaluate_and_size_trade(
                entry_price=signal["ltp"],
                stop_loss=signal["stop_loss"],
                target_1=signal["target_1"],
                target_2=signal["target_2"],
                atr=signal["atr"],
                available_cash=available_cash,
                total_capital=total_capital
            )
            if valid:
                signal.update(sizing)
                return signal
            else:
                logger.info(f"Signal for {ticker} filtered by Risk Manager: {sizing.get('reason')}")

        return None

    def scan_all(self, available_cash: float, total_capital: float, active_tickers: List[str] = None) -> List[Dict[str, Any]]:
        # 1. Market Regime Check
        is_allowed, regime_msg, _ = self.regime_filter.get_market_regime()
        if not is_allowed:
            logger.warning(f"Scan aborted: {regime_msg}")
            return []

        if active_tickers is None:
            active_tickers = []

        found_signals = []
        for ticker in self.watchlist:
            if ticker in active_tickers:
                continue
            res = self.scan_ticker(ticker, available_cash, total_capital)
            if res:
                found_signals.append(res)
        return found_signals
