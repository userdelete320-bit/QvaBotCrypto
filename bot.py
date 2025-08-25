import os
import logging
import requests
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, 
    MessageHandler, filters, JobQueue, CallbackContext
)
from supabase import create_client, Client

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = "5376388604"
COINCAP_API_KEY = "c0b9354ec2c2d06d6395519f432b056c06f6340b62b72de1cf71a44ed9c6a36e"
COINCAP_API_URL = "https://rest.coincap.io/v3"
MAX_DAILY_CHECKS = 80
MIN_DEPOSITO = 5000  # Cambiado a 5000 CUP
MIN_RIESGO = 5000
MIN_RETIRO = 6500
CUP_RATE = 440
CONFIRMATION_NUMBER = "59190241"
CARD_NUMBER = "9227 0699 9532 8054"
GROUP_ID = os.getenv("GROUP_ID", "-1002479699968")

# Mapeo de activos
ASSETS = {
    "bitcoin": {"symbol": "BTC", "name": "Bitcoin", "coincap_id": "bitcoin", "emoji": "🪙"},
    "ethereum": {"symbol": "ETH", "name": "Ethereum", "coincap_id": "ethereum", "emoji": "🔷"},
    "binance-coin": {"symbol": "BNB", "name": "Binance Coin", "coincap_id": "binance-coin", "emoji": "🅱️"},
    "tether": {"symbol": "USDT", "name": "Tether", "coincap_id": "tether", "emoji": "💵"},
    "dai": {"symbol": "DAI", "name": "Dai", "coincap_id": "dai", "emoji": "🌀"},
    "usd-coin": {"symbol": "USDC", "name": "USD Coin", "coincap_id": "usd-coin", "emoji": "💲"},
    "ripple": {"symbol": "XRP", "name": "XRP", "coincap_id": "ripple", "emoji": "✖️"},
    "cardano": {"symbol": "ADA", "name": "Cardano", "coincap_id": "cardano", "emoji": "🅰️"},
    "solana": {"symbol": "SOL", "name": "Solana", "coincap_id": "solana", "emoji": "☀️"},
    "dogecoin": {"symbol": "DOGE", "name": "Dogecoin", "coincap_id": "dogecoin", "emoji": "🐶"},
    "polkadot": {"symbol": "DOT", "name": "Polkadot", "coincap_id": "polkadot", "emoji": "🔴"},
    "litecoin": {"symbol": "LTC", "name": "Litecoin", "coincap_id": "litecoin", "emoji": "🔶"},
    "chainlink": {"symbol": "LINK", "name": "Chainlink", "coincap_id": "chainlink", "emoji": "🔗"},
    "bitcoin-cash": {"symbol": "BCH", "name": "Bitcoin Cash", "coincap_id": "bitcoin-cash", "emoji": "💰"}
}

# Valores de pip para cada activo
PIP_VALUES = {
    "bitcoin": 0.01,
    "ethereum": 0.01,
    "binance-coin": 0.01,
    "tether": 0.0001,
    "dai": 0.0001,
    "usd-coin": 0.0001,
    "ripple": 0.0001,
    "cardano": 0.0001,
    "solana": 0.01,
    "dogecoin": 0.000001,
    "polkadot": 0.01,
    "litecoin": 0.01,
    "chainlink": 0.001,
    "bitcoin-cash": 0.01
}

# Configurar Supabase
SUPABASE_URL = "https://xowsmpukhedukeoqcreb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhbmFzZSIsInJlZiI6Inhvd3NtcHVraGVkdWtlb3FjcmViIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ4MzkwNDEsImV4cCI6MjA3MDQxNTA0MX0.zy1rCXPfuNQ95Bk0ATTkdF6DGLB9DhG9EjaBr0v3c0M"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Niveles de apalancamiento
APALANCAMIENTOS = [5, 10, 20, 50, 100]

# Funciones de cálculo de pips
def calcular_valor_pip(asset_id, cup_rate):
    pip_value_usd = PIP_VALUES.get(asset_id, 0.01)
    return pip_value_usd * cup_rate

def calcular_ganancia_pips(pips, asset_id, cup_rate, apalancamiento=1):
    valor_pip = calcular_valor_pip(asset_id, cup_rate)
    return pips * valor_pip * apalancamiento

def calcular_pips_movidos(precio_inicial, precio_final, asset_id):
    pip_value = PIP_VALUES.get(asset_id, 0.01)
    return abs(precio_final - precio_inicial) / pip_value

def calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, cup_rate):
    valor_pip = calcular_valor_pip(asset_id, cup_rate) * leverage
    max_pips = monto_riesgo / valor_pip
    return max_pips

# Gestión de saldo
def obtener_saldo(user_id: str) -> float:
    try:
        response = supabase.table('balance').select('saldo').eq('user_id', user_id).execute()
        return response.data[0]['saldo'] if response.data else 0.0
    except Exception as e:
        logger.error(f"Error obteniendo saldo: {e}")
        return 0.0

def actualizar_saldo(user_id: str, monto: float) -> float:
    try:
        saldo_actual = obtener_saldo(user_id)
        nuevo_saldo = saldo_actual + monto
        supabase.table('balance').upsert({'user_id': user_id, 'saldo': nuevo_saldo}).execute()
        return nuevo_saldo
    except Exception as e:
        logger.error(f"Error actualizando saldo: {e}")
        return saldo_actual

