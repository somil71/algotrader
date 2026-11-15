import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Telegram Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Trading Mode
PAPER_TRADING = True  # Always start in Paper Trading mode (Zero real financial risk)

# Capital & Risk Management Settings
INITIAL_CAPITAL = 100000.0   # Virtual capital in INR: ₹1,00,000
MAX_RISK_PER_TRADE = 1000.0  # Max risk in INR per trade: ₹1,000 (1% of ₹1 Lakh)
MAX_OPEN_POSITIONS = 4       # Max simultaneous active swing positions
MAX_CAPITAL_PER_TRADE_PCT = 0.35  # Max 35% of capital in a single stock

# Target Stock Universe (Liquid Large & Midcap NSE Equities)
WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "LT.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "HINDUNILVR.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "BAJFINANCE.NS",
    "M&M.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "TATASTEEL.NS",
    "COALINDIA.NS",
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "WIPRO.NS",
    "ULTRACEMCO.NS",
    "NESTLEIND.NS",
    "ASIANPAINT.NS",
    "HCLTECH.NS",
    "BAJAJFINSV.NS",
    "JSWSTEEL.NS",
    "ONGC.NS",
    "GRASIM.NS",
    "TECHM.NS",
    "HINDALCO.NS",
    "CIPLA.NS",
    "BPCL.NS",
    "DRREDDY.NS",
    "APOLLOHOSP.NS",
    "SHRIRAMFIN.NS",
    "TRENT.NS",
    "BEL.NS",
    "HAL.NS"
]

# Market Timing (Indian Standard Time - IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30
