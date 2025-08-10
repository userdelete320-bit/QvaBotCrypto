import os
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from datetime import datetime

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Lista de activos
ASSETS = {
    "bitcoin": {"symbol": "BTC", "name": "Bitcoin"},
    "ethereum": {"symbol": "ETH", "name": "Ethereum"},
    "binancecoin": {"symbol": "BNB", "name": "Binance Coin"},
    "tether": {"symbol": "USDT", "name": "Tether"},
    "dai": {"symbol": "DAI", "name": "Dai"},
    "usd-coin": {"symbol": "USDC", "name": "USD Coin"},
    "ripple": {"symbol": "XRP", "name": "XRP"},
    "cardano": {"symbol": "ADA", "name": "Cardano"},
    "solana": {"symbol": "SOL", "name": "Solana"},
    "dogecoin": {"symbol": "DOGE", "name": "Dogecoin"}
}

# Sistema de caché
PRICE_CACHE = {}
CACHE_DURATION = 60  # Almacenar precios por 60 segundos
LAST_REQUEST_TIME = 0
REQUEST_DELAY = 1.5  # Retardo mínimo entre solicitudes (1.5 segundos)

# Generar teclado
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

# Obtener precios con caché y manejo de tasa
def get_price(crypto_id):
    global LAST_REQUEST_TIME
    
    # Verificar si tenemos un resultado en caché válido
    current_time = time.time()
    if crypto_id in PRICE_CACHE:
        cached_time, cached_message = PRICE_CACHE[crypto_id]
        if current_time - cached_time < CACHE_DURATION:
            return cached_message
    
    # Respetar el límite de tasa
    time_since_last = current_time - LAST_REQUEST_TIME
    if time_since_last < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - time_since_last)
    
    try:
        # Consultar la API de CoinGecko
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd,eur"
        response = requests.get(url, timeout=15)
        LAST_REQUEST_TIME = time.time()
        
        # Manejar respuesta HTTP
        if response.status_code != 200:
            if response.status_code == 429:
                # Manejar específicamente el error 429
                return "⚠️ Demasiadas solicitudes. Por favor espera 1 minuto antes de intentar nuevamente."
            return f"⚠️ Error API ({response.status_code})"
        
        data = response.json()
        
        # Verificar si se recibieron los datos esperados
        if crypto_id not in data:
            return "⚠️ No se encontraron datos para este activo"
        
        prices = data[crypto_id]
        usd_price = prices.get('usd', 'N/A')
        eur_price = prices.get('eur', 'N/A')
        
        # Formatear los precios
        if isinstance(usd_price, float):
            usd_price = f"{usd_price:,.2f}"
        if isinstance(eur_price, float):
            eur_price = f"{eur_price:,.2f}"
        
        message = (
            f"*{ASSETS[crypto_id]['name']} ({ASSETS[crypto_id]['symbol']})*\n\n"
            f"💵 USD: `{usd_price}`\n"
            f"💶 EUR: `{eur_price}`\n\n"
            f"🕓 _Actualizado: {datetime.now().strftime('%H:%M:%S')}_"
        )
        
        # Actualizar caché
        PRICE_CACHE[crypto_id] = (current_time, message)
        
        return message
        
    except requests.exceptions.Timeout:
        return "⏱️ Tiempo de espera agotado. Por favor intenta nuevamente."
    except Exception as e:
        logging.error(f"Error inesperado: {e}")
        # Intentar devolver datos en caché si están disponibles
        if crypto_id in PRICE_CACHE:
            _, cached_message = PRICE_CACHE[crypto_id]
            return cached_message + "\n\n⚠️ (Datos pueden estar desactualizados)"
        return "⚠️ Error inesperado al obtener datos"

# Handlers asíncronos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💰 *Monitor de Criptoactivos* 💰\nSelecciona un activo:",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    # Mostrar mensaje de carga
    await query.edit_message_text(
        text="⌛ Obteniendo datos...",
        reply_markup=get_keyboard()
    )
    
    # Obtener datos y actualizar mensaje
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
    logging.info("🤖 Bot iniciado - Usando CoinGecko con caché")
    application.run_polling()

if __name__ == "__main__":
    main()