# Solicitudes
def crear_solicitud(user_id: str, tipo: str, monto: float, datos: str = None) -> int:
    try:
        solicitud_data = {
            'user_id': user_id,
            'tipo': tipo,
            'monto': monto,
            'estado': 'pendiente',
            'fecha_solicitud': datetime.now(timezone.utc).isoformat()
        }
        if datos:
            solicitud_data['datos'] = datos
            
        response = supabase.table('solicitudes').insert(solicitud_data).execute()
        return response.data[0]['id'] if response.data else None
    except Exception as e:
        logger.error(f"Error creando solicitud: {e}")
        return None

def actualizar_solicitud(solicitud_id: int, estado: str, motivo: str = None) -> bool:
    try:
        update_data = {
            'estado': estado,
            'fecha_resolucion': datetime.now(timezone.utc).isoformat()
        }
        if motivo:
            update_data['motivo_rechazo'] = motivo
            
        supabase.table('solicitudes').update(update_data).eq('id', solicitud_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error actualizando solicitud: {e}")
        return False

# Gestión de créditos
def check_credits(user_id: str) -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        response = supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today).execute()
        if response.data:
            count = response.data[0]["count"]
            return count < MAX_DAILY_CHECKS
        return True
    except Exception as e:
        logger.error(f"Error checking credits: {e}")
        return True

def log_credit_usage(user_id: str) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        response = supabase.table("credit_usage").select("*").eq("user_id", user_id).eq("date", today).execute()
        if response.data:
            record = response.data[0]
            new_count = record["count"] + 1
            supabase.table("credit_usage").update({"count": new_count}).eq("id", record["id"]).execute()
        else:
            supabase.table("credit_usage").insert({
                "user_id": user_id,
                "date": today,
                "count": 1
            }).execute()
    except Exception as e:
        logger.error(f"Error logging credit usage: {e}")

def get_credit_info(user_id: str) -> tuple:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        response = supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today).execute()
        if response.data:
            count = response.data[0]["count"]
            return count, MAX_DAILY_CHECKS - count
        return 0, MAX_DAILY_CHECKS
    except Exception as e:
        logger.error(f"Error getting credit info: {e}")
        return 0, MAX_DAILY_CHECKS

# Funciones de precios
def get_current_price(asset_id: str, currency: str = "USD") -> float:
    try:
        coincap_id = ASSETS[asset_id]["coincap_id"]
        headers = {
            "Authorization": f"Bearer {COINCAP_API_KEY}",
            "Accept-Encoding": "gzip"
        }
        url = f"{COINCAP_API_URL}/assets/{coincap_id}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return float(data['data']['priceUsd'])
    except Exception as e:
        logger.error(f"Error obteniendo precio de {asset_id}: {e}")
        return 0.0

def get_historical_prices(asset_id: str, start_time: datetime, end_time: datetime, interval: str = "m1") -> list:
    try:
        coincap_id = ASSETS[asset_id]["coincap_id"]
        headers = {
            "Authorization": f"Bearer {COINCAP_API_KEY},
            "Accept-Encoding": "gzip"
        }
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        url = f"{COINCAP_API_URL}/assets/{coincap_id}/history"
        params = {
            "interval": interval,
            "start": start_ms,
            "end": end_ms
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return [{"time": item["time"], "price": float(item["priceUsd"])} for item in data['data']]
    except Exception as e:
        logger.error(f"Error obteniendo precios históricos de {asset_id}: {e}")
        return []

def analyze_price_history(price_history, entry_price, sl_price, tp_price, operation_type):
    if not price_history:
        return None, None
        
    hit_sl = False
    hit_tp = False
    sl_time = None
    tp_time = None
    
    for price_point in price_history:
        price = price_point['price']
        
        if operation_type == 'buy':
            if price <= sl_price and not hit_sl:
                hit_sl = True
                sl_time = price_point['time']
            if price >= tp_price and not hit_tp:
                hit_tp = True
                tp_time = price_point['time']
        else:  # sell
            if price >= sl_price and not hit_sl:
                hit_sl = True
                sl_time = price_point['time']
            if price <= tp_price and not hit_tp:
                hit_tp = True
                tp_time = price_point['time']
                
        if hit_sl and hit_tp:
            break
            
    return sl_time, tp_time

# Teclados
def get_admin_keyboard(solicitud_id: int, tipo: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aprobar", callback_data=f"apr_{tipo}_{solicitud_id}"),
        InlineKeyboardButton("❌ Rechazar", callback_data=f"rej_{tipo}_{solicitud_id}")
    ]])

def get_balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬆️ Depositar", callback_data="depositar"),
        InlineKeyboardButton("⬇️ Retirar", callback_data="retirar")
    ], [InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")]])

def get_main_keyboard():
    buttons = []
    row = []
    for i, asset_id in enumerate(ASSETS.keys()):
        asset = ASSETS[asset_id]
        row.append(InlineKeyboardButton(f"{asset['emoji']} {asset['symbol']}", callback_data=f"asset_{asset_id}"))
        if (i + 1) % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("💰 Balance", callback_data="balance")])
    buttons.append([InlineKeyboardButton("📊 Operaciones", callback_data="operations")])
    buttons.append([InlineKeyboardButton("📋 Historial", callback_data="history")])
    
    return InlineKeyboardMarkup(buttons)

def get_currency_keyboard(asset_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 USD", callback_data=f"currency_{asset_id}_USD"),
    ], [InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")]])

def get_trade_keyboard(asset_id, currency):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 COMPRAR", callback_data=f"trade_{asset_id}_{currency}_buy"),
        InlineKeyboardButton("🔴 VENDER", callback_data=f"trade_{asset_id}_{currency}_sell")
    ], [InlineKeyboardButton("🔙 Atrás", callback_data=f"back_asset_{asset_id}")]])

