import time
from portfolio import PortfolioManager
from risk_manager import RiskManager
from scanner import TechnicalScanner

def run_demo():
    print("="*65)
    print("📊 ALGOTRADER INDIA: INTERACTIVE CONSOLE DEMO & SIMULATION")
    print("="*65)
    print("Mode: Paper Trading (Zero Financial Risk)")
    print("Starting Capital: ₹1,00,000.00")
    print("Max Risk Per Trade: ₹1,000.00 (1%)")
    print("="*65 + "\n")

    portfolio = PortfolioManager()
    risk_mgr = RiskManager()
    
    # 1. Simulate an identified trade setup
    print("🔍 [STEP 1] Scanner detects high-probability setup on NSE:")
    mock_signal = {
        "ticker": "RELIANCE.NS",
        "symbol": "RELIANCE",
        "strategy": "20-Day Breakout + Volume Spike 🚀",
        "ltp": 1336.60,
        "stop_loss": 1300.00,
        "target": 1410.00,
        "reason": "Stock broke 20-day high with 1.45x volume surge. Bullish EMA alignment."
    }

    # Evaluate risk & sizing
    summary = portfolio.get_summary()
    valid, sizing = risk_mgr.evaluate_and_size_trade(
        entry_price=mock_signal["ltp"],
        stop_loss=mock_signal["stop_loss"],
        target=mock_signal["target"],
        available_cash=summary["cash_balance"],
        total_capital=summary["initial_capital"]
    )
    mock_signal.update(sizing)

    # 2. Display the card that will be sent to Father's Telegram
    print("\n📱 [TELEGRAM ALERT PREVIEW]")
    print("┌────────────────────────────────────────────────────────┐")
    print(f"│ 🚀 TRADE SETUP: {mock_signal['symbol']} (NSE)")
    print(f"│ Strategy: {mock_signal['strategy']}")
    print(f"│ Current Price (LTP): ₹{mock_signal['entry_price']:,.2f}")
    print(f"│ 🛑 Stop Loss:        ₹{mock_signal['stop_loss']:,.2f} (-2.7%)")
    print(f"│ 🎯 Target:           ₹{mock_signal['target']:,.2f} (+5.5%)")
    print(f"│ ⚖️ Risk/Reward:       1 : {mock_signal['risk_reward_ratio']}")
    print(f"│ 📦 Suggested Qty:    {mock_signal['quantity']} shares")
    print(f"│ 💵 Total Investment: ₹{mock_signal['total_investment']:,.2f}")
    print(f"│ 🛡️ Max Risk Allowed: ₹{mock_signal['max_risk_amount']:,.2f} (1.0% of capital)")
    print("│")
    print("│ [ ✅ Approve Buy ]        [ ❌ Dismiss ]")
    print("└────────────────────────────────────────────────────────┘")

    # 3. Simulate Father tapping "Approve Buy"
    print("\n👉 [STEP 2] Simulating Father tapping '[ ✅ Approve Buy ]' on Telegram...")
    time.sleep(1)
    
    can_open, msg = portfolio.can_open_position(mock_signal["total_investment"], mock_signal["ticker"])
    if not can_open:
        print(f"❌ Order rejected: {msg}")
        return

    pos = portfolio.open_position(mock_signal, mock_signal["quantity"], mock_signal["entry_price"])
    print(f"✅ Paper Trade Placed! Bought {pos['quantity']} shares of {pos['ticker']} @ ₹{pos['entry_price']}")
    
    # 4. Check Portfolio state
    print("\n💼 [STEP 3] Current Virtual Portfolio Status:")
    s = portfolio.get_summary()
    print(f"• Cash Balance:      ₹{s['cash_balance']:,.2f}")
    print(f"• Invested Capital:  ₹{s['invested_capital']:,.2f}")
    print(f"• Active Positions:  {s['open_positions_count']}")

    # 5. Simulate Market Movement towards Target
    print("\n📈 [STEP 4] Fast-forwarding simulation: Stock rallies to Target price ₹1,410.00...")
    time.sleep(1)
    simulated_prices = {"RELIANCE.NS": 1410.00}
    exits = portfolio.check_exits(simulated_prices)

    if exits:
        for ex in exits:
            print(f"\n🎉 🎯 ALERT: {ex['reason']}!")
            print(f"• Stock: {ex['ticker']}")
            print(f"• Sold {ex['quantity']} shares @ ₹{ex['exit_price']}")
            print(f"• Realized Profit: +₹{ex['pnl']:,.2f} (+{ex['pnl_pct']}%)")

    # 6. Final Report
    print("\n📊 [STEP 5] Final Performance & P&L Report:")
    final_s = portfolio.get_summary()
    print(f"• Total Portfolio Value: ₹{final_s['total_value']:,.2f}")
    print(f"• Net Return:            {final_s['net_return_pct']:+.2f}%")
    print(f"• Win Rate:              {final_s['win_rate']}%")
    print(f"• Available Cash:        ₹{final_s['cash_balance']:,.2f}")
    print("\n✅ Simulation complete. The system is ready to connect to Telegram!")

if __name__ == "__main__":
    run_demo()
