import os
import logging
from typing import Dict, Any, Optional
import pyotp
import config

logger = logging.getLogger("KotakBroker")

class KotakNeoBroker:
    def __init__(self):
        self.consumer_key = os.getenv("KOTAK_CONSUMER_KEY", "4b8cbb57-32df-46ac-a202-409f592d31c3")
        self.mobile_number = os.getenv("KOTAK_MOBILE_NUMBER", "")
        self.ucc = os.getenv("KOTAK_UCC", "")              # Client Code
        self.mpin = os.getenv("KOTAK_MPIN", "")            # 6-digit App MPIN
        self.totp_secret = os.getenv("KOTAK_TOTP_SECRET", "") # TOTP Secret key
        self.client = None
        self.is_authenticated = False

    def initialize(self) -> bool:
        """Initializes and authenticates with Kotak Neo API."""
        if config.PAPER_TRADING:
            logger.info("Operating in PAPER TRADING mode. Kotak live orders disabled.")
            return True

        if not self.consumer_key:
            logger.warning("KOTAK_CONSUMER_KEY missing. Falling back to Paper Trading.")
            return False

        try:
            from neo_api_client import NeoAPI
            
            self.client = NeoAPI(
                consumer_key=self.consumer_key,
                environment="prod"
            )

            # Step 1: TOTP Login (View Access)
            if self.totp_secret and (self.mobile_number or self.ucc):
                totp_code = pyotp.TOTP(self.totp_secret).now()
                login_resp = self.client.totp_login(
                    mobile_number=self.mobile_number if self.mobile_number else None,
                    ucc=self.ucc if self.ucc else None,
                    totp=totp_code
                )
                logger.info("Kotak Neo TOTP Login step completed.")

                # Step 2: Validate MPIN (Trading Access)
                if self.mpin:
                    validate_resp = self.client.totp_validate(mpin=self.mpin)
                    logger.info("Kotak Neo MPIN validated. Full trading permissions enabled.")
                    self.is_authenticated = True
                    return True
                else:
                    logger.warning("KOTAK_MPIN not provided. Only view access available.")
                    return False
            else:
                logger.warning("Kotak login credentials (Mobile/UCC, TOTP, MPIN) not fully set in .env.")
                return False

        except Exception as e:
            logger.error(f"Failed to authenticate with Kotak Neo API: {e}")
            return False

    def place_equity_order(self, 
                           symbol: str, 
                           quantity: int, 
                           transaction_type: str = "B", # 'B' for Buy, 'S' for Sell
                           order_type: str = "MKT",     # 'MKT' or 'L'
                           price: float = 0.0,
                           product: str = "CNC"         # 'CNC' for Delivery/Swing
                           ) -> Dict[str, Any]:
        """
        Places order on NSE Cash Market (nse_cm) via Kotak Neo API.
        If in Paper Trading mode or unauthenticated, simulates order safely.
        """
        clean_symbol = symbol.replace(".NS", "").upper()

        if config.PAPER_TRADING or not self.client or not self.is_authenticated:
            return {
                "status": "success",
                "order_id": f"PAPER_{clean_symbol}_{quantity}",
                "mode": "PAPER_TRADING",
                "symbol": clean_symbol,
                "quantity": quantity,
                "transaction_type": transaction_type,
                "price": price,
                "message": "Order simulated successfully in virtual paper portfolio."
            }

        try:
            resp = self.client.place_order(
                exchange_segment="nse_cm",
                product=product,
                price=str(price) if order_type == "L" else "0",
                order_type=order_type,
                quantity=str(quantity),
                validity="DAY",
                trading_symbol=f"{clean_symbol}-EQ",
                transaction_type=transaction_type,
                amo="NO",
                disclosed_quantity="0"
            )
            logger.info(f"Kotak Neo live order response: {resp}")
            return {
                "status": "success",
                "order_id": resp.get("nOrdNo", "LIVE_ORDER"),
                "mode": "LIVE_KOTAK_NEO",
                "raw_response": resp
            }
        except Exception as e:
            logger.error(f"Error placing live order on Kotak Neo: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
