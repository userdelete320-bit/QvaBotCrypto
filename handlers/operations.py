from telegram import Update
from telegram.ext import ContextTypes
from config import ASSETS
from utils import get_current_price, calcular_pips_movidos, calcular_valor_pip
from database import obtener_operacion, actualizar_operacion, actualizar_saldo
from keyboards import get_operations_keyboard, get_history_keyboard, get_operation_detail_keyboard, get_navigation_keyboard
import logging

logger = logging.getLogger(__name__)

async def show_operations(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    await query.edit_message_text(
        "Tus operaciones activas:",
        reply_markup=get_operations_keyboard(user_id)
    )

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    await query.edit_message_text(
        "Tu historial de operaciones:",
        reply_markup=get_history_keyboard(user_id)
    )

async def show_operation_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    op_id = int(query.data.split("_")[1])
    operation = obtener_operacion(op_id)
    
    if operation:
        asset = ASSETS[operation['asset']]
        operation_type = "COMPRA" if operation['operation_type'] == 'buy' else "VENTA"
        
        message = (
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {operation_type}\n"
            f"Precio de entrada: {operation['entry_price']:.8f} {operation['currency']}\n"
            f"Apalancamiento: x{operation['apalancamiento']}\n"
            f"Stop Loss: {operation['sl_price'] if operation['sl_price'] else 'No establecido'}\n"
            f"Take Profit: {operation['tp_price'] if operation['tp_price'] else 'No establecido'}\n"
            f"Fecha: {operation['entry_time']}\n"
            f"Estado: {operation['status']}\n\n"
            "Selecciona una acción:"
        )
        
        await query.edit_message_text(message, reply_markup=get_operation_detail_keyboard(op_id))
    else:
        await query.edit_message_text("❌ Operación no encontrada.")

async def show_history_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    op_id = int(query.data.split("_")[1])
    operation = obtener_operacion(op_id)
    
    if operation:
        asset = ASSETS[operation['asset']]
        operation_type = "COMPRA" if operation['operation_type'] == 'buy' else "VENTA"
        result_emoji = "✅" if operation['result'] == "ganancia" else "❌" if operation['result'] == "perdida" else "➖"
        result_text = "Ganancia" if operation['result'] == "ganancia" else "Pérdida" if operation['result'] == "perdida" else "Sin resultado"
        
        message = (
            f"{result_emoji} {asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {operation_type}\n"
            f"Precio de entrada: {operation['entry_price']:.8f} {operation['currency']}\n"
            f"Precio de salida: {operation['exit_price'] if operation['exit_price'] else 'N/A'}\n"
            f"Apalancamiento: x{operation['apalancamiento']}\n"
            f"Resultado: {result_text}\n"
            f"Monto: {operation['result_amount'] if operation['result_amount'] else 'N/A'} CUP\n"
            f"Fecha entrada: {operation['entry_time']}\n"
            f"Fecha salida: {operation['exit_time'] if operation['exit_time'] else 'N/A'}\n"
        )
        
        await query.edit_message_text(message, reply_markup=get_operation_detail_keyboard(op_id, True))
    else:
        await query.edit_message_text("❌ Operación no encontrada.")

async def close_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    op_id = int(query.data.split("_")[2])
    operation = obtener_operacion(op_id)
    
    if operation:
        current_price = get_current_price(operation['asset'], operation['currency'])
        pips_movidos = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
        
        if operation['operation_type'] == 'buy':
            result = "ganancia" if current_price > operation['entry_price'] else "perdida"
        else:
            result = "ganancia" if current_price < operation['entry_price'] else "perdida"
        
        valor_pip = calcular_valor_pip(operation['asset'])
        resultado_monto = pips_movidos * valor_pip * operation['apalancamiento']
        if result == "perdida":
            resultado_monto = -resultado_monto
        
        update_data = {
            'status': 'cerrada',
            'exit_price': current_price,
            'exit_time': datetime.now(timezone.utc).isoformat(),
            'result': result,
            'result_amount': resultado_monto
        }
        
        if actualizar_operacion(op_id, update_data):
            nuevo_saldo = actualizar_saldo(user_id, resultado_monto)
            
            asset = ASSETS[operation['asset']]
            result_emoji = "✅" if result == "ganancia" else "❌"
            
            await query.edit_message_text(
                f"{result_emoji} Operación cerrada\n\n"
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Resultado: {result.capitalize()}\n"
                f"Monto: {resultado_monto:.2f} CUP\n"
                f"💳 Nuevo saldo: {nuevo_saldo:.2f} CUP\n\n"
                "Selecciona una opción:",
                reply_markup=get_navigation_keyboard()
            )
        else:
            await query.edit_message_text("❌ Error al cerrar la operación.")
    else:
        await query.edit_message_text("❌ Operación no encontrada.")

async def check_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    op_id = int(query.data.split("_")[2])
    operation = obtener_operacion(op_id)
    
    if operation:
        current_price = get_current_price(operation['asset'], operation['currency'])
        pips_movidos = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
        
        valor_pip = calcular_valor_pip(operation['asset'])
        resultado_actual = pips_movidos * valor_pip * operation['apalancamiento']
        
        if operation['operation_type'] == 'sell':
            resultado_actual = -resultado_actual
            
        asset = ASSETS[operation['asset']]
        operation_type = "COMPRA" if operation['operation_type'] == 'buy' else "VENTA"
        resultado_text = f"{resultado_actual:.2f} CUP" if resultado_actual >= 0 else f"{resultado_actual:.2f} CUP"
        emoji_resultado = "✅" if resultado_actual >= 0 else "❌"
        
        sl_alcanzado = False
        tp_alcanzado = False
        
        if operation['sl_price']:
            if (operation['operation_type'] == 'buy' and current_price <= operation['sl_price']) or \
               (operation['operation_type'] == 'sell' and current_price >= operation['sl_price']):
                sl_alcanzado = True
                
        if operation['tp_price']:
            if (operation['operation_type'] == 'buy' and current_price >= operation['tp_price']) or \
               (operation['operation_type'] == 'sell' and current_price <= operation['tp_price']):
                tp_alcanzado = True
        
        message = (
            f"{emoji_resultado} Estado de operación\n\n"
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {operation_type}\n"
            f"Apalancamiento: x{operation['apalancamiento']}\n"
            f"Precio entrada: {operation['entry_price']:.8f}\n"
            f"Precio actual: {current_price:.8f}\n"
            f"Pips movidos: {pips_movidos:.2f}\n"
            f"Resultado actual: {resultado_text}\n"
        )
        
        if sl_alcanzado:
            message += "\n🛑 Stop Loss alcanzado"
        elif tp_alcanzado:
            message += "\n🎯 Take Profit alcanzado"
            
        if sl_alcanzado or tp_alcanzado:
            message += "\n\nConsidera cerrar la operación."
            
        await query.edit_message_text(message, reply_markup=get_operation_detail_keyboard(op_id))
    else:
        await query.edit_message_text("❌ Operación no encontrada.")