def get_apalancamiento_keyboard(asset_id, currency, operation_type):
    buttons = []
    row = []
    for leverage in APALANCAMIENTOS:
        row.append(InlineKeyboardButton(f"x{leverage}", callback_data=f"lev_{asset_id}_{currency}_{operation_type}_{leverage}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ Personalizado", callback_data=f"lev_custom_{asset_id}_{currency}_{operation_type}")])
    buttons.append([InlineKeyboardButton("🔙 Atrás", callback_data=f"back_trade_{asset_id}_{currency}")])
    return InlineKeyboardMarkup(buttons)

def get_operations_keyboard(user_id):
    try:
        response = supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price, apalancamiento"
        ).eq("user_id", user_id).eq("status", "pendiente").execute()
        operations = response.data
    except Exception as e:
        logger.error(f"Error fetching operations: {e}")
        operations = []
    
    buttons = []
    for op in operations:
        asset = ASSETS[op['asset']]
        buttons.append([InlineKeyboardButton(
            f"{asset['emoji']} {asset['symbol']} {op['operation_type'].upper()} x{op['apalancamiento']}",
            callback_data=f"op_{op['id']}"
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def get_history_keyboard(user_id):
    try:
        response = supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price, result, apalancamiento"
        ).eq("user_id", user_id).eq("status", "cerrada").order("entry_time", desc=True).limit(10).execute()
        operations = response.data
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        operations = []
    
    buttons = []
    for op in operations:
        asset = ASSETS[op['asset']]
        result_emoji = "✅" if op['result'] == "ganada" else "❌" if op['result'] == "perdida" else "➖"
        buttons.append([InlineKeyboardButton(
            f"{result_emoji} {asset['emoji']} {asset['symbol']} {op['operation_type'].upper()}",
            callback_data=f"hist_{op['id']}"
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def get_operation_detail_keyboard(op_id, is_history=False):
    if is_history:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 A Historial", callback_data="history")]])
    else:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Cerrar Operación", callback_data=f"close_op_{op_id}"),
            InlineKeyboardButton("📈 Comprobar", callback_data=f"check_op_{op_id}")
        ], [
            InlineKeyboardButton("🛑 Modificar SL", callback_data=f"mod_sl_{op_id}"),
            InlineKeyboardButton("🎯 Modificar TP", callback_data=f"mod_tp_{op_id}")
        ], [InlineKeyboardButton("🔙 A Operaciones", callback_data="operations")]])

# Teclado de bienvenida
def get_welcome_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Empezar a Operar", callback_data="start_trading")]])

def get_navigation_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Menú Principal", callback_data="back_main")
    ], [InlineKeyboardButton("💳 Ver Balance", callback_data="balance")]])

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
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

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    data = query.data
    
    if data == "start_trading":
        await query.edit_message_text("🏠 Menú Principal", reply_markup=get_main_keyboard())
    
    elif data == "back_main":
        await query.edit_message_text("🏠 Menú Principal", reply_markup=get_main_keyboard())
    
    elif data == "balance":
        saldo = obtener_saldo(user_id)
        await query.edit_message_text(
            f"💰 Tu saldo actual es: {saldo:.2f} CUP\n\n"
            "Selecciona una opción:",
            reply_markup=get_balance_keyboard()
        )
    
    elif data == "depositar":
        context.user_data['solicitud'] = {'tipo': 'deposito'}
        await query.edit_message_text(
            f"💵 Depósito Mínimo: {MIN_DEPOSITO} CUP\n\n"
            "Por favor, ingresa el monto que deseas depositar:"
        )
        context.user_data['esperando_monto'] = True
    
    elif data == "retirar":
        saldo = obtener_saldo(user_id)
        if saldo < MIN_RETIRO:
            await query.edit_message_text(
                f"❌ Saldo insuficiente para retirar. Mínimo: {MIN_RETIRO} CUP\n"
                f"Tu saldo actual: {saldo:.2f} CUP",
                reply_markup=get_navigation_keyboard()
            )
            return
            
        context.user_data['solicitud'] = {'tipo': 'retiro'}
        await query.edit_message_text(
            f"💵 Retiro Mínimo: {MIN_RETIRO} CUP\n"
            f"💰 Tu saldo actual: {saldo:.2f} CUP\n\n"
            "Por favor, ingresa el monto que deseas retirar:"
        )
        context.user_data['esperando_monto'] = True
    
    elif data == "operations":
        await query.edit_message_text(
            "📊 Tus operaciones activas:\n\n"
            "Selecciona una operación para ver detalles:",
            reply_markup=get_operations_keyboard(user_id)
        )
    
    elif data == "history":
        await query.edit_message_text(
            "📋 Historial de operaciones:\n\n"
            "Selecciona una operación para ver detalles:",
            reply_markup=get_history_keyboard(user_id)
        )
    
    elif data.startswith("asset_"):
        asset_id = data.split("_")[1]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n\n"
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
            f"Precio actual: {price:.6f} {currency}\n\n"
            "Selecciona el tipo de operación:",
            reply_markup=get_trade_keyboard(asset_id, currency)
        )
    
    elif data.startswith("trade_"):
        parts = data.split("_")
        asset_id = parts[1]
        currency = parts[2]
        operation_type = parts[3]
        asset = ASSETS[asset_id]
        
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n\n"
            "Selecciona el nivel de apalancamiento:",
            reply_markup=get_apalancamiento_keyboard(asset_id, currency, operation_type)
        )
    
    elif data.startswith("lev_"):
        parts = data.split("_")
        if parts[1] == "custom":
            asset_id = parts[2]
            currency = parts[3]
            operation_type = parts[4]
            await query.edit_message_text(
                "Por favor, ingresa el apalancamiento personalizado:"
            )
            context.user_data['esperando_apalancamiento'] = {
                'asset_id': asset_id,
                'currency': currency,
                'operation_type': operation_type
            }
        else:
            asset_id = parts[1]
            currency = parts[2]
            operation_type = parts[3]
            leverage = int(parts[4])
            await process_leverage_selection(query, context, asset_id, currency, operation_type, leverage)
    
    elif data.startswith("op_") or data.startswith("hist_"):
        is_history = data.startswith("hist_")
        op_id = int(data.split("_")[1])
        
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0] if response.data else None
            
            if not operation:
                await query.edit_message_text("❌ Operación no encontrada.", reply_markup=get_main_keyboard())
                return
                
            asset = ASSETS[operation['asset']]
            current_price = get_current_price(operation['asset'], operation['currency'])
            pips_movidos = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
            
            message = (
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Tipo: {'COMPRA' if operation['operation_type'] == 'buy' else 'VENTA'}\n"
                f"Apalancamiento: x{operation['apalancamiento']}\n"
                f"Precio entrada: {operation['entry_price']:.6f}\n"
                f"Precio actual: {current_price:.6f}\n"
                f"Pips movidos: {pips_movidos:.2f}\n"
            )
            
            if operation['stop_loss']:
                message += f"Stop Loss: {operation['stop_loss']:.6f}\n"
            if operation['take_profit']:
                message += f"Take Profit: {operation['take_profit']:.6f}\n"
                
            if is_history:
                message += f"Resultado: {operation['result']}\n"
                if operation['close_price']:
                    message += f"Precio cierre: {operation['close_price']:.6f}\n"
                if operation['profit_loss']:
                    message += f"Ganancia/Pérdida: {operation['profit_loss']:.2f} CUP\n"
            
            await query.edit_message_text(
                message,
                reply_markup=get_operation_detail_keyboard(op_id, is_history)
            )
        except Exception as e:
            logger.error(f"Error obteniendo detalles de operación: {e}")
            await query.edit_message_text(
                "❌ Error al obtener detalles de la operación.",
                reply_markup=get_main_keyboard()
            )
    
    elif data.startswith("close_op_"):
        op_id = int(data.split("_")[2])
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0] if response.data else None
            
            if not operation:
                await query.answer("❌ Operación no encontrada.")
                return
                
            current_price = get_current_price(operation['asset'], operation['currency'])
            pips = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
            
            # Determinar si fue ganancia o pérdida
            if (operation['operation_type'] == 'buy' and current_price > operation['entry_price']) or \
               (operation['operation_type'] == 'sell' and current_price < operation['entry_price']):
                result = "ganada"
            else:
                result = "perdida"
                
            # Calcular ganancia/pérdida
            profit_loss = calcular_ganancia_pips(
                pips, operation['asset'], CUP_RATE, operation['apalancamiento']
            )
            
            if operation['operation_type'] == 'sell':
                profit_loss = -profit_loss
                
            # Actualizar operación
            supabase.table('operations').update({
                'status': 'cerrada',
                'close_price': current_price,
                'close_time': datetime.now(timezone.utc).isoformat(),
                'result': result,
                'profit_loss': profit_loss
            }).eq('id', op_id).execute()
            
            # Actualizar saldo
            nuevo_saldo = actualizar_saldo(operation['user_id'], profit_loss)
            
            await query.edit_message_text(
                f"✅ Operación cerrada\n"
                f"Resultado: {result}\n"
                f"Ganancia/Pérdida: {profit_loss:.2f} CUP\n"
                f"Nuevo saldo: {nuevo_saldo:.2f} CUP",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Error cerrando operación: {e}")
            await query.answer("❌ Error al cerrar la operación.")
    
    elif data.startswith("check_op_"):
        op_id = int(data.split("_")[2])
        await check_operation(update, context, op_id)
    
    elif data.startswith("mod_sl_") or data.startswith("mod_tp_"):
        op_id = int(data.split("_")[2])
        is_sl = data.startswith("mod_sl_")
        
        context.user_data['modificando'] = {
            'op_id': op_id,
            'tipo': 'sl' if is_sl else 'tp'
        }
        
        await query.edit_message_text(
            f"Por favor, ingresa el nuevo valor para {'Stop Loss' if is_sl else 'Take Profit'}:"
        )
    
    elif data.startswith("apr_") or data.startswith("rej_"):
        # Handler para administradores
        if user_id != ADMIN_ID:
            await query.answer("❌ No tienes permisos para realizar esta acción.")
            return
            
        parts = data.split("_")
        action = parts[0]
        tipo = parts[1]
        solicitud_id = int(parts[2])
        
        if action == "apr":
            # Aprobar solicitud
            try:
                response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
                solicitud = response.data[0] if response.data else None
                
                if not solicitud:
                    await query.answer("❌ Solicitud no encontrada.")
                    return
                
                if tipo == "deposito":
                    # Aprobar depósito - acreditar saldo
                    nuevo_saldo = actualizar_saldo(solicitud['user_id'], solicitud['monto'])
                    actualizar_solicitud(solicitud_id, "aprobada")
                    
                    # Notificar al usuario
                    try:
                        await context.bot.send_message(
                            chat_id=solicitud['user_id'],
                            text=f"✅ Tu depósito de {solicitud['monto']} CUP ha sido aprobado.\n"
                                 f"💰 Nuevo saldo: {nuevo_saldo:.2f} CUP",
                            reply_markup=get_navigation_keyboard()
                        )
                    except Exception as e:
                        logger.error(f"Error notificando usuario: {e}")
                    
                    await query.edit_message_text(
                        f"✅ Depósito aprobado.\n"
                        f"👤 User ID: {solicitud['user_id']}\n"
                        f"💵 Monto: {solicitud['monto']} CUP\n"
                        f"💰 Nuevo saldo: {nuevo_saldo:.2f} CUP"
                    )
                    
                else:  # retiro
                    # Aprobar retiro - debitar saldo
                    saldo_actual = obtener_saldo(solicitud['user_id'])
                    
                    if saldo_actual < solicitud['monto']:
                        await query.answer("❌ Saldo insuficiente para aprobar el retiro.")
                        return
                        
                    nuevo_saldo = actualizar_saldo(solicitud['user_id'], -solicitud['monto'])
                    actualizar_solicitud(solicitud_id, "aprobada")
                    
                    # Notificar al usuario
                    try:
                        await context.bot.send_message(
                            chat_id=solicitud['user_id'],
                            text=f"✅ Tu retiro de {solicitud['monto']} CUP ha sido aprobado.\n"
                                 f"💰 Nuevo saldo: {nuevo_saldo:.2f} CUP",
                            reply_markup=get_navigation_keyboard()
                        )
                    except Exception as e:
                        logger.error(f"Error notificando usuario: {e}")
                    
                    await query.edit_message_text(
                        f"✅ Retiro aprobado.\n"
                        f"👤 User ID: {solicitud['user_id']}\n"
                        f"💵 Monto: {solicitud['monto']} CUP\n"
                        f"💰 Nuevo saldo: {nuevo_saldo:.2f} CUP"
                    )
                    
            except Exception as e:
                logger.error(f"Error aprobando solicitud: {e}")
                await query.answer("❌ Error al aprobar la solicitud.")
                
        else:  # rej
            context.user_data['rechazando'] = {
                'solicitud_id': solicitud_id,
                'tipo': tipo
            }
            await query.edit_message_text("Por favor, ingresa el motivo del rechazo:")

# Handler para recibir apalancamiento personalizado
async def recibir_apalancamiento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        leverage = float(text)
        if leverage <= 0:
            await update.message.reply_text("❌ El apalancamiento debe ser mayor a 0.")
            return
            
        leverage_data = context.user_data.get('esperando_apalancamiento')
        if not leverage_data:
            await update.message.reply_text("❌ No se encontraron datos de apalancamiento.")
            return
            
        asset_id = leverage_data['asset_id']
        currency = leverage_data['currency']
        operation_type = leverage_data['operation_type']
        
        # Simular query para process_leverage_selection
        class MockQuery:
            def __init__(self, message):
                self.message = message
                
            async def edit_message_text(self, text, reply_markup=None):
                await self.message.reply_text(text, reply_markup=reply_markup)
                
        mock_query = MockQuery(update.message)
        await process_leverage_selection(mock_query, context, asset_id, currency, operation_type, leverage)
        
        # Limpiar estado
        context.user_data.pop('esperando_apalancamiento', None)
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, ingresa un número válido.")

# Handler para recibir monto de riesgo
async def recibir_monto_riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        monto_riesgo = float(text)
        if monto_riesgo < MIN_RIESGO:
            await update.message.reply_text(f"❌ El monto de riesgo mínimo es {MIN_RIESGO} CUP.")
            return
            
        saldo = obtener_saldo(user_id)
        if monto_riesgo > saldo:
            await update.message.reply_text(f"❌ No tienes suficiente saldo. Tu saldo actual es: {saldo:.2f} CUP")
            return
            
        operacion_data = context.user_data.get('operacion')
        if not operacion_data:
            await update.message.reply_text("❌ No se encontraron datos de operación.")
            return
            
        asset_id = operacion_data['asset_id']
        currency = operacion_data['currency']
        operation_type = operacion_data['operation_type']
        leverage = operacion_data['leverage']
        entry_price = operacion_data['entry_price']
        
        # Calcular SL máximo
        max_sl_pips = calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, CUP_RATE)
        
        context.user_data['operacion']['monto_riesgo'] = monto_riesgo
        
        await update.message.reply_text(
            f"💰 Monto de riesgo: {monto_riesgo} CUP\n"
            f"📉 Stop Loss máximo permitido: {max_sl_pips:.2f} pips\n\n"
            "Por favor, ingresa el Stop Loss en pips:"
        )
        context.user_data['esperando_sl'] = True
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, ingresa un número válido.")

