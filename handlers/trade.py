from telegram import Update
from telegram.ext import ContextTypes
from config import ASSETS, MIN_RIESGO, CUP_RATE, PIP_VALUES
from utils import get_current_price, calcular_max_sl, calcular_valor_pip
from keyboards import get_main_keyboard, get_currency_keyboard, get_trade_keyboard, get_apalancamiento_keyboard, get_confirmation_keyboard, get_navigation_keyboard
from database import crear_operacion, actualizar_saldo, obtener_saldo
import logging

logger = logging.getLogger(__name__)

async def process_leverage_selection(update, context, asset_id, currency, operation_type, leverage):
    asset = ASSETS[asset_id]
    price = get_current_price(asset_id, currency)
    
    operation_type_text = "COMPRA" if operation_type == "buy" else "VENTA"
    
    context.user_data['trade_data'] = {
        'asset_id': asset_id,
        'currency': currency,
        'operation_type': operation_type,
        'leverage': leverage,
        'entry_price': price
    }
    
    # Obtener saldo del usuario
    user_id = str(update.from_user.id if hasattr(update, 'from_user') else update.message.from_user.id)
    saldo_actual = obtener_saldo(user_id)
    
    message = (
        f"📊 Configuración de operación\n\n"
        f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
        f"Operación: {operation_type_text}\n"
        f"Apalancamiento: x{leverage}\n"
        f"Precio actual: {price:.8f} {currency}\n"
        f"💳 Tu saldo actual: {saldo_actual:.2f} CUP\n\n"
        f"Por favor, envía el monto que deseas arriesgar (en CUP, mínimo {MIN_RIESGO} CUP):"
    )
    
    if hasattr(update, 'edit_message_text'):
        await update.edit_message_text(message)
    else:
        await update.message.reply_text(message)
    
    context.user_data['state'] = 'esperando_monto_riesgo'

async def recibir_monto_riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        monto_riesgo = float(text)
        saldo_actual = obtener_saldo(user_id)
        
        if monto_riesgo < MIN_RIESGO:
            await update.message.reply_text(
                f"❌ El monto de riesgo mínimo es {MIN_RIESGO} CUP. Intenta nuevamente.\n"
                f"💳 Tu saldo actual: {saldo_actual:.2f} CUP"
            )
            return
            
        if monto_riesgo > saldo_actual:
            await update.message.reply_text(
                f"❌ No tienes suficiente saldo. \n"
                f"💳 Tu saldo actual: {saldo_actual:.2f} CUP\n"
                f"📋 Monto solicitado: {monto_riesgo} CUP\n\n"
                "Por favor, envía un monto menor o realiza un depósito."
            )
            return
            
        trade_data = context.user_data.get('trade_data', {})
        asset_id = trade_data.get('asset_id')
        currency = trade_data.get('currency')
        operation_type = trade_data.get('operation_type')
        leverage = trade_data.get('leverage')
        entry_price = trade_data.get('entry_price')
        
        if not all([asset_id, currency, operation_type, leverage, entry_price]):
            await update.message.reply_text("❌ Error en los datos de operación. Comienza nuevamente.")
            return
            
        max_sl_pips = calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, CUP_RATE)
        
        asset = ASSETS[asset_id]
        valor_pip = calcular_valor_pip(asset_id, CUP_RATE) * leverage
        
        await update.message.reply_text(
            f"📊 Análisis de riesgo\n\n"
            f"💰 Monto de riesgo: {monto_riesgo} CUP\n"
            f"💳 Saldo restante: {saldo_actual - monto_riesgo:.2f} CUP\n"
            f"📏 SL máximo: {max_sl_pips:.2f} pips\n"
            f"💵 Valor por pip: {valor_pip:.2f} CUP\n\n"
            f"Por favor, envía el valor para el Stop Loss (en pips):"
        )
        
        context.user_data['monto_riesgo'] = monto_riesgo
        context.user_data['state'] = 'esperando_sl'
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido para el monto de riesgo.")

