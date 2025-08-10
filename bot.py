import os
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from datetime import datetime

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")
COINCAP_API_KEY = "b34066586e40c21753e4882ca3cd8f1cbab9037e0eb2e274f02d168a6c8f58f5"  # Tu API key de CoinCap

# Mapeo de IDs de CoinCap (diferentes a CoinGecko)
ASSETS = {
    "bitcoin": {"symbol": "BTC", "name": "Bitcoin", "coincap_id": "bitcoin"},
    "ethereum": {"symbol": "ETH", "name": "Ethereum", "coincap_id": "ethereum"},
    "binance-coin": {"symbol": "BNB", "name": "Binance Coin", "coincap_id": "binance-coin"},
    "tether": {"symbol": "USDT", "name": "Tether", "coincap_id": "tether"},
    "dai": {"symbol": "DAI", "name": "Dai", "coincap_id": "dai"},
    "usd-coin": {"symbol": "USDC", "name": "USD Coin", "coincap_id": "usd-coin"},
    "ripple": {"symbol": "XRP", "name": "XRP", "coincap_id": "ripple"},
    "cardano": {"symbol": "ADA", "name": "Cardano", "coincap_id": "cardano"},
    "solana": {"symbol": "SOL", "name": "Solana", "coincap_id": "solana"},
    "dogecoin": {"symbol": "DOGE", "name": "Dogecoin", "coincap_id": "dogecoin"}
}

# Sistema de caché
PRICE_CACHE = {}
CACHE_DURATION = 30  # 30 segundos de caché para no exceder límites
REQUEST_DELAY = 0.5  # Pequeño delay entre requests

# Generar teclado (igual que antes)
def get_keyboard():
    buttons = []
    row = []
    for i, (crypto_id, data) in enumerate(ASSETS.items()):
        row.append(InlineKeyboardButton(data["symbol"], callback_data=crypto_id))
        if (i + 1) % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# Obtener precios de CoinCap
def get_price(crypto_id):
    try:
        # Verificar caché primero
        current_time = time.time()
        if crypto_id in PRICE_CACHE:
            cached_time, cached_data = PRICE_CACHE[crypto_id]
            if current_time - cached_time < CACHE_DURATION:
                return cached_data

        time.sleep(REQUEST_DELAY)  # Evitar rate limits
        
        coincap_id = ASSETS[crypto_id]["coincap_id"]
        headers = {"Authorization": f"Bearer {COINCAP_API_KEY}"}
        
        # 1. Obtener precio en USD
        url = f"https://api.coincap.io/v2/assets/{coincap_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            error_msg = f"⚠️ Error API CoinCap ({response.status_code})"
            if response.status_code == 429:
                error_msg += "\n🔔 Por favor espera unos segundos antes de intentar nuevamente."
            return error_msg
        
        usd_price = float(response.json()["data"]["priceUsd"])
        
        # 2. Obtener tasa EUR/USD
        eur_rate = requests.get("https://api.coincap.io/v2/rates/euro", headers=headers).json()
        eur_rate = float(eur_rate["data"]["rateUsd"])
        eur_price = usd_price / eur_rate
        
        # Formatear mensaje
        message = (
            f"*{ASSETS[crypto_id]['name']} ({ASSETS[crypto_id]['symbol']})*\n\n"
            f"💵 USD: `{usd_price:,.2f}`\n"
            f"💶 EUR: `{eur_price:,.2f}`\n\n"
            f"🕓 _Actualizado: {datetime.now().strftime('%H:%M:%S')}_"
        )
        
        # Actualizar caché
        PRICE_CACHE[crypto_id] = (current_time, message)
        return message
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return "⚠️ Error al obtener datos. Intenta nuevamente más tarde."

# Handlers (igual que antes)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💰 *Monitor de Criptoactivos* 💰\nSelecciona un activo:",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        text="⌛ Obteniendo datos...",
        reply_markup=get_keyboard()
    )
    
    message = get_price(query.data)
    await query.edit_message_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    logging.info("🤖 Bot iniciado - Usando CoinCap API")
    application.run_polling()

if __name__ == "__main__":
    main()
