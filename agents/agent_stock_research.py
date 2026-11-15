"""
Agent 3: Correlated Stock Research
------------------------------------
For every open position or pending signal, finds the most correlated
stocks in the same sector using historical price correlation.

Logic:
  1. Take the target stock (e.g., INFY)
  2. Find its sector peers from the config watchlist
  3. Compute Pearson correlation over last 30 days using yfinance
  4. If top 3 correlated peers are ALSO breaking out → CONFIRMATION
  5. If correlated peers are FALLING → DIVERGENCE (risk flag)

Triggered:
  - On every new signal (called from orchestrator)
  - On-demand via /correlate <SYMBOL> Telegram command
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger("CorrelationResearchAgent")


# Sector mapping — which stocks belong to same sector
# (from the 42-stock Nifty watchlist in config.py)
SECTOR_PEERS = {
    # IT / Technology
    "INFY.NS":    ["TCS.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTI.NS"],
    "TCS.NS":     ["INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTI.NS"],
    "WIPRO.NS":   ["INFY.NS", "TCS.NS", "HCLTECH.NS", "TECHM.NS"],
    "HCLTECH.NS": ["INFY.NS", "TCS.NS", "WIPRO.NS", "TECHM.NS"],
    "TECHM.NS":   ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS"],

    # Banking / Finance
    "HDFCBANK.NS": ["ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SBIN.NS", "BANKBARODA.NS"],
    "ICICIBANK.NS":["HDFCBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SBIN.NS"],
    "AXISBANK.NS": ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "SBIN.NS"],
    "KOTAKBANK.NS":["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "SBIN.NS"],
    "SBIN.NS":     ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "BANKBARODA.NS"],

    # Auto
    "MARUTI.NS":  ["TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS", "EICHERMOT.NS"],
    "M&M.NS":     ["MARUTI.NS", "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
    "BAJAJ-AUTO.NS":["MARUTI.NS", "M&M.NS", "HEROMOTOCO.NS", "EICHERMOT.NS"],

    # Energy / Oil
    "RELIANCE.NS": ["ONGC.NS", "BPCL.NS", "IOC.NS", "NTPC.NS"],
    "ONGC.NS":     ["RELIANCE.NS", "BPCL.NS", "IOC.NS"],
    "BPCL.NS":     ["RELIANCE.NS", "ONGC.NS", "IOC.NS"],

    # Pharma
    "SUNPHARMA.NS":["DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS"],
    "DRREDDY.NS":  ["SUNPHARMA.NS", "CIPLA.NS", "DIVISLAB.NS"],
    "CIPLA.NS":    ["SUNPHARMA.NS", "DRREDDY.NS", "DIVISLAB.NS"],

    # FMCG
    "HINDUNILVR.NS":["NESTLEIND.NS", "DABUR.NS", "MARICO.NS", "GODREJCP.NS"],
    "NESTLEIND.NS": ["HINDUNILVR.NS", "DABUR.NS", "MARICO.NS"],

    # Metals
    "TATASTEEL.NS": ["JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "SAIL.NS"],
    "JSWSTEEL.NS":  ["TATASTEEL.NS", "HINDALCO.NS", "VEDL.NS"],
    "HINDALCO.NS":  ["TATASTEEL.NS", "JSWSTEEL.NS", "VEDL.NS"],

    # Cement
    "ULTRACEMCO.NS":["GRASIM.NS", "ACC.NS", "AMBUJACEM.NS", "SHREECEM.NS"],

    # Telecom
    "BHARTIARTL.NS":["IDEA.NS"],
}

# Default peers if ticker not in SECTOR_PEERS (use broad Nifty proxies)
DEFAULT_PEERS = ["^NSEI", "HDFCBANK.NS", "RELIANCE.NS", "INFY.NS", "ICICIBANK.NS"]


@dataclass
class CorrelationResult:
    ticker: str
    peer: str
    correlation: float
    peer_trend: str      # "RISING" | "FALLING" | "FLAT"
    peer_rsi: float
    signal: str          # "CONFIRMS" | "DIVERGES" | "NEUTRAL"


class CorrelationResearchAgent:
    """
    Agent 3: Finds correlated sector peers and validates trade signals.
    Helps identify whether a breakout is sector-wide (strong) or isolated (risky).
    """

    def __init__(self, message_queue: List):
        self.message_queue = message_queue
        self.name = "CorrelationResearchAgent"
        logger.info(f"[{self.name}] Initialized. Ready for correlation analysis.")

    def _get_peers(self, ticker: str) -> List[str]:
        """Return sector peers for a given ticker."""
        peers = SECTOR_PEERS.get(ticker, DEFAULT_PEERS)
        # Remove the ticker itself
        return [p for p in peers if p != ticker][:5]  # Max 5 peers

    def _compute_rsi(self, series: pd.Series, period: int = 14) -> float:
        """Compute RSI from a price series."""
        try:
            delta = series.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)
            avg_gain = gain.rolling(period).mean()
            avg_loss = loss.rolling(period).mean()
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1]) if not rsi.empty else 50.0
        except Exception:
            return 50.0

    def _get_peer_trend(self, series: pd.Series) -> str:
        """Determine if the peer stock is trending up, down, or flat (last 5 days)."""
        try:
            if len(series) < 5:
                return "FLAT"
            change_5d = (series.iloc[-1] - series.iloc[-5]) / series.iloc[-5] * 100
            if change_5d > 1.5:
                return "RISING"
            elif change_5d < -1.5:
                return "FALLING"
            else:
                return "FLAT"
        except Exception:
            return "FLAT"

    def analyze(self, ticker: str, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Core analysis: compute correlation between ticker and its sector peers.
        Returns structured result with confirmation/divergence signal.
        """
        peers = self._get_peers(ticker)
        all_tickers = [ticker] + peers

        logger.info(f"[{self.name}] Analyzing {ticker} vs peers: {peers}")

        try:
            # Download 30 days of daily close prices
            data = yf.download(
                all_tickers,
                period=f"{lookback_days}d",
                interval="1d",
                progress=False,
                auto_adjust=True
            )

            if "Close" not in data:
                logger.warning(f"[{self.name}] No Close data returned.")
                return self._empty_result(ticker)

            close_df = data["Close"] if len(all_tickers) > 1 else data[["Close"]].rename(columns={"Close": ticker})

            # Ensure we have the main ticker
            if ticker not in close_df.columns:
                logger.warning(f"[{self.name}] Ticker {ticker} not in downloaded data.")
                return self._empty_result(ticker)

            # Drop columns with all NaN
            close_df = close_df.dropna(axis=1, how="all")
            close_df = close_df.dropna(axis=0, how="any")

            if close_df.empty or len(close_df) < 10:
                logger.warning(f"[{self.name}] Insufficient price data.")
                return self._empty_result(ticker)

            # Compute correlation matrix
            corr_matrix = close_df.pct_change().corr()
            ticker_corr = corr_matrix[ticker].drop(ticker).sort_values(ascending=False)

            # Build results for each peer
            results: List[CorrelationResult] = []
            confirms = 0
            diverges = 0

            for peer in peers:
                if peer not in close_df.columns:
                    continue
                try:
                    corr = float(ticker_corr.get(peer, 0.0))
                    peer_series = close_df[peer]
                    peer_trend = self._get_peer_trend(peer_series)
                    peer_rsi = self._compute_rsi(peer_series)

                    # Determine confirmation/divergence
                    # If corr > 0.7 and peer is RISING → confirms our bullish signal
                    # If corr > 0.7 and peer is FALLING → divergence (risky trade)
                    if corr > 0.7:
                        if peer_trend == "RISING":
                            signal = "CONFIRMS"
                            confirms += 1
                        elif peer_trend == "FALLING":
                            signal = "DIVERGES"
                            diverges += 1
                        else:
                            signal = "NEUTRAL"
                    else:
                        signal = "NEUTRAL"

                    results.append(CorrelationResult(
                        ticker=ticker,
                        peer=peer.replace(".NS", ""),
                        correlation=round(corr, 3),
                        peer_trend=peer_trend,
                        peer_rsi=round(peer_rsi, 1),
                        signal=signal,
                    ))
                except Exception as e:
                    logger.warning(f"[{self.name}] Peer {peer} analysis failed: {e}")

            # Sort by correlation strength
            results.sort(key=lambda x: abs(x.correlation), reverse=True)

            # Overall verdict
            if confirms >= 2:
                verdict = "SECTOR_CONFIRMING"
                verdict_text = "✅ Sector-wide breakout — HIGH CONFIDENCE signal"
            elif diverges >= 2:
                verdict = "SECTOR_DIVERGING"
                verdict_text = "⚠️ Peers are falling — RISKY TRADE, consider waiting"
            else:
                verdict = "MIXED"
                verdict_text = "⚖️ Mixed signals — Monitor closely, use strict SL"

            return {
                "ticker": ticker,
                "peers_analyzed": len(results),
                "verdict": verdict,
                "verdict_text": verdict_text,
                "confirms": confirms,
                "diverges": diverges,
                "correlations": [
                    {
                        "peer": r.peer,
                        "correlation": r.correlation,
                        "trend": r.peer_trend,
                        "rsi": r.peer_rsi,
                        "signal": r.signal,
                    }
                    for r in results
                ],
            }

        except Exception as e:
            logger.error(f"[{self.name}] Analysis error for {ticker}: {e}")
            return self._empty_result(ticker)

    def _empty_result(self, ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "peers_analyzed": 0,
            "verdict": "DATA_ERROR",
            "verdict_text": "⚪ Could not fetch peer data. Trade on price action alone.",
            "confirms": 0,
            "diverges": 0,
            "correlations": [],
        }

    def format_telegram_message(self, result: Dict[str, Any]) -> str:
        """Format correlation analysis result as a Telegram HTML message."""
        ticker_clean = result["ticker"].replace(".NS", "")
        lines = [
            f"🔗 <b>CORRELATION ANALYSIS: {ticker_clean}</b>",
            "",
            f"<b>{result['verdict_text']}</b>",
            f"Peers Analyzed: {result['peers_analyzed']} | "
            f"✅ {result['confirms']} Confirm | ⚠️ {result['diverges']} Diverge",
            "",
            "📊 <b>Sector Peer Breakdown:</b>",
        ]

        for c in result.get("correlations", []):
            icon = "✅" if c["signal"] == "CONFIRMS" else ("⚠️" if c["signal"] == "DIVERGES" else "⚪")
            trend_icon = "📈" if c["trend"] == "RISING" else ("📉" if c["trend"] == "FALLING" else "➡️")
            lines.append(
                f"  {icon} <b>{c['peer']}</b> | Corr: {c['correlation']:.2f} | "
                f"{trend_icon} {c['trend']} | RSI: {c['rsi']:.0f}"
            )

        lines.append("")
        lines.append("💡 <i>High correlation (>0.7) + same trend = strong signal</i>")
        return "\n".join(lines)

    async def run_for_signal(self, ticker: str) -> Dict[str, Any]:
        """Called by orchestrator when a new trade signal is generated."""
        result = self.analyze(ticker)
        logger.info(f"[{self.name}] {ticker} verdict: {result['verdict']}")
        return result

    async def run_on_demand(self, ticker: str) -> str:
        """Called by /correlate <TICKER> Telegram command."""
        result = self.analyze(ticker)
        return self.format_telegram_message(result)