async def set_sl_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        value = float(text)
        state = context.user_data.get('state')
        
        if state == 'esperando_sl':
            monto_riesgo = context.user_data.get('monto_riesgo')
            trade_data = context.user_data.get('trade_data', {})
            asset_id = trade_data.get('asset_id')
            entry_price = trade_data.get('entry_price')
            operation_type = trade_data.get('operation_type')
            leverage = trade_data.get('leverage')
            currency = trade_data.get('currency')
            
            max_sl_pips = calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, CUP_RATE)
            
            if value > max_sl_pips:
                await update.message.reply_text(
                    f"❌ El Stop Loss excede el máximo permitido de {max_sl_pips:.2f} pips. "
                    f"Envía un valor menor o igual:"
                )
                return
                
            context.user_data['sl_pips'] = value
            
            pip_value = PIP_VALUES.get(asset_id, 0.01)
            if operation_type == 'buy':
                sl_price = entry_price - (value * pip_value)
            else:
                sl_price = entry_price + (value * pip_value)
                
            context.user_data['sl_price'] = sl_price
            
            await update.message.reply_text(
                f"✅ Stop Loss establecido a {value} pips.\n"
                f"📉 Precio de Stop Loss: {sl_price:.8f} {currency}\n\n"
                "Ahora envía el valor para el Take Profit (en pips):"
            )
            context.user_data['state'] = 'esperando_tp'
            
        elif state == 'esperando_tp':
            trade_data = context.user_data.get('trade_data', {})
            asset_id = trade_data.get('asset_id')
            entry_price = trade_data.get('entry_price')
            operation_type = trade_data.get('operation_type')
            currency = trade_data.get('currency')
            
            context.user_data['tp_pips'] = value
            
            pip_value = PIP_VALUES.get(asset_id, 0.01)
            if operation_type == 'buy':
                tp_price = entry_price + (value * pip_value)
            else:
                tp_price = entry_price - (value * pip_value)
                
            context.user_data['tp_price'] = tp_price
            
            sl_price = context.user_data.get('sl_price')
            monto_riesgo = context.user_data.get('monto_riesgo')
            
            asset = ASSETS[asset_id]
            operation_type_text = "COMPRA" if operation_type == 'buy' else "VENTA"
            
            riesgo_recompensa = value / context.user_data.get('sl_pips', 1) if context.user_data.get('sl_pips', 0) > 0 else 0
            
            message = (
                f"📋 Resumen de operación\n\n"
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Operación: {operation_type_text}\n"
                f"Apalancamiento: x{trade_data['leverage']}\n"
                f"Precio entrada: {entry_price:.8f} {currency}\n"
                f"Stop Loss: {sl_price:.8f} {currency} ({context.user_data.get('sl_pips', 0):.2f} pips)\n"
                f"Take Profit: {tp_price:.8f} {currency} ({value:.2f} pips)\n"
                f"Monto riesgo: {monto_riesgo} CUP\n"
                f"Riesgo/Recompensa: 1:{riesgo_recompensa:.2f}\n\n"
                f"¿Confirmar operación?"
            )
            
            await update.message.reply_text(message, reply_markup=get_confirmation_keyboard())
            context.user_data['state'] = 'confirmando_operacion'
            
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido.")

async def confirm_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    trade_data = context.user_data.get('trade_data', {})
    monto_riesgo = context.user_data.get('monto_riesgo')
    sl_pips = context.user_data.get('sl_pips')
    tp_pips = context.user_data.get('tp_pips')
    sl_price = context.user_data.get('sl_price')
    tp_price = context.user_data.get('tp_price')
    
    if not all([trade_data, monto_riesgo, sl_pips, tp_pips, sl_price, tp_price]):
        await query.edit_message_text("❌ Error: Datos de operación incompletos. Comienza nuevamente.")
        return
        
    try:
        operation_data = {
            'user_id': user_id,
            'asset': trade_data['asset_id'],
            'currency': trade_data['currency'],
            'operation_type': trade_data['operation_type'],
            'entry_price': trade_data['entry_price'],
            'apalancamiento': trade_data['leverage'],
            'sl_price': sl_price,
            'tp_price': tp_price,
            'monto_riesgo': monto_riesgo,
            'status': 'pendiente',
            'entry_time': datetime.now(timezone.utc).isoformat()
        }
        
        op_id = crear_operacion(operation_data)
        if op_id:
            await query.edit_message_text(
                "✅ Operación confirmada y registrada.\n\n"
                "Puedes verificar el estado de tus operaciones en el menú 'Operaciones'.",
                reply_markup=get_navigation_keyboard()
            )
        else:
            await query.edit_message_text("❌ Error al registrar la operación.")
    except Exception as e:
        logger.error(f"Error insertando operación: {e}")
        await query.edit_message_text("❌ Error al registrar la operación.")
    
    # Limpiar datos de la operación
    keys_to_remove = ['trade_data', 'monto_riesgo', 'sl_pips', 'tp_pips', 'sl_price', 'tp_price', 'state']
    for key in keys_to_remove:
        context.user_data.pop(key, None)

async def cancel_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    keys_to_remove = ['trade_data', 'monto_riesgo', 'sl_pips', 'tp_pips', 'sl_price', 'tp_price', 'state']
    for key in keys_to_remove:
        context.user_data.pop(key, None)
    await query.edit_message_text("❌ Operación cancelada.", reply_markup=get_navigation_keyboard())