# Handler para recibir SL/TP
async def set_sl_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        value = float(text)
        modificando = context.user_data.get('modificando')
        
        if modificando:
            op_id = modificando['op_id']
            tipo = modificando['tipo']
            
            # Obtener operación
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0] if response.data else None
            
            if not operation:
                await update.message.reply_text("❌ Operación no encontrada.")
                context.user_data.pop('modificando', None)
                return
                
            # Validar valor según tipo de operación
            current_price = get_current_price(operation['asset'], operation['currency'])
            
            if tipo == 'sl':
                if (operation['operation_type'] == 'buy' and value >= current_price) or \
                   (operation['operation_type'] == 'sell' and value <= current_price):
                    await update.message.reply_text(
                        f"❌ El Stop Loss debe estar {'por debajo' if operation['operation_type'] == 'buy' else 'por encima'} "
                        f"del precio actual ({current_price:.6f})"
                    )
                    return
            else:  # tp
                if (operation['operation_type'] == 'buy' and value <= current_price) or \
                   (operation['operation_type'] == 'sell' and value >= current_price):
                    await update.message.reply_text(
                        f"❌ El Take Profit debe estar {'por encima' if operation['operation_type'] == 'buy' else 'por debajo'} "
                        f"del precio actual ({current_price:.6f})"
                    )
                    return
            
            # Actualizar operación
            update_data = {'stop_loss' if tipo == 'sl' else 'take_profit': value}
            supabase.table('operations').update(update_data).eq('id', op_id).execute()
            
            await update.message.reply_text(
                f"✅ {'Stop Loss' if tipo == 'sl' else 'Take Profit'} actualizado a {value:.6f}",
                reply_markup=get_operation_detail_keyboard(op_id, False)
            )
            
            context.user_data.pop('modificando', None)
            return
        
        # Si no está modificando, es una nueva operación
        operacion_data = context.user_data.get('operacion')
        if not operacion_data:
            await update.message.reply_text("❌ No se encontraron datos de operación.")
            return
            
        esperando_sl = context.user_data.get('esperando_sl', False)
        esperando_tp = context.user_data.get('esperando_tp', False)
        
        if esperando_sl:
            # Validar SL
            max_sl_pips = calcular_max_sl(
                operacion_data['monto_riesgo'], operacion_data['asset_id'], 
                operacion_data['entry_price'], operacion_data['operation_type'],
                operacion_data['leverage'], CUP_RATE
            )
            
            if value > max_sl_pips:
                await update.message.reply_text(
                    f"❌ El Stop Loss excede el máximo permitido de {max_sl_pips:.2f} pips.\n"
                    "Por favor, ingresa un valor válido:"
                )
                return
                
            operacion_data['sl_pips'] = value
            context.user_data['esperando_sl'] = False
            context.user_data['esperando_tp'] = True
            
            await update.message.reply_text(
                f"✅ Stop Loss: {value:.2f} pips\n\n"
                "Por favor, ingresa el Take Profit en pips:"
            )
            
        elif esperando_tp:
            operacion_data['tp_pips'] = value
            
            # Calcular precios SL y TP
            entry_price = operacion_data['entry_price']
            pip_value = PIP_VALUES[operacion_data['asset_id']]
            
            if operacion_data['operation_type'] == 'buy':
                sl_price = entry_price - (operacion_data['sl_pips'] * pip_value)
                tp_price = entry_price + (value * pip_value)
            else:  # sell
                sl_price = entry_price + (operacion_data['sl_pips'] * pip_value)
                tp_price = entry_price - (value * pip_value)
                
            operacion_data['sl_price'] = sl_price
            operacion_data['tp_price'] = tp_price
            
            # Crear operación en la base de datos
            try:
                operation_data = {
                    'user_id': user_id,
                    'asset': operacion_data['asset_id'],
                    'currency': operacion_data['currency'],
                    'operation_type': operacion_data['operation_type'],
                    'entry_price': entry_price,
                    'apalancamiento': operacion_data['leverage'],
                    'stop_loss': sl_price,
                    'take_profit': tp_price,
                    'monto_riesgo': operacion_data['monto_riesgo'],
                    'status': 'pendiente',
                    'entry_time': datetime.now(timezone.utc).isoformat()
                }
                
                response = supabase.table('operations').insert(operation_data).execute()
                operation_id = response.data[0]['id'] if response.data else None
                
                if operation_id:
                    asset = ASSETS[operacion_data['asset_id']]
                    await update.message.reply_text(
                        f"✅ Operación creada exitosamente!\n\n"
                        f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                        f"Tipo: {'COMPRA' if operacion_data['operation_type'] == 'buy' else 'VENTA'}\n"
                        f"Apalancamiento: x{operacion_data['leverage']}\n"
                        f"Precio entrada: {entry_price:.6f}\n"
                        f"Stop Loss: {sl_price:.6f}\n"
                        f"Take Profit: {tp_price:.6f}\n"
                        f"Monto riesgo: {operacion_data['monto_riesgo']} CUP\n\n"
                        "Puedes ver y gestionar tu operación en el menú 'Operaciones'.",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        "❌ Error al crear la operación. Intenta nuevamente.",
                        reply_markup=get_main_keyboard()
                    )
                    
            except Exception as e:
                logger.error(f"Error creando operación: {e}")
                await update.message.reply_text(
                    "❌ Error al crear la operación. Intenta nuevamente.",
                    reply_markup=get_main_keyboard()
                )
            
            # Limpiar datos de operación
            context.user_data.pop('operacion', None)
            context.user_data.pop('esperando_tp', None)
            
    except ValueError:
        await update.message.reply_text("❌ Por favor, ingresa un número válido.")

