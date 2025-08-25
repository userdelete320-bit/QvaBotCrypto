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
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhvd3NtcHVraGVkdWtlb3FjcmViIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ4MzkwNDEsImV4cCI6MjA3MDQxNTA0MX0.zy1rCXPfuNQ95Bk0ATTkdF6DGLB9DhG9EjaBr0v3c0M"
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
        
        # Verificar si el usuario existe en la tabla
        response = supabase.table('balance').select('*').eq('user_id', user_id).execute()
        
        if response.data:
            # Actualizar saldo existente
            supabase.table('balance').update({'saldo': nuevo_saldo}).eq('user_id', user_id).execute()
        else:
            # Insertar nuevo registro
            supabase.table('balance').insert({'user_id': user_id, 'saldo': nuevo_saldo}).execute()
            
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
        logger.error(f"Error obteniendo precio: {e}")
        return 0.0

def get_historical_prices(asset_id: str, start_time: datetime, end_time: datetime, interval: str = "m1") -> list:
    try:
        coincap_id = ASSETS[asset_id]["coincap_id"]
        headers = {
            "Authorization": f"Bearer {COINCAP_API_KEY}",
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
        
        return [(datetime.fromtimestamp(item['time']/1000), float(item['priceUsd'])) for item in data['data']]
    except Exception as e:
        logger.error(f"Error obteniendo precios históricos: {e}")
        return []

def analyze_price_history(price_history, entry_price, sl_price, tp_price, operation_type):
    if not price_history:
        return None, None
        
    # Implementar análisis de precio histórico
    max_price = max(price[1] for price in price_history)
    min_price = min(price[1] for price in price_history)
    
    if operation_type == "buy":
        if min_price <= sl_price:
            return "sl", min_price
        elif max_price >= tp_price:
            return "tp", max_price
    else:  # sell
        if max_price >= sl_price:
            return "sl", max_price
        elif min_price <= tp_price:
            return "tp", min_price
            
    return None, None

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
    buttons.append([InlineKeyboardButton("💳 Balance", callback_data="balance")])
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
            f"{asset['emoji']} {asset['symbol']} {op['operation_type']} x{op['apalancamiento']}",
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
        result_emoji = "✅" if op['result'] == "ganancia" else "❌" if op['result'] == "perdida" else "➖"
        buttons.append([InlineKeyboardButton(
            f"{result_emoji} {asset['emoji']} {asset['symbol']} {op['operation_type']}",
            callback_data=f"history_{op['id']}"
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
        InlineKeyboardButton("🏠 Menú Principal", callback_data="back_main")],
        [InlineKeyboardButton("💳 Ver Balance", callback_data="balance")]
    ])

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
        await query.edit_message_text("Selecciona un activo para operar:", reply_markup=get_main_keyboard())
    
    elif data == "back_main":
        await query.edit_message_text("Selecciona un activo para operar:", reply_markup=get_main_keyboard())
    
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
    
    elif data == "balance":
        saldo = obtener_saldo(user_id)
        await query.edit_message_text(
            f"💳 Tu saldo actual: {saldo:.2f} CUP\n\n"
            "Selecciona una opción:",
            reply_markup=get_balance_keyboard()
        )
    
    elif data == "depositar":
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
    
    elif data == "retirar":
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
    
    elif data == "operations":
        await query.edit_message_text(
            "Tus operaciones activas:",
            reply_markup=get_operations_keyboard(user_id)
        )
    
    elif data == "history":
        await query.edit_message_text(
            "Tu historial de operaciones:",
            reply_markup=get_history_keyboard(user_id)
        )
    
    elif data.startswith("op_"):
        op_id = int(data.split("_")[1])
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0] if response.data else None
            
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
        except Exception as e:
            logger.error(f"Error obteniendo operación: {e}")
            await query.edit_message_text("❌ Error al obtener los detalles de la operación.")
    
    elif data.startswith("history_"):
        op_id = int(data.split("_")[1])
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0] if response.data else None
            
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
        except Exception as e:
            logger.error(f"Error obteniendo operación histórica: {e}")
            await query.edit_message_text("❌ Error al obtener los detalles de la operación.")
    
    elif data.startswith("close_op_"):
        op_id = int(data.split("_")[2])
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0] if response.data else None
            
            if operation:
                current_price = get_current_price(operation['asset'], operation['currency'])
                pips_movidos = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
                
                if operation['operation_type'] == 'buy':
                    result = "ganancia" if current_price > operation['entry_price'] else "perdida"
                else:
                    result = "ganancia" if current_price < operation['entry_price'] else "perdida"
                
                # Calcular monto de resultado
                valor_pip = calcular_valor_pip(operation['asset'], CUP_RATE)
                resultado_monto = pips_movidos * valor_pip * operation['apalancamiento']
                if result == "perdida":
                    resultado_monto = -resultado_monto
                
                # Actualizar operación
                update_data = {
                    'status': 'cerrada',
                    'exit_price': current_price,
                    'exit_time': datetime.now(timezone.utc).isoformat(),
                    'result': result,
                    'result_amount': resultado_monto
                }
                
                supabase.table('operations').update(update_data).eq('id', op_id).execute()
                
                # Actualizar saldo
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
                await query.edit_message_text("❌ Operación no encontrada.")
        except Exception as e:
            logger.error(f"Error cerrando operación: {e}")
            await query.edit_message_text("❌ Error al cerrar la operación.")
    
    elif data.startswith("check_op_"):
        op_id = int(data.split("_")[2])
        await check_operation(update, context, op_id)
    
    elif data.startswith("mod_sl_"):
        op_id = int(data.split("_")[2])
        context.user_data['modifying_sl'] = op_id
        await query.edit_message_text("Por favor, envía el nuevo valor para el Stop Loss:")
    
    elif data.startswith("mod_tp_"):
        op_id = int(data.split("_")[2])
        context.user_data['modifying_tp'] = op_id
        await query.edit_message_text("Por favor, envía el nuevo valor para el Take Profit:")
    
    elif data.startswith("apr_"):
        if user_id != ADMIN_ID:
            await query.answer("❌ Solo el administrador puede realizar esta acción.")
            return
            
        parts = data.split("_")
        tipo = parts[1]
        solicitud_id = int(parts[2])
        
        # Obtener información de la solicitud
        try:
            response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
            solicitud = response.data[0] if response.data else None
            
            if not solicitud:
                await query.answer("❌ Solicitud no encontrada.")
                return
                
            user_id_solicitud = solicitud['user_id']
            monto = solicitud['monto']
            
            if tipo == 'deposito':
                # Aprobar depósito - acreditar saldo
                nuevo_saldo = actualizar_saldo(user_id_solicitud, monto)
                actualizar_solicitud(solicitud_id, 'aprobada')
                
                # Notificar al usuario
                try:
                    await context.bot.send_message(
                        chat_id=user_id_solicitud,
                        text=f"✅ Tu depósito de {monto} CUP ha sido aprobado.\n\n💳 Tu nuevo saldo: {nuevo_saldo:.2f} CUP",
                        reply_markup=get_navigation_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Error notificando al usuario: {e}")
                
                await query.edit_message_text(f"✅ Depósito aprobado. Nuevo saldo: {nuevo_saldo:.2f} CUP")
                
            else:  # retiro
                # Verificar saldo suficiente
                saldo_actual = obtener_saldo(user_id_solicitud)
                if saldo_actual < monto:
                    actualizar_solicitud(solicitud_id, 'rechazada', 'Saldo insuficiente')
                    await query.edit_message_text("❌ Saldo insuficiente para aprobar el retiro.")
                    return
                    
                # Aprobar retiro - debitar saldo
                nuevo_saldo = actualizar_saldo(user_id_solicitud, -monto)
                actualizar_solicitud(solicitud_id, 'aprobada')
                
                # Notificar al usuario
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
    
    elif data.startswith("rej_"):
        if user_id != ADMIN_ID:
            await query.answer("❌ Solo el administrador puede realizar esta acción.")
            return
            
        parts = data.split("_")
        tipo = parts[1]
        solicitud_id = int(parts[2])
        
        context.user_data['rechazando_solicitud'] = {
            'solicitud_id': solicitud_id,
            'tipo': tipo
        }
        await query.edit_message_text("Por favor, envía el motivo del rechazo:")

    # Manejar confirmación y cancelación de operaciones
    elif data == "confirm_trade":
        # Obtener todos los datos de la operación del user_data
        trade_data = context.user_data.get('trade_data', {})
        monto_riesgo = context.user_data.get('monto_riesgo')
        sl_pips = context.user_data.get('sl_pips')
        tp_pips = context.user_data.get('tp_pips')
        sl_price = context.user_data.get('sl_price')
        tp_price = context.user_data.get('tp_price')
        
        if not all([trade_data, monto_riesgo, sl_pips, tp_pips, sl_price, tp_price]):
            await query.edit_message_text("❌ Error: Datos de operación incompletos. Comienza nuevamente.")
            return
            
        # Insertar operación en la base de datos
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
            
            response = supabase.table('operations').insert(operation_data).execute()
            if response.data:
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
        
        # Limpiar user_data
        keys_to_remove = ['trade_data', 'monto_riesgo', 'sl_pips', 'tp_pips', 'sl_price', 'tp_price', 'state']
        for key in keys_to_remove:
            context.user_data.pop(key, None)
            
    elif data == "cancel_trade":
        # Limpiar user_data y cancelar
        keys_to_remove = ['trade_data', 'monto_riesgo', 'sl_pips', 'tp_pips', 'sl_price', 'tp_price', 'state']
        for key in keys_to_remove:
            context.user_data.pop(key, None)
        await query.edit_message_text("❌ Operación cancelada.", reply_markup=get_navigation_keyboard())

# Handler para recibir apalancamiento personalizado
async def recibir_apalancamiento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        leverage = float(text)
        if leverage <= 0:
            await update.message.reply_text("❌ El apalancamiento debe ser mayor a 0. Intenta nuevamente.")
            return
            
        custom_data = context.user_data.get('awaiting_custom_leverage')
        if custom_data:
            asset_id = custom_data['asset_id']
            currency = custom_data['currency']
            operation_type = custom_data['operation_type']
            
            await process_leverage_selection(update, context, asset_id, currency, operation_type, leverage)
            
            # Limpiar estado
            del context.user_data['awaiting_custom_leverage']
        else:
            await update.message.reply_text("❌ No se encontraron datos de operación. Comienza nuevamente.")
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido para el apalancamiento.")

# Handler para recibir monto de riesgo
async def recibir_monto_riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        monto_riesgo = float(text)
        if monto_riesgo < MIN_RIESGO:
            await update.message.reply_text(f"❌ El monto de riesgo mínimo es {MIN_RIESGO} CUP. Intenta nuevamente.")
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
            
        # Calcular SL máximo
        max_sl_pips = calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, CUP_RATE)
        
        asset = ASSETS[asset_id]
        valor_pip = calcular_valor_pip(asset_id, CUP_RATE) * leverage
        
        await update.message.reply_text(
            f"📊 Análisis de riesgo\n\n"
            f"💰 Monto de riesgo: {monto_riesgo} CUP\n"
            f"📏 SL máximo: {max_sl_pips:.2f} pips\n"
            f"💵 Valor por pip: {valor_pip:.2f} CUP\n\n"
            f"Por favor, envía el valor para el Stop Loss (en pips):"
        )
        
        context.user_data['monto_riesgo'] = monto_riesgo
        context.user_data['state'] = 'esperando_sl'
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido para el monto de riesgo.")

