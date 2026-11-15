# 📈 AlgoTrader India (Father's Assistant)

A semi-automated, risk-managed algorithmic trading system built for Indian Equities (NSE). Designed specifically to be safe, transparent, and easy for beginners:

- **100% Human-in-the-Loop:** The algorithm scans the market and does the math, but your father confirms trades with **1 click on Telegram**. No runaway bots.
- **Zero Financial Risk (Paper Trading Mode):** Starts with virtual ₹1,00,000 capital and live NSE price feeds so he can practice stress-free.
- **Strict Risk Management:** Automatically sizes positions so no trade ever risks more than ₹1,000 (1% of capital).

---

## 🚀 Quick Start in 3 Minutes

### 1. Run the Interactive Simulation (Instant)
Test the entire pipeline in your terminal right now without any setup:
```bash
python test_simulation.py
```

### 2. Connect Telegram (2 Minutes, Free)
To get signal alerts directly on your father's phone:
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, give it a name (e.g., `DadTradeBot`), and copy the **Bot Token**.
3. Open `@userinfobot` on Telegram to get your numeric **Chat ID**.
4. Paste them into `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Run the live assistant:
   ```bash
   python main.py
   ```
6. Open your bot in Telegram and tap `/start`!

---

## 📱 Telegram Commands for Dad

| Command | Action |
| :--- | :--- |
| `/scan` | Scans Nifty 100 stocks right now for high-probability setups |
| `/portfolio` | Shows active trades, invested amount, and live unrealized P&L |
| `/pnl` | Performance report with win rate and net profit |
| `/close <SYMBOL>` | Manually exit a trade before target/stop loss is hit |
| `/help` | Explains the strategies and safety rules |

---

## 🛡️ Built-in Safety Engine
- **Max Loss per Trade:** Capped at ₹1,000.
- **Max Open Positions:** Capped at 4 concurrent stocks.
- **Target / Stop-Loss Monitoring:** Checked continuously; automatically triggers exit alerts.
- **Risk-to-Reward Filter:** Any setup with an R:R below 1:1.4 is automatically rejected.