# Handler para recibir montos de depósito/retiro
async def recibir_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        monto = float(text)
        solicitud = context.user_data.get('solicitud', {})
        tipo = solicitud.get('tipo')
        
        if not tipo:
            await update.message.reply_text("❌ No se encontró tipo de solicitud.")
            context.user_data.pop('esperando_monto', None)
            return
            
        if tipo == 'deposito':
            if monto < MIN_DEPOSITO:
                await update.message.reply_text(
                    f"❌ El monto mínimo de depósito es {MIN_DEPOSITO} CUP.\n"
                    "Por favor, ingresa un monto válido:"
                )
                return
                
            context.user_data['solicitud']['monto'] = monto
            await update.message.reply_text(
                f"💵 Monto a depositar: {monto} CUP\n\n"
                "Por favor, envía el comprobante de pago (foto o captura de pantalla):"
            )
            context.user_data['esperando_datos'] = True
            
        else:  # retiro
            saldo = obtener_saldo(user_id)
            if monto < MIN_RETIRO:
                await update.message.reply_text(
                    f"❌ El monto mínimo de retiro es {MIN_RETIRO} CUP.\n"
                    "Por favor, ingresa un monto válido:"
                )
                return
                
            if monto > saldo:
                await update.message.reply_text(
                    f"❌ No tienes suficiente saldo. Tu saldo actual es: {saldo:.2f} CUP\n"
                    "Por favor, ingresa un monto válido:"
                )
                return
                
            context.user_data['solicitud']['monto'] = monto
            await update.message.reply_text(
                f"💵 Monto a retirar: {monto} CUP\n\n"
                "💳 Por favor envía tu número de tarjeta y teléfono separados por un guion (-).\n\n"
                "Ejemplo: 9227 0699 9532 8054-59190241"
            )
            context.user_data['esperando_datos'] = True
        
        context.user_data.pop('esperando_monto', None)
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, ingresa un número válido.")