# Handler para recibir SL/TP
async def set_sl_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        value = float(text)
        state = context.user_data.get('state')
        
        if state == 'esperando_sl':
            # Verificar que el SL no exceda el máximo permitido
            monto_riesgo = context.user_data.get('monto_riesgo')
            trade_data = context.user_data.get('trade_data', {})
            asset_id = trade_data.get('asset_id')
            entry_price = trade_data.get('entry_price')
            operation_type = trade_data.get('operation_type')
            leverage = trade_data.get('leverage')
            
            max_sl_pips = calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, CUP_RATE)
            
            if value > max_sl_pips:
                await update.message.reply_text(
                    f"❌ El Stop Loss excede el máximo permitido de {max_sl_pips:.2f} pips. "
                    f"Envía un valor menor o igual:"
                )
                return
                
            context.user_data['sl_pips'] = value
            
            # Calcular precio de SL
            pip_value = PIP_VALUES.get(asset_id, 0.01)
            if operation_type == 'buy':
                sl_price = entry_price - (value * pip_value)
            else:
                sl_price = entry_price + (value * pip_value)
                
            context.user_data['sl_price'] = sl_price
            
            await update.message.reply_text("✅ Stop Loss establecido. Ahora envía el valor para el Take Profit (en pips):")
            context.user_data['state'] = 'esperando_tp'
            
        elif state == 'esperando_tp':
            context.user_data['tp_pips'] = value
            
            # Calcular precio de TP
            trade_data = context.user_data.get('trade_data', {})
            asset_id = trade_data.get('asset_id')
            entry_price = trade_data.get('entry_price')
            operation_type = trade_data.get('operation_type')
            
            pip_value = PIP_VALUES.get(asset_id, 0.01)
            if operation_type == 'buy':
                tp_price = entry_price + (value * pip_value)
            else:
                tp_price = entry_price - (value * pip_value)
                
            context.user_data['tp_price'] = tp_price
            
            # Confirmar operación
            sl_price = context.user_data.get('sl_price')
            tp_price = context.user_data.get('tp_price')
            monto_riesgo = context.user_data.get('monto_riesgo')
            
            asset = ASSETS[asset_id]
            operation_type_text = "COMPRA" if operation_type == 'buy' else "VENTA"
            
            # Calcular riesgo/recompensa
            riesgo_recompensa = value / context.user_data.get('sl_pips', 1) if context.user_data.get('sl_pips', 0) > 0 else 0
            
            message = (
                f"📋 Resumen de operación\n\n"
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Operación: {operation_type_text}\n"
                f"Apalancamiento: x{leverage}\n"
                f"Precio entrada: {entry_price:.8f}\n"
                f"Stop Loss: {sl_price:.8f} ({context.user_data.get('sl_pips', 0):.2f} pips)\n"
                f"Take Profit: {tp_price:.8f} ({value:.2f} pips)\n"
                f"Monto riesgo: {monto_riesgo} CUP\n"
                f"Riesgo/Recompensa: 1:{riesgo_recompensa:.2f}\n\n"
                f"¿Confirmar operación?"
            )
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confirmar", callback_data="confirm_trade"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel_trade")
            ]])
            
            await update.message.reply_text(message, reply_markup=keyboard)
            context.user_data['state'] = 'confirmando_operacion'
            
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido.")

