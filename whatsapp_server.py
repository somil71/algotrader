from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from portfolio import PortfolioManager
from scanner import TechnicalScanner
from kotak_broker import KotakNeoBroker
from whatsapp_bot import WhatsAppTradingBot

app = FastAPI(title="WhatsApp Trading Bot")

portfolio = PortfolioManager()
scanner = TechnicalScanner()
broker = KotakNeoBroker()
broker.initialize()
wa_bot = WhatsAppTradingBot(portfolio, scanner, broker)

@app.post("/whatsapp")
async def whatsapp_webhook(From: str = Form(...), Body: str = Form(...)):
    """Receives incoming messages from Father on WhatsApp."""
    reply_text = wa_bot.handle_incoming_message(from_number=From, message_text=Body)
    
    resp = MessagingResponse()
    resp.message(reply_text)
    return Response(content=str(resp), media_type="application/xml")

@app.get("/")
def home():
    return {"status": "WhatsApp Trading Bot is active and listening"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