# Handler para recibir comprobantes y datos de retiro
async def recibir_datos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    user = update.message.from_user
    username = f"@{user.username}" if user.username else "Sin username"
    solicitud = context.user_data.get('solicitud', {})
    tipo = solicitud.get('tipo')
    monto = solicitud.get('monto')
    
    if not tipo or not monto:
        await update.message.reply_text("❌ No se encontraron datos de solicitud.")
        context.user_data.pop('esperando_datos', None)
        return
        
    if tipo == 'deposito':
        if update.message.photo:
            # Es una foto (comprobante de depósito)
            file_id = update.message.photo[-1].file_id
            file = await context.bot.get_file(file_id)
            file_url = file.file_path
            
            # Crear solicitud de depósito
            datos = f"Comprobante: {file_url}"
            solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
            
            if solicitud_id:
                # Mensaje para el admin con ID de usuario
                admin_message = (f"🔄 Nueva solicitud de DEPÓSITO\n\n"
                                f"👤 Usuario: {username} (ID: {user_id})\n"
                                f"💳 Monto: {monto} CUP\n"
                                f"📋 Datos: {datos}\n"
                                f"🆔 ID de solicitud: {solicitud_id}")
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=admin_message,
                        reply_markup=get_admin_keyboard(solicitud_id, tipo)
                    )
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")
                
                await update.message.reply_text(
                    "✅ Comprobante recibido. Tu solicitud de depósito ha sido enviada para revisión.",
                    reply_markup=get_navigation_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Error al crear la solicitud. Intenta nuevamente.",
                    reply_markup=get_navigation_keyboard()
                )
        else:
            await update.message.reply_text("Por favor, envía una foto del comprobante de pago.")
        
    else:  # retiro
        if update.message.text:
            datos = update.message.text
            # Verificar formato de datos (tarjeta y teléfono)
            if '-' not in datos:
                await update.message.reply_text(
                    "❌ Formato incorrecto. Por favor envía el número de tarjeta y teléfono separados por un guion (-).\n\n"
                    "Ejemplo: 9227 0699 9532 8054-59190241"
                )
                return

            # Crear solicitud de retiro inmediatamente sin pedir comprobante
            solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
            if solicitud_id:
                # Mensaje para el admin
                admin_message = (f"🔄 Nueva solicitud de RETIRO\n\n"
                                f"👤 Usuario: {username} (ID: {user_id})\n"
                                f"💳 Monto: {monto} CUP\n"
                                f"📋 Datos: {datos}\n"
                                f"🆔 ID de solicitud: {solicitud_id}")
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=admin_message,
                        reply_markup=get_admin_keyboard(solicitud_id, tipo)
                    )
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")

                await update.message.reply_text(
                    "✅ Solicitud de retiro enviada para revisión. Te notificaremos cuando sea procesada.",
                    reply_markup=get_navigation_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Error al crear la solicitud. Intenta nuevamente.",
                    reply_markup=get_navigation_keyboard()
                )
            
            # Limpiar datos de solicitud
            context.user_data.pop('solicitud', None)
        else:
            await update.message.reply_text("Por favor, envía los datos en formato texto.")
    
    context.user_data.pop('esperando_datos', None)