# Handler para recibir montos de depósito/retiro
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

# Handler para recibir comprobantes y datos de retiro
async def recibir_datos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    user = update.message.from_user
    username = f"@{user.username}" if user.username else "Sin username"
    solicitud = context.user_data.get('solicitud', {})
    tipo = solicitud.get('tipo')
    monto = solicitud.get('monto')
    
    if tipo == 'deposito':
        # Para depósito, esperamos una foto
        if update.message.photo:
            # Guardar información de la foto (en un sistema real, deberías guardar la imagen)
            file_id = update.message.photo[-1].file_id
            file = await context.bot.get_file(file_id)
            file_path = file.file_path
            
            # Crear solicitud de depósito
            datos = f"Comprobante: {file_path}"
            solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
            
            if solicitud_id:
                # Mensaje para admin con ID de usuario
                admin_message = (f"📥 Nueva solicitud de DEPÓSITO\n"
                               f"👤 Usuario: {username} (ID: {user_id})\n"
                               f"💵 Monto: {monto} CUP\n"
                               f"📋 Datos: {datos}")
                
                keyboard = get_admin_keyboard(solicitud_id, tipo)
                try:
                    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=keyboard)
                    await context.bot.send_message(chat_id=GROUP_ID, text=admin_message, reply_markup=keyboard)
                except Exception as e:
                    logger.error(f"Error notificando al admin: {e}")

                await update.message.reply_text(
                    "✅ Comprobante recibido. Espera la confirmación del administrador.",
                    reply_markup=get_navigation_keyboard()
                )
            else:
                await update.message.reply_text("❌ Error creando la solicitud. Intenta nuevamente.")
            
            context.user_data.clear()
        else:
            await update.message.reply_text("❌ Por favor, envía una foto del comprobante.")
    
    else:  # retiro
        # Para retiro, esperamos texto con tarjeta y teléfono
        datos = update.message.text.strip()
        
        # Crear solicitud de retiro
        solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
        
        if solicitud_id:
            # Mensaje para admin con ID de usuario
            admin_message = (f"📤 Nueva solicitud de RETIRO\n"
                           f"👤 Usuario: {username} (ID: {user_id})\n"
                           f"💳 Monto: {monto} CUP\n"
                           f"📋 Datos: {datos}")
            
            keyboard = get_admin_keyboard(solicitud_id, tipo)
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=keyboard)
                await context.bot.send_message(chat_id=GROUP_ID, text=admin_message, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error notificando al admin: {e}")

            await update.message.reply_text(
                "✅ Solicitud de retiro enviada. Espera la confirmación del administrador.",
                reply_markup=get_navigation_keyboard()
            )
        else:
            await update.message.reply_text("❌ Error creando la solicitud. Intenta nuevamente.")
        
        context.user_data.clear()

# Handler para recibir motivos de rechazo (admin)
async def recibir_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    motivo = update.message.text.strip()
    
    solicitud_data = context.user_data.get('rechazando_solicitud')
    if solicitud_data:
        solicitud_id = solicitud_data['solicitud_id']
        tipo = solicitud_data['tipo']
        
        # Actualizar solicitud como rechazada
        if actualizar_solicitud(solicitud_id, 'rechazada', motivo):
            # Obtener información de la solicitud para notificar al usuario
            try:
                response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
                solicitud = response.data[0] if response.data else None
                
                if solicitud:
                    user_id_solicitud = solicitud['user_id']
                    monto = solicitud['monto']
                    
                    # Notificar al usuario
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
        
        # Limpiar estado
        del context.user_data['rechazando_solicitud']
    else:
        await update.message.reply_text("❌ No se encontró solicitud para rechazar.")

# Función para comprobar operación
async def check_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, op_id: int):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    try:
        response = supabase.table('operations').select('*').eq('id', op_id).execute()
        operation = response.data[0] if response.data else None
        
        if operation:
            current_price = get_current_price(operation['asset'], operation['currency'])
            pips_movidos = calcular_pips_movidos(operation['entry_price'], current_price, operation['asset'])
            
            # Calcular ganancia/pérdida actual
            valor_pip = calcular_valor_pip(operation['asset'], CUP_RATE)
            resultado_actual = pips_movidos * valor_pip * operation['apalancamiento']
            
            if operation['operation_type'] == 'sell':
                resultado_actual = -resultado_actual
                
            asset = ASSETS[operation['asset']]
            operation_type = "COMPRA" if operation['operation_type'] == 'buy' else "VENTA"
            resultado_text = f"{resultado_actual:.2f} CUP" if resultado_actual >= 0 else f"{resultado_actual:.2f} CUP"
            emoji_resultado = "✅" if resultado_actual >= 0 else "❌"
            
            # Verificar si se alcanzó SL o TP
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
    except Exception as e:
        logger.error(f"Error comprobando operación: {e}")
        await query.edit_message_text("❌ Error al comprobar la operación.")

