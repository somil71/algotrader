"""
Agent 2: News & Global Market Intelligence
-------------------------------------------
Fetches macro news from free RSS feeds and monitors:
  - Global indices: S&P 500, Nikkei, Hang Seng, FTSE
  - Currency: USD/INR, DXY
  - India-specific: Nifty 50, Nifty Bank
  - Free RSS sources: Moneycontrol, NSE, Yahoo Finance, Reuters India

Sends a morning briefing at 9:00 AM IST and intraday alerts
when significant macro events are detected.
Posts to Telegram via /news command and on significant moves.
"""

import logging
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("NewsGlobalAgent")


# --- Free News RSS Feeds (No API Key Required) ---
RSS_FEEDS = {
    "Moneycontrol Markets": "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rss.cms",
    "Reuters India Business": "https://feeds.reuters.com/reuters/INbusinessNews",
    "Yahoo Finance India": "https://finance.yahoo.com/rss/topfinstories",
}

# Global tickers to monitor
GLOBAL_TICKERS = {
    "S&P 500 (US)":    "^GSPC",
    "Nikkei 225 (JP)": "^N225",
    "Hang Seng (HK)":  "^HSI",
    "FTSE 100 (UK)":   "^FTSE",
    "Nifty 50 (IN)":   "^NSEI",
    "Nifty Bank (IN)": "^NSEBANK",
    "USD/INR":         "INR=X",
    "Gold (USD)":      "GC=F",
    "Crude Oil (USD)": "CL=F",
}

# Alert thresholds — notify if move > this % from previous close
ALERT_THRESHOLDS = {
    "^GSPC":  1.5,   # S&P 500 moves >1.5%
    "^N225":  2.0,   # Nikkei moves >2.0%
    "^HSI":   2.0,
    "^FTSE":  1.5,
    "^NSEI":  1.0,   # Nifty moves >1.0% (most relevant)
    "^NSEBANK": 1.5,
    "INR=X":  0.5,   # USD/INR moves >0.5%
    "GC=F":   1.5,   # Gold
    "CL=F":   2.0,   # Crude
}


