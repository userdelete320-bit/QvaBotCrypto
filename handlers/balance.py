from telegram import Update
from telegram.ext import ContextTypes
from config import MIN_DEPOSITO, MIN_RETIRO, CARD_NUMBER, CONFIRMATION_NUMBER
from database import obtener_saldo, crear_solicitud, actualizar_saldo
from keyboards import get_navigation_keyboard, get_balance_keyboard
import logging

logger = logging.getLogger(__name__)

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    saldo = obtener_saldo(user_id)
    await query.edit_message_text(
        f"💳 Tu saldo actual: {saldo:.2f} CUP\n\n"
        "Selecciona una opción:",
        reply_markup=get_balance_keyboard()
    )

async def solicitar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    saldo = obtener_saldo(user_id)
    context.user_data['state'] = 'solicitud_deposito'
    await query.edit_message_text(
        f"💳 Tu saldo actual: {saldo:.2f} CUP\n\n"
        f"Para depositar, envía el monto en CUP (mínimo {MIN_DEPOSITO} CUP).\n\n"
        f"📋 Datos para transferencia:\n"
        f"💳 Número de tarjeta: {CARD_NUMBER}\n"
        f"📞 Número de confirmación: {CONFIRMATION_NUMBER}\n\n"
        "Después de realizar la transferencia, envía una foto del comprobante."
    )

async def solicitar_retiro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    saldo = obtener_saldo(user_id)
    if saldo < MIN_RETIRO:
        await query.edit_message_text(
            f"❌ Saldo insuficiente para retirar. \n"
            f"💳 Tu saldo actual: {saldo:.2f} CUP\n"
            f"📋 Mínimo para retiro: {MIN_RETIRO} CUP\n\n"
            "Puedes realizar un depósito para aumentar tu saldo.",
            reply_markup=get_navigation_keyboard()
        )
        return
        
    context.user_data['state'] = 'solicitud_retiro'
    await query.edit_message_text(
        f"💳 Tu saldo actual: {saldo:.2f} CUP\n\n"
        f"Para retirar, envía el monto en CUP (mínimo {MIN_RETIRO} CUP).\n\n"
        "Luego necesitaremos tus datos de contacto y tarjeta para realizar la transferencia."
    )

async def recibir_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        monto = float(text)
        state = context.user_data.get('state')
        
        if state == 'solicitud_deposito':
            if monto < MIN_DEPOSITO:
                await update.message.reply_text(f"❌ El monto mínimo para depósito es {MIN_DEPOSITO} CUP. Intenta nuevamente.")
                return
                
            context.user_data['solicitud'] = {
                'tipo': 'deposito',
                'monto': monto
            }
            
            await update.message.reply_text(
                f"✅ Monto de depósito aceptado: {monto} CUP\n\n"
                "Por favor, envía una foto del comprobante de transferencia."
            )
            context.user_data['state'] = 'esperando_comprobante'
            
        elif state == 'solicitud_retiro':
            saldo = obtener_saldo(user_id)
            if monto < MIN_RETIRO:
                await update.message.reply_text(f"❌ El monto mínimo para retiro es {MIN_RETIRO} CUP. Intenta nuevamente.")
                return
                
            if monto > saldo:
                await update.message.reply_text(f"❌ Saldo insuficiente. Tu saldo actual es {saldo:.2f} CUP. Intenta con un monto menor.")
                return
                
            context.user_data['solicitud'] = {
                'tipo': 'retiro',
                'monto': monto
            }
            
            await update.message.reply_text(
                f"✅ Monto de retiro aceptado: {monto} CUP\n\n"
                "Por favor, envía tu número de tarjeta y teléfono de contacto (en un solo mensaje):"
            )
            context.user_data['state'] = 'solicitud_retiro_datos'
            
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido para el monto.")

async def recibir_datos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    user = update.message.from_user
    username = f"@{user.username}" if user.username else "Sin username"
    solicitud = context.user_data.get('solicitud', {})
    tipo = solicitud.get('tipo')
    monto = solicitud.get('monto')
    
    if tipo == 'deposito':
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            file = await context.bot.get_file(file_id)
            file_path = file.file_path
            
            datos = f"Comprobante: {file_path}"
            solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
            
            if solicitud_id:
                admin_message = (f"📥 Nueva solicitud de DEPÓSITO\n"
                               f"👤 Usuario: {username} (ID: {user_id})\n"
                               f"💵 Monto: {monto} CUP\n"
                               f"📋 Datos: {datos}")
                
                # Aquí se enviaría el mensaje al admin (implementar después)
                
                await update.message.reply_text(
                    "✅ Comprobante recibido. Espera la confirmación del administrador.",
                    reply_markup=get_navigation_keyboard()
                )
            else:
                await update.message.reply_text("❌ Error creando la solicitud. Intenta nuevamente.")
            
            context.user_data.clear()
        else:
            await update.message.reply_text("❌ Por favor, envía una foto del comprobante.")
    
    else:
        datos = update.message.text.strip()
        
        solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
        
        if solicitud_id:
            admin_message = (f"📤 Nueva solicitud de RETIRO\n"
                           f"👤 Usuario: {username} (ID: {user_id})\n"
                           f"💳 Monto: {monto} CUP\n"
                           f"📋 Datos: {datos}")
            
            # Aquí se enviaría el mensaje al admin (implementar después)
            
            await update.message.reply_text(
                "✅ Solicitud de retiro enviada. Espera la confirmación del administrador.",
                reply_markup=get_navigation_keyboard()
            )
        else:
            await update.message.reply_text("❌ Error creando la solicitud. Intenta nuevamente.")
        
        context.user_data.clear()