# Comando para establecer saldo (solo admin)
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
    await update.message.reply_text(f"✅ ID de grupo actualizado a: {GROUP_ID}")

# Comando para obtener ID de chat
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    await update.message.reply_text(f"El ID de este chat es: `{chat_id}`", parse_mode="Markdown")

# Función para procesar selección de apalancamiento
async def process_leverage_selection(update, context, asset_id, currency, operation_type, leverage):
    asset = ASSETS[asset_id]
    price = get_current_price(asset_id, currency)
    
    operation_type_text = "COMPRA" if operation_type == "buy" else "VENTA"
    
    # Guardar datos de la operación
    context.user_data['trade_data'] = {
        'asset_id': asset_id,
        'currency': currency,
        'operation_type': operation_type,
        'leverage': leverage,
        'entry_price': price
    }
    
    message = (
        f"📊 Configuración de operación\n\n"
        f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
        f"Operación: {operation_type_text}\n"
        f"Apalancamiento: x{leverage}\n"
        f"Precio actual: {price:.8f} {currency}\n\n"
        f"Por favor, envía el monto que deseas arriesgar (en CUP):"
    )
    
    if hasattr(update, 'edit_message_text'):
        await update.edit_message_text(message)
    else:
        await update.message.reply_text(message)
    
    context.user_data['state'] = 'esperando_monto_riesgo'

