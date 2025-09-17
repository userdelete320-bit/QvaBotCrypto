from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_welcome_keyboard

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_message = (
        "🌟 Bienvenido al Sistema de Trading QVA Crypto 🌟\n\n"
        "Este bot te permite operar con criptomonedas de forma sencilla y segura. "
        "Con nuestro sistema podrás:\n\n"
        "• 📈 Realizar operaciones de COMPRA/VENTA\n"
        "• 🛑 Configurar Stop Loss y Take Profit\n"
        "• 💰 Gestionar tu saldo en CUP\n"
        "• 📊 Monitorear tus operaciones en tiempo real\n"
        "• 🔔 Recibir alertas cuando se alcancen tus objetivos\n\n"
        "Todo calculado automáticamente en pesos cubanos (CUP) usando la tasa actual de USDT.\n\n"
        "¡Comienza ahora y lleva tu trading al siguiente nivel!"
    )
    
    await update.message.reply_text(welcome_message, reply_markup=get_welcome_keyboard())