# Handler para recibir motivos de rechazo (admin)
async def recibir_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    motivo = update.message.text.strip()
    
    rechazando = context.user_data.get('rechazando')
    if not rechazando:
        await update.message.reply_text("❌ No se encontraron datos de rechazo.")
        return
        
    solicitud_id = rechazando['solicitud_id']
    tipo = rechazando['tipo']
    
    # Actualizar solicitud como rechazada
    if actualizar_solicitud(solicitud_id, "rechazada", motivo):
        # Obtener datos de la solicitud para notificar al usuario
        try:
            response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
            solicitud = response.data[0] if response.data else None
            
            if solicitud:
                # Notificar al usuario
                try:
                    await context.bot.send_message(
                        chat_id=solicitud['user_id'],
                        text=f"❌ Tu solicitud de {tipo} de {solicitud['monto']} CUP ha sido rechazada.\n"
                             f"Motivo: {motivo}",
                        reply_markup=get_navigation_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Error notificando usuario: {e}")
        except Exception as e:
            logger.error(f"Error obteniendo datos de solicitud: {e}")
        
        await update.message.reply_text("✅ Solicitud rechazada y usuario notificado.")
    else:
        await update.message.reply_text("❌ Error al rechazar la solicitud.")
        
    context.user_data.pop('rechazando', None)

# Función para comprobar operación
async def check_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, op_id: int):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    try:
        response = supabase.table('operations').select('*').eq('id', op_id).execute()
        operation = response.data[0] if response.data else None
        
        if not operation:
            await query.answer("❌ Operación no encontrada.")
            return
            
        current_price = get_current_price(operation['asset'], operation['currency'])
        pips_movidos = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
        
        # Verificar si se alcanzó SL o TP
        sl_alcanzado = False
        tp_alcanzado = False
        
        if operation['stop_loss']:
            if (operation['operation_type'] == 'buy' and current_price <= operation['stop_loss']) or \
               (operation['operation_type'] == 'sell' and current_price >= operation['stop_loss']):
                sl_alcanzado = True
                
        if operation['take_profit']:
            if (operation['operation_type'] == 'buy' and current_price >= operation['take_profit']) or \
               (operation['operation_type'] == 'sell' and current_price <= operation['take_profit']):
                tp_alcanzado = True
                
        asset = ASSETS[operation['asset']]
        message = (
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Precio actual: {current_price:.6f}\n"
            f"Pips movidos: {pips_movidos:.2f}\n"
        )
        
        if sl_alcanzado:
            message += "🛑 Stop Loss alcanzado\n"
        if tp_alcanzado:
            message += "🎯 Take Profit alcanzado\n"
            
        if not sl_alcanzado and not tp_alcanzado:
            message += "📈 Operación aún activa\n"
            
        await query.edit_message_text(
            message,
            reply_markup=get_operation_detail_keyboard(op_id, False)
        )
        
    except Exception as e:
        logger.error(f"Error comprobando operación: {e}")
        await query.answer("❌ Error al comprobar la operación.")

