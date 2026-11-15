import math
import config
from typing import Dict, Any, Tuple

class RiskManager:
    def __init__(self, max_risk_per_trade: float = config.MAX_RISK_PER_TRADE,
                 max_capital_pct: float = config.MAX_CAPITAL_PER_TRADE_PCT):
        self.max_risk = max_risk_per_trade
        self.max_capital_pct = max_capital_pct

    def evaluate_and_size_trade(self,
                                entry_price: float,
                                stop_loss: float,
                                target_1: float,
                                target_2: float,
                                atr: float,
                                available_cash: float,
                                total_capital: float) -> Tuple[bool, Dict[str, Any]]:
        """
        Fine-tuned Institutional Position Sizing:
        - Strict capital protection (Max risk per trade, e.g. ₹1,000)
        - Multi-target scale-out: Target 1 (1:1.5 R:R) & Target 2 (1:3.0 R:R)
        - Volatility-adjusted ATR stop distance
        """
        if entry_price <= 0 or stop_loss <= 0 or target_1 <= 0:
            return False, {"reason": "Invalid price inputs"}

        if stop_loss >= entry_price:
            return False, {"reason": "Stop Loss must be strictly below Entry Price for Long setups"}

        if target_1 <= entry_price:
            return False, {"reason": "Target 1 must be strictly above Entry Price"}

        # 1. Risk calculation
        risk_per_share = entry_price - stop_loss
        reward_1 = target_1 - entry_price
        rr_1 = reward_1 / risk_per_share

        if rr_1 < 1.3:
            return False, {
                "reason": f"Risk-Reward too low (1:{rr_1:.2f}). Minimum required is 1:1.3"
            }

        # 2. Size by max risk allowed
        raw_qty = math.floor(self.max_risk / risk_per_share)
        if raw_qty < 1:
            return False, {"reason": "Stock volatility exceeds max risk threshold"}

        # Even number preference for clean 50% partial exit
        if raw_qty > 2 and raw_qty % 2 != 0:
            raw_qty -= 1

        # 3. Cap by portfolio concentration limits
        max_allowed_investment = min(available_cash, total_capital * self.max_capital_pct)
        max_shares_by_capital = math.floor(max_allowed_investment / entry_price)

        final_qty = min(raw_qty, max_shares_by_capital)
        if final_qty < 1:
            return False, {
                "reason": f"Not enough cash for minimum 1 share (Need ₹{entry_price:.2f}, Max Allowed ₹{max_allowed_investment:.2f})"
            }

        total_investment = round(final_qty * entry_price, 2)
        total_risk_incurred = round(final_qty * risk_per_share, 2)
        potential_gain_t1 = round((final_qty * 0.5) * (target_1 - entry_price), 2)
        potential_gain_t2 = round((final_qty * 0.5) * (target_2 - entry_price), 2)

        return True, {
            "quantity": final_qty,
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "target": round(target_1, 2),
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "atr": round(atr, 2),
            "risk_per_share": round(risk_per_share, 2),
            "risk_reward_ratio": round(rr_1, 2),
            "total_investment": total_investment,
            "max_risk_amount": total_risk_incurred,
            "potential_gain_t1": potential_gain_t1,
            "potential_gain_t2": potential_gain_t2,
            "risk_pct_of_capital": round((total_risk_incurred / total_capital) * 100, 2)
        }
