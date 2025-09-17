import os
import logging
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, JobQueue
)
from config import TOKEN, ASSETS, GROUP_ID  # Importar ASSETS y GROUP_ID
from handlers.start import start
from handlers.trade import (
    process_leverage_selection, recibir_monto_riesgo, set_sl_tp, 
    confirm_trade, cancel_trade
)
from handlers.balance import (
    show_balance, solicitar_deposito, solicitar_retiro, 
    recibir_monto, recibir_datos
)
from handlers.operations import (
    show_operations, show_history, show_operation_detail,
    show_history_detail, close_operation, check_operation
)
from handlers.admin import (
    set_saldo, set_group_id, get_chat_id,
    approve_request, reject_request, receive_rejection_reason
)
from jobs import keep_alive
from keyboards import get_main_keyboard, get_navigation_keyboard, get_currency_keyboard, get_trade_keyboard, get_apalancamiento_keyboard
from utils import get_current_price

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def error_handler(update, context):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    state = user_data.get('state')
    text = update.message.text.strip()
    
    if state == 'esperando_monto_riesgo':
        await recibir_monto_riesgo(update, context)
    elif state in ['esperando_sl', 'esperando_tp']:
        await set_sl_tp(update, context)
    elif state in ['solicitud_deposito', 'solicitud_retiro']:
        await recibir_monto(update, context)
    elif state == 'solicitud_retiro_datos':
        await recibir_datos(update, context)
    elif 'rechazando_solicitud' in user_data:
        await receive_rejection_reason(update, context)
    elif 'awaiting_custom_leverage' in user_data:
        # Manejar apalancamiento personalizado
        try:
            leverage = float(text)
            if leverage <= 0:
                await update.message.reply_text("❌ El apalancamiento debe ser mayor a 0. Intenta nuevamente.")
                return
                
            custom_data = user_data['awaiting_custom_leverage']
            asset_id = custom_data['asset_id']
            currency = custom_data['currency']
            operation_type = custom_data['operation_type']
            
            await process_leverage_selection(update, context, asset_id, currency, operation_type, leverage)
            
            del user_data['awaiting_custom_leverage']
        except ValueError:
            await update.message.reply_text("❌ Por favor, envía un número válido para el apalancamiento.")
    elif 'modifying_sl' in user_data or 'modifying_tp' in user_data:
        try:
            value = float(text)
            if 'modifying_sl' in user_data:
                op_id = user_data['modifying_sl']
                supabase.table('operations').update({'sl_price': value}).eq('id', op_id).execute()
                await update.message.reply_text("✅ Stop Loss actualizado correctamente.")
                del user_data['modifying_sl']
            elif 'modifying_tp' in user_data:
                op_id = user_data['modifying_tp']
                supabase.table('operations').update({'tp_price': value}).eq('id', op_id).execute()
                await update.message.reply_text("✅ Take Profit actualizado correctamente.")
                del user_data['modifying_tp']
        except ValueError:
            await update.message.reply_text("❌ Por favor, envía un número válido.")
    else:
        await update.message.reply_text(
            "No entiendo ese comando. Usa /start para comenzar.",
            reply_markup=get_navigation_keyboard()
        )

async def handle_photo(update, context):
    user_data = context.user_data
    if 'solicitud' in user_data and 'monto' in user_data['solicitud'] and user_data['solicitud']['tipo'] == 'deposito':
        await recibir_datos(update, context)

async def button_click(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    data = query.data
    
    # Navegación principal
    if data == "start_trading":
        await query.edit_message_text("Selecciona un activo para operar:", reply_markup=get_main_keyboard())
    elif data == "back_main":
        await query.edit_message_text("Selecciona un activo para operar:", reply_markup=get_main_keyboard())
    
    # Selección de activos y operaciones
    elif data.startswith("asset_"):
        asset_id = data.split("_")[1]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"Has seleccionado {asset['emoji']} {asset['name']} ({asset['symbol']})\n\n"
            "Selecciona la moneda para operar:",
            reply_markup=get_currency_keyboard(asset_id)
        )
    elif data.startswith("currency_"):
        parts = data.split("_")
        asset_id = parts[1]
        currency = parts[2]
        asset = ASSETS[asset_id]
        
        price = get_current_price(asset_id, currency)
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Precio actual: {price:.8f} {currency}\n\n"
            "Selecciona el tipo de operación:",
            reply_markup=get_trade_keyboard(asset_id, currency)
        )
    elif data.startswith("trade_"):
        parts = data.split("_")
        asset_id = parts[1]
        currency = parts[2]
        operation_type = parts[3]
        asset = ASSETS[asset_id]
        
        operation_text = "COMPRA" if operation_type == "buy" else "VENTA"
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {operation_text}\n\n"
            "Selecciona el nivel de apalancamiento:",
            reply_markup=get_apalancamiento_keyboard(asset_id, currency, operation_type)
        )
    elif data.startswith("lev_"):
        parts = data.split("_")
        
        if parts[1] == "custom":
            asset_id = parts[2]
            currency = parts[3]
            operation_type = parts[4]
            context.user_data['awaiting_custom_leverage'] = {
                'asset_id': asset_id,
                'currency': currency,
                'operation_type': operation_type
            }
            await query.edit_message_text("Por favor, envía el nivel de apalancamiento personalizado (ej: 25):")
        else:
            asset_id = parts[1]
            currency = parts[2]
            operation_type = parts[3]
            leverage = int(parts[4])
            
            await process_leverage_selection(query, context, asset_id, currency, operation_type, leverage)
    
    # Balance
    elif data == "balance":
        await show_balance(update, context)
    elif data == "depositar":
        await solicitar_deposito(update, context)
    elif data == "retirar":
        await solicitar_retiro(update, context)
    
    # Operaciones
    elif data == "operations":
        await show_operations(update, context)
    elif data == "history":
        await show_history(update, context)
    elif data.startswith("op_"):
        await show_operation_detail(update, context)
    elif data.startswith("history_"):
        await show_history_detail(update, context)
    elif data.startswith("close_op_"):
        await close_operation(update, context)
    elif data.startswith("check_op_"):
        await check_operation(update, context)
    
    # Admin
    elif data.startswith("apr_"):
        await approve_request(update, context)
    elif data.startswith("rej_"):
        await reject_request(update, context)
    
    # Confirmación de operación
    elif data == "confirm_trade":
        await confirm_trade(update, context)
    elif data == "cancel_trade":
        await cancel_trade(update, context)

def main():
    PORT = int(os.environ.get('PORT', 10000))
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://qvabotcrypto.onrender.com')
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Añadir handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setsaldo", set_saldo))
    application.add_handler(CommandHandler("setgroupid", set_group_id))
    application.add_handler(CommandHandler("getchatid", get_chat_id))
    
    application.add_handler(CallbackQueryHandler(button_click))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Añadir manejador de errores
    application.add_error_handler(error_handler)
    
    # Añadir job de keep-alive
    job_queue = application.job_queue
    job_queue.run_repeating(keep_alive, interval=300, first=10)
    
    # Iniciar bot
    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
