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

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Lista de activos actualizada
ASSETS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "binancecoin": "BNB",
    "tether": "USDT",
    "dai": "DAI",
    "usd-coin": "USDC",
    "ripple": "XRP",
    "cardano": "ADA"
}

# Generar teclado
def get_keyboard():
    buttons = []
    row = []
    for i, (crypto_id, symbol) in enumerate(ASSETS.items()):
        row.append(InlineKeyboardButton(symbol, callback_data=crypto_id))
        if (i + 1) % 3 == 0:  # 3 botones por fila
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# Obtener precios mejorado
def get_price(crypto_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd,eur"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if crypto_id in data:
            prices = data[crypto_id]
            return (
                f"*{ASSETS[crypto_id]}*\n\n"
                f"💵 USD: `{prices.get('usd', 'N/A')}`\n"
                f"💶 EUR: `{prices.get('eur', 'N/A')}`\n\n"
                f"🕓 _Actualizado: {datetime.now().strftime('%H:%M:%S')}_"
            )
        return "❌ Activo no encontrado"
    except Exception as e:
        logging.error(f"API Error: {e}")
        return "⚠️ Error al obtener datos. Intenta nuevamente."

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
    
    # Crear la aplicación y pasar el token
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Iniciar bot
    logging.info("Bot iniciado - Escuchando comandos...")
    application.run_polling()

if __name__ == "__main__":
    main()