# Función unificada para mensajes de texto
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
        await recibir_motivo(update, context)
    elif 'awaiting_custom_leverage' in user_data:
        await recibir_apalancamiento(update, context)
    elif 'modifying_sl' in user_data or 'modifying_tp' in user_data:
        # Manejar modificación de SL/TP
        try:
            value = float(text)
            if 'modifying_sl' in user_data:
                op_id = user_data['modifying_sl']
                # Actualizar SL en la base de datos
                supabase.table('operations').update({'sl_price': value}).eq('id', op_id).execute()
                await update.message.reply_text("✅ Stop Loss actualizado correctamente.")
                del user_data['modifying_sl']
            elif 'modifying_tp' in user_data:
                op_id = user_data['modifying_tp']
                # Actualizar TP en la base de datos
                supabase.table('operations').update({'tp_price': value}).eq('id', op_id).execute()
                await update.message.reply_text("✅ Take Profit actualizado correctamente.")
                del user_data['modifying_tp']
        except ValueError:
            await update.message.reply_text("❌ Por favor, envía un número válido.")
    else:
        # Mensaje no reconocido
        await update.message.reply_text(
            "No entiendo ese comando. Usa /start para comenzar.",
            reply_markup=get_navigation_keyboard()
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
    
    # Añadir handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setsaldo", set_saldo))
    application.add_handler(CommandHandler("setgroupid", set_group_id))
    application.add_handler(CommandHandler("getchatid", get_chat_id))
    
    application.add_handler(CallbackQueryHandler(button_click))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Añadir job de keep-alive
    job_queue = application.job_queue
    job_queue.run_repeating(keep_alive, interval=300, first=10)
    
    # Iniciar bot
    if WEBHOOK_URL:
        # Modo webhook para producción
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
