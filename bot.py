import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import requests
from datetime import datetime
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from datetime import datetime
import time

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Lista de activos actualizada con IDs correctos
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

# Obtener precios con mejor manejo de errores
def get_price(crypto_id):
    try:
        # Verificar si el ID es válido
        if crypto_id not in ASSETS:
            return "❌ Activo no reconocido"
        
        # Intentar obtener datos de CoinGecko
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd,eur"
        response = requests.get(url, timeout=15)
        
        # Verificar respuesta HTTP
        if response.status_code != 200:
            error_msg = f"⚠️ Error API ({response.status_code})"
            if response.status_code == 429:
                error_msg += " - Límite de solicitudes excedido"
            return error_msg
        
        data = response.json()
        
        # Verificar si se recibieron datos válidos
        if not data or crypto_id not in data:
            return "⚠️ No se encontraron datos para este activo"
        
        prices = data[crypto_id]
        usd_price = prices.get('usd', 'N/A')
        eur_price = prices.get('eur', 'N/A')
        
        # Formatear precios
        if isinstance(usd_price, float):
            usd_price = f"{usd_price:,.2f}"
        if isinstance(eur_price, float):
            eur_price = f"{eur_price:,.2f}"
        
        return (
            f"*{ASSETS[crypto_id]['name']} ({ASSETS[crypto_id]['symbol']})*\n\n"
            f"💵 USD: `{usd_price}`\n"
            f"💶 EUR: `{eur_price}`\n\n"
            f"🕓 _Actualizado: {datetime.now().strftime('%H:%M:%S')}_"
        )
        
    except requests.exceptions.Timeout:
        return "⏱️ Tiempo de espera agotado. Por favor intenta nuevamente."
    except requests.exceptions.RequestException as e:
        logging.error(f"Error de conexión: {e}")
        return "🔌 Error de conexión con la API"
    except Exception as e:
        logging.exception(f"Error inesperado: {e}")
        return "⚠️ Error inesperado al obtener datos"

# Handler de comandos
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
        parse_mode="Markdown",
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
    # Configurar logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Iniciar bot
    logging.info("🤖 Bot iniciado - Escuchando comandos...")
    application.run_polling()

if __name__ == "__main__":
    main()
