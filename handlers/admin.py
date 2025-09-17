from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, GROUP_ID
from database import actualizar_solicitud, obtener_solicitud, actualizar_saldo, obtener_saldo
from keyboards import get_admin_keyboard
import logging

logger = logging.getLogger(__name__)

async def set_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Comando solo disponible para el administrador.")
        return
        
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Uso: /setsaldo <user_id> <monto>")
        return
        
    try:
        target_user_id = context.args[0]
        monto = float(context.args[1])
        
        nuevo_saldo = actualizar_saldo(target_user_id, monto)
        await update.message.reply_text(f"✅ Saldo de {target_user_id} actualizado a {nuevo_saldo:.2f} CUP")
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.")
    except Exception as e:
        logger.error(f"Error estableciendo saldo: {e}")
        await update.message.reply_text("❌ Error al establecer el saldo.")

async def set_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede usar este comando.")
        return
        
    if not context.args:
        await update.message.reply_text("Uso: /setgroupid <group_id>")
        return
        
    global GROUP_ID
    GROUP_ID = context.args[0]
    await update.message.reply_text(f"✅ ID de grupo actualizado a: {GROUP_ID}")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    await update.message.reply_text(f"El ID de este chat es: `{chat_id}`", parse_mode="Markdown")

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