class NewsGlobalAgent:
    """
    Agent 2: Global market intelligence and news monitoring.
    Runs at 9:00 AM IST for morning briefing, and on-demand via /news.
    """

    def __init__(self, message_queue: List):
        self.message_queue = message_queue
        self.name = "NewsGlobalAgent"
        self._last_prices: Dict[str, float] = {}  # Previous prices for % change calc
        logger.info(f"[{self.name}] Initialized. Watching {len(GLOBAL_TICKERS)} global markets.")

    # ─────────────────────────────────────────────
    #  SECTION 1: Global Market Snapshot
    # ─────────────────────────────────────────────

    def get_global_snapshot(self) -> Dict[str, Any]:
        """Fetch current prices and % changes for all global tickers."""
        snapshot = {}
        tickers_list = list(GLOBAL_TICKERS.values())
        alerts = []

        try:
            # Download 2 days of daily data to compute % change from yesterday's close
            data = yf.download(tickers_list, period="2d", interval="1d", progress=False)

            for label, ticker in GLOBAL_TICKERS.items():
                try:
                    if "Close" in data:
                        if len(tickers_list) == 1:
                            series = data["Close"].dropna()
                        else:
                            series = data["Close"][ticker].dropna() if ticker in data["Close"] else None

                        if series is not None and len(series) >= 2:
                            prev_close = float(series.iloc[-2])
                            current = float(series.iloc[-1])
                            change_pct = ((current - prev_close) / prev_close) * 100

                            snapshot[label] = {
                                "ticker": ticker,
                                "current": round(current, 2),
                                "prev_close": round(prev_close, 2),
                                "change_pct": round(change_pct, 2),
                                "direction": "🟢" if change_pct >= 0 else "🔴",
                            }

                            # Check alert threshold
                            threshold = ALERT_THRESHOLDS.get(ticker, 2.0)
                            if abs(change_pct) >= threshold:
                                alerts.append({
                                    "market": label,
                                    "ticker": ticker,
                                    "change_pct": change_pct,
                                    "current": current,
                                })
                except Exception as e:
                    logger.warning(f"[{self.name}] Could not get data for {ticker}: {e}")
                    snapshot[label] = {"ticker": ticker, "current": None, "change_pct": None, "direction": "⚪"}

        except Exception as e:
            logger.error(f"[{self.name}] Global snapshot fetch failed: {e}")

        return {"markets": snapshot, "alerts": alerts}

    def get_market_sentiment(self, snapshot: Dict) -> str:
        """
        Derive overall market sentiment from global data:
        BULLISH / NEUTRAL / BEARISH
        """
        markets = snapshot.get("markets", {})
        up_count = sum(1 for m in markets.values() if (m.get("change_pct") or 0) > 0)
        down_count = sum(1 for m in markets.values() if (m.get("change_pct") or 0) < 0)
        total = up_count + down_count
        if total == 0:
            return "NEUTRAL"
        ratio = up_count / total
        if ratio >= 0.65:
            return "BULLISH 🐂"
        elif ratio <= 0.35:
            return "BEARISH 🐻"
        else:
            return "NEUTRAL ⚖️"

    # ─────────────────────────────────────────────
    #  SECTION 2: News Headlines
    # ─────────────────────────────────────────────

    def fetch_news_headlines(self, max_per_source: int = 3) -> List[Dict[str, str]]:
        """Fetch top headlines from free RSS feeds. No API key needed."""
        all_headlines = []
        headers = {"User-Agent": "Mozilla/5.0 AlgoTrader-NewsBot/1.0"}

        for source_name, url in RSS_FEEDS.items():
            try:
                resp = requests.get(url, timeout=8, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"[{self.name}] RSS fetch failed for {source_name}: HTTP {resp.status_code}")
                    continue

                root = ET.fromstring(resp.content)
                items = root.findall(".//item")
                count = 0
                for item in items:
                    if count >= max_per_source:
                        break
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    pub_date = item.findtext("pubDate", "").strip()
                    if title:
                        all_headlines.append({
                            "source": source_name,
                            "title": title,
                            "link": link,
                            "pub_date": pub_date,
                        })
                        count += 1

            except Exception as e:
                logger.warning(f"[{self.name}] Error parsing RSS from {source_name}: {e}")

        logger.info(f"[{self.name}] Fetched {len(all_headlines)} headlines from {len(RSS_FEEDS)} sources.")
        return all_headlines

    # ─────────────────────────────────────────────
    #  SECTION 3: Telegram Message Formatters
    # ─────────────────────────────────────────────

    def format_morning_briefing(self, snapshot: Dict, headlines: List[Dict]) -> str:
        """Format the full morning briefing message for Telegram."""
        sentiment = self.get_market_sentiment(snapshot)
        markets = snapshot.get("markets", {})
        alerts = snapshot.get("alerts", [])

        lines = [
            "🌅 <b>MORNING MARKET BRIEFING</b>",
            f"🗓️ {datetime.now().strftime('%A, %d %b %Y')} | <b>Sentiment: {sentiment}</b>",
            "",
        ]

        # Key markets
        lines.append("📊 <b>Global Markets</b>")
        for label, m in markets.items():
            if m.get("current") is None:
                lines.append(f"  {m['direction']} {label}: <i>data unavailable</i>")
            else:
                lines.append(
                    f"  {m['direction']} {label}: "
                    f"{m['current']:,.1f} ({m['change_pct']:+.2f}%)"
                )

        # Alerts
        if alerts:
            lines.append("")
            lines.append("⚠️ <b>Significant Moves (Threshold Breach)</b>")
            for a in alerts:
                direction = "📈 UP" if a["change_pct"] > 0 else "📉 DOWN"
                lines.append(f"  {direction} {a['market']}: {a['change_pct']:+.2f}%")

        # News
        if headlines:
            lines.append("")
            lines.append("📰 <b>Top Market Headlines</b>")
            for h in headlines[:6]:
                lines.append(f"  • <b>{h['source']}</b>: {h['title'][:80]}...")

        lines.append("")
        lines.append("💡 <i>Use /scan to find today's trading setups</i>")
        return "\n".join(lines)

    def format_alert_message(self, alerts: List[Dict]) -> str:
        """Format an intraday alert for large global moves."""
        lines = ["🚨 <b>GLOBAL MARKET ALERT</b>", ""]
        for a in alerts:
            direction = "📈 Surging" if a["change_pct"] > 0 else "📉 Falling"
            lines.append(f"{direction}: <b>{a['market']}</b> {a['change_pct']:+.2f}%")
        lines.append("")
        lines.append("⚡ Consider reviewing open positions. Use /portfolio to check.")
        return "\n".join(lines)

    # ─────────────────────────────────────────────
    #  SECTION 4: Main Run (called by orchestrator)
    # ─────────────────────────────────────────────

    async def run_morning_briefing(self) -> Tuple[str, List[Dict]]:
        """
        Full morning run: fetch global snapshot + headlines.
        Returns (telegram_message, alerts_list).
        """
        logger.info(f"[{self.name}] Running morning briefing...")
        snapshot = self.get_global_snapshot()
        headlines = self.fetch_news_headlines(max_per_source=3)
        message = self.format_morning_briefing(snapshot, headlines)
        alerts = snapshot.get("alerts", [])
        logger.info(f"[{self.name}] Morning briefing ready. Alerts: {len(alerts)}")
        return message, alerts

    async def run_intraday_check(self) -> Tuple[str, bool]:
        """
        Quick intraday check — only fetches market snapshot (no news).
        Returns (alert_message, should_send_alert).
        """
        snapshot = self.get_global_snapshot()
        alerts = snapshot.get("alerts", [])
        if alerts:
            msg = self.format_alert_message(alerts)
            return msg, True
        return "", False

    async def run_on_demand(self) -> str:
        """Called when user sends /news command."""
        snapshot = self.get_global_snapshot()
        headlines = self.fetch_news_headlines(max_per_source=2)
        return self.format_morning_briefing(snapshot, headlines)