# Comando para establecer saldo (solo admin)
async def set_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Comando solo disponible para el administrador.")
        return
        
    if not context.args or len(context.args) < 2:
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
        await update.message.reply_text("❌ Error al establecer saldo.")

# Comando para establecer ID de grupo
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
    await update.message.reply_text(f"✅ ID de grupo establecido a: {GROUP_ID}")

# Comando para obtener ID de chat
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    await update.message.reply_text(f"El ID de este chat es: {chat_id}", parse_mode="Markdown")

# Función para procesar selección de apalancamiento
async def process_leverage_selection(query, context, asset_id, currency, operation_type, leverage):
    asset = ASSETS[asset_id]
    price = get_current_price(asset_id, currency)
    
    if price == 0:
        await query.edit_message_text(
            "❌ Error al obtener el precio actual. Intenta nuevamente.",
            reply_markup=get_main_keyboard()
        )
        return
        
    # Guardar datos de operación
    context.user_data['operacion'] = {
        'asset_id': asset_id,
        'currency': currency,
        'operation_type': operation_type,
        'leverage': leverage,
        'entry_price': price
    }
    
    saldo = obtener_saldo(str(query.from_user.id))
    await query.edit_message_text(
        f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
        f"Precio actual: {price:.6f} {currency}\n"
        f"Operación: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n"
        f"Apalancamiento: x{leverage}\n\n"
        f"💰 Tu saldo actual: {saldo:.2f} CUP\n\n"
        f"Por favor, ingresa el monto de riesgo en CUP (mínimo {MIN_RIESGO} CUP):"
    )

# Función unificada para mensajes de texto
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    
    if user_data.get('esperando_monto', False):
        await recibir_monto(update, context)
    elif user_data.get('esperando_apalancamiento', False):
        await recibir_apalancamiento(update, context)
    elif user_data.get('esperando_sl', False) or user_data.get('esperando_tp', False):
        await set_sl_tp(update, context)
    elif user_data.get('rechazando', False):
        await recibir_motivo(update, context)
    elif user_data.get('modificando', False):
        await set_sl_tp(update, context)
    elif user_data.get('esperando_datos', False):
        await recibir_datos(update, context)
    else:
        # Mensaje no reconocido
        await update.message.reply_text(
            "No entiendo ese comando. Usa /start para comenzar.",
            reply_markup=get_main_keyboard()
        )

# Handler para fotos (solo para comprobantes de depósito)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    if 'solicitud' in user_data and 'monto' in user_data['solicitud'] and user_data['solicitud']['tipo'] == 'deposito':
        await recibir_datos(update, context)
    else:
        # Si no está en el estado de depósito, ignorar la foto
        pass

# Función keep-alive
async def keep_alive(context: ContextTypes.DEFAULT_TYPE):
    try:
        # Hacer una petición a una URL conocida para mantener la app activa
        requests.get("https://google.com", timeout=5)
        logger.info("✅ Keep-alive ejecutado")
    except Exception as e:
        logger.warning(f"⚠️ Keep-alive falló: {e}")

        # Main con webhook
def main():
    PORT = int(os.environ.get('PORT', 10000))
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://qvabotcrypto.onrender.com')
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setsaldo", set_saldo))
    application.add_handler(CommandHandler("setgroupid", set_group_id))
    application.add_handler(CommandHandler("getchatid", get_chat_id))
    
    application.add_handler(CallbackQueryHandler(button_click))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Job queue para keep-alive
    job_queue = application.job_queue
    job_queue.run_repeating(keep_alive, interval=300, first=10)
    
    # Iniciar bot
    if WEBHOOK_URL:
        # Configurar webhook para Render
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        # Modo polling para desarrollo
        application.run_polling()

if __name__ == "__main__":
    main()

        
