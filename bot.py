import os
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from datetime import datetime

# --- Configuración ---
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Tu token de Telegram Bot
COINCAP_API_KEY = "b34066586e40c21753e4882ca3cd8f1cbab9037e0eb2e274f02d168a6c8f58f5"  # Tu API key de CoinCap
COINCAP_API_URL = "https://rest.coincap.io/v3"  # Endpoint de la API v3

# --- Mapeo de activos ---
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

# --- Caché de precios ---
PRICE_CACHE = {}
CACHE_DURATION = 30  # 30 segundos de caché
REQUEST_DELAY = 0.5  # Delay entre requests para evitar rate limits

# --- Generar teclado interactivo ---
def get_keyboard():
    buttons = []
    row = []
    for i, (crypto_id, data) in enumerate(ASSETS.items()):
        row.append(InlineKeyboardButton(data["symbol"], callback_data=crypto_id))
        if (i + 1) % 3 == 0:  # 3 botones por fila
            buttons.append(row)
            row = []
    if row:  # Añadir fila incompleta
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# --- Obtener precios desde CoinCap ---
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
        url = f"{COINCAP_API_URL}/assets/{coincap_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            error_msg = f"⚠️ Error API ({response.status_code})"
            if response.status_code == 429:
                error_msg += "\n🔔 Límite de solicitudes alcanzado. Espera 1 minuto."
            elif response.status_code == 404:
                error_msg += "\n🔔 Activo no encontrado. ¿ID correcto?"
            return error_msg
        
        usd_price = float(response.json()["data"]["priceUsd"])
        
        # 2. Obtener tasa EUR/USD
        eur_response = requests.get(f"{COINCAP_API_URL}/rates/euro", headers=headers)
        eur_rate = float(eur_response.json()["data"]["rateUsd"])
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
        
    except requests.exceptions.Timeout:
        return "⏱️ Tiempo de espera agotado. Intenta nuevamente."
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return "⚠️ Error inesperado. Intenta más tarde."

# --- Handlers de Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💰 *Monitor de Criptomonedas* 💰\nSelecciona un activo:",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    # Mensaje de carga
    await query.edit_message_text(
        text="⌛ Obteniendo datos...",
        reply_markup=get_keyboard()
    )
    
    # Obtener y mostrar precio
    message = get_price(query.data)
    await query.edit_message_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

# --- Main ---
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Inicializar bot
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    
    logging.info("🤖 Bot iniciado - Usando CoinCap API v3")
    application.run_polling()

if __name__ == "__main__":
    main()
