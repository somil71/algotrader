import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import config

logger = logging.getLogger("OrderPlanner")
PLANNER_FILE = Path("E:/TRADING/custom_orders.json")

class CustomOrderPlanner:
    """
    Allows Father to specify a stock, custom quantity, and target entry price
    a day earlier. The bot will monitor it continuously during market hours.
    """
    def __init__(self, filepath: Path = PLANNER_FILE):
        self.filepath = filepath
        self.planned_orders = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading custom orders: {e}")
        return []

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.planned_orders, f, indent=2)

    def add_planned_order(self, 
                          symbol: str, 
                          trigger_price: float, 
                          quantity: int, 
                          direction: str = "ABOVE", # 'ABOVE' (buy breakout) or 'BELOW' (buy dip)
                          stop_loss: Optional[float] = None,
                          target: Optional[float] = None) -> Dict[str, Any]:
        clean_symbol = symbol.upper().replace(".NS", "")
        ticker = f"{clean_symbol}.NS"

        sl = stop_loss if stop_loss else round(trigger_price * 0.97, 2)
        tgt = target if target else round(trigger_price * 1.05, 2)

        order_plan = {
            "id": f"{clean_symbol}_{int(trigger_price)}_{int(datetime.now().timestamp())}",
            "symbol": clean_symbol,
            "ticker": ticker,
            "trigger_price": round(trigger_price, 2),
            "quantity": quantity,
            "direction": direction,
            "stop_loss": sl,
            "target_1": tgt,
            "target_2": round(trigger_price * 1.10, 2),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "PENDING"
        }
        
        self.planned_orders.append(order_plan)
        self._save()
        logger.info(f"Added planned order: {order_plan}")
        return order_plan

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        return [o for o in self.planned_orders if o.get("status") == "PENDING"]

    def check_triggers(self, current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """Checks if any planned stock reached Father's specified price."""
        triggered = []
        for order in self.planned_orders:
            if order.get("status") != "PENDING":
                continue

            ticker = order["ticker"]
            ltp = current_prices.get(ticker)
            if not ltp:
                continue

            trig_price = order["trigger_price"]
            direction = order.get("direction", "ABOVE")

            condition_met = False
            if direction == "ABOVE" and ltp >= trig_price:
                condition_met = True
            elif direction == "BELOW" and ltp <= trig_price:
                condition_met = True

            if condition_met:
                order["status"] = "TRIGGERED"
                order["triggered_price"] = ltp
                order["triggered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                triggered.append(order)

        if triggered:
            self._save()
        return triggered

    def cancel_planned_order(self, symbol: str) -> bool:
        clean = symbol.upper().replace(".NS", "")
        initial_len = len(self.planned_orders)
        self.planned_orders = [o for o in self.planned_orders if o["symbol"] != clean or o.get("status") != "PENDING"]
        self._save()
        return len(self.planned_orders) < initial_len
