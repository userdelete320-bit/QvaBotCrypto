# handlers/admin.py
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, GROUP_ID
from database import actualizar_solicitud, obtener_solicitud, actualizar_saldo, obtener_saldo
from keyboards import get_admin_keyboard, get_navigation_keyboard
import logging

logger = logging.getLogger(__name__)

async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Solo el administrador puede realizar esta acción.")
        return
        
    parts = query.data.split("_")
    tipo = parts[1]
    solicitud_id = int(parts[2])
    
    try:
        solicitud = obtener_solicitud(solicitud_id)
        if not solicitud:
            await query.answer("❌ Solicitud no encontrada.")
            return
            
        user_id_solicitud = solicitud['user_id']
        monto = solicitud['monto']
        
        if tipo == 'deposito':
            nuevo_saldo = actualizar_saldo(user_id_solicitud, monto)
            actualizar_solicitud(solicitud_id, 'aprobada')
            
            try:
                await context.bot.send_message(
                    chat_id=user_id_solicitud,
                    text=f"✅ Tu depósito de {monto} CUP ha sido aprobado.\n\n💳 Tu nuevo saldo: {nuevo_saldo:.2f} CUP",
                    reply_markup=get_navigation_keyboard()
                )
                # Enviar también al grupo
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=f"✅ Depósito aprobado\nUsuario: {user_id_solicitud}\nMonto: {monto} CUP"
                )
            except Exception as e:
                logger.error(f"Error notificando al usuario: {e}")
            
            await query.edit_message_text(f"✅ Depósito aprobado. Nuevo saldo: {nuevo_saldo:.2f} CUP")
            
        else:
            saldo_actual = obtener_saldo(user_id_solicitud)
            if saldo_actual < monto:
                actualizar_solicitud(solicitud_id, 'rechazada', 'Saldo insuficiente')
                await query.edit_message_text("❌ Saldo insuficiente para aprobar el retiro.")
                return
                
            nuevo_saldo = actualizar_saldo(user_id_solicitud, -monto)
            actualizar_solicitud(solicitud_id, 'aprobada')
            
            try:
                await context.bot.send_message(
                    chat_id=user_id_solicitud,
                    text=f"✅ Tu retiro de {monto} CUP ha sido aprobado.\n\n💳 Tu nuevo saldo: {nuevo_saldo:.2f} CUP",
                    reply_markup=get_navigation_keyboard()
                )
                # Enviar también al grupo
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=f"✅ Retiro aprobado\nUsuario: {user_id_solicitud}\nMonto: {monto} CUP"
                )
            except Exception as e:
                logger.error(f"Error notificando al usuario: {e}")
            
            await query.edit_message_text(f"✅ Retiro aprobado. Nuevo saldo: {nuevo_saldo:.2f} CUP")
            
    except Exception as e:
        logger.error(f"Error aprobando solicitud: {e}")
        await query.answer("❌ Error al procesar la solicitud.")

async def reject_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Solo el administrador puede realizar esta acción.")
        return
        
    parts = query.data.split("_")
    tipo = parts[1]
    solicitud_id = int(parts[2])
    
    context.user_data['rechazando_solicitud'] = {
        'solicitud_id': solicitud_id,
        'tipo': tipo
    }
    await query.edit_message_text("Por favor, envía el motivo del rechazo:")

async def receive_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    motivo = update.message.text.strip()
    
    solicitud_data = context.user_data.get('rechazando_solicitud')
    if solicitud_data:
        solicitud_id = solicitud_data['solicitud_id']
        tipo = solicitud_data['tipo']
        
        if actualizar_solicitud(solicitud_id, 'rechazada', motivo):
            try:
                solicitud = obtener_solicitud(solicitud_id)
                if solicitud:
                    user_id_solicitud = solicitud['user_id']
                    monto = solicitud['monto']
                    
                    try:
                        await context.bot.send_message(
                            chat_id=user_id_solicitud,
                            text=f"❌ Tu solicitud de {tipo} de {monto} CUP ha sido rechazada.\n\nMotivo: {motivo}",
                            reply_markup=get_navigation_keyboard()
                        )
                        # Enviar también al grupo
                        await context.bot.send_message(
                            chat_id=GROUP_ID,
                            text=f"❌ Solicitud de {tipo} rechazada\nUsuario: {user_id_solicitud}\nMonto: {monto} CUP\nMotivo: {motivo}"
                        )
                    except Exception as e:
                        logger.error(f"Error notificando al usuario: {e}")
            except Exception as e:
                logger.error(f"Error obteniendo información de solicitud: {e}")
            
            await update.message.reply_text("✅ Solicitud rechazada y usuario notificado.")
        else:
            await update.message.reply_text("❌ Error al actualizar la solicitud.")
        
        del context.user_data['rechazando_solicitud']
    else:
        await update.message.reply_text("❌ No se encontró solicitud para rechazar.")

# Los otros handlers de admin (set_saldo, set_group_id, get_chat_id) permanecen igual
