 main():
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
    
    if operation_type == "buy":
        max_sl_price = entry_price - (max_pips * PIP_VALUES[asset_id])
    else:  # sell
        max_sl_price = entry_price + (max_pips * PIP_VALUES[asset_id])
    
    return max_sl_price, max_pips

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
        return response.data[0]['id']
    except Exception as e:
        logger.error(f"Error creando solicitud: {e}")
        return -1

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
        
        return [{"time": item["time"], "price": float(item["priceUsd"])} for item in data["data"]]
    except Exception as e:
        logger.error(f"Error obteniendo precios históricos: {e}")
        return []

def analyze_price_history(price_history, entry_price, sl_price, tp_price, operation_type):
    if not price_history:
        return None, None
    
    # Verificar si se alcanzó el SL o TP
    sl_hit = False
    tp_hit = False
    
    for price_point in price_history:
        price = price_point["price"]
        
        if operation_type == "buy":
            if price <= sl_price:
                sl_hit = True
                break
            if price >= tp_price:
                tp_hit = True
                break
        else:  # sell
            if price >= sl_price:
                sl_hit = True
                break
            if price <= tp_price:
                tp_hit = True
                break
    
    return sl_hit, tp_hit

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
    
    for i, (asset_id, asset) in enumerate(ASSETS.items(), 1):
        row.append(InlineKeyboardButton(
            f"{asset['emoji']} {asset['symbol']}", 
            callback_data=f"asset_{asset_id}"
        ))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton("💳 Balance", callback_data="balance"),
        InlineKeyboardButton("📊 Operaciones", callback_data="operations"),
        InlineKeyboardButton("📋 Historial", callback_data="history")
    ])
    
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
        buttons.append([
            InlineKeyboardButton(
                f"{asset['emoji']} {asset['symbol']} {op['operation_type'].upper()} x{op['apalancamiento']}",
                callback_data=f"op_{op['id']}"
            )
        ])
    
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
        result_emoji = "🟢" if op['result'] == "ganancia" else "🔴" if op['result'] == "perdida" else "⚪"
        buttons.append([
            InlineKeyboardButton(
                f"{result_emoji} {asset['symbol']} {op['operation_type'].upper()} x{op['apalancamiento']}",
                callback_data=f"hist_{op['id']}"
            )
        ])
    
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
        await query.edit_message_text("Selecciona una opción:", reply_markup=get_main_keyboard())
    
    elif data == "back_main":
        await query.edit_message_text("Selecciona una opción:", reply_markup=get_main_keyboard())
    
    elif data == "balance":
        saldo = obtener_saldo(user_id)
        await query.edit_message_text(
            f"💳 Tu saldo actual: {saldo:.2f} CUP\n\n"
            "Selecciona una opción:",
            reply_markup=get_balance_keyboard()
        )
    
    elif data == "depositar":
        context.user_data['esperando'] = 'monto_deposito'
        await query.edit_message_text(
            f"💵 Para realizar un depósito, transfiere a la tarjeta:\n`{CARD_NUMBER}`\n\n"
            f"Luego envía el monto en CUP que deseas depositar (mínimo {MIN_DEPOSITO} CUP).\n\n"
            f"📞 Número de confirmación: {CONFIRMATION_NUMBER}",
            parse_mode="Markdown",
            reply_markup=get_navigation_keyboard()
        )
    
    elif data == "retirar":
        saldo = obtener_saldo(user_id)
        if saldo < MIN_RETIRO:
            await query.edit_message_text(
                f"❌ Saldo insuficiente para retirar. Mínimo: {MIN_RETIRO} CUP\n"
                f"Tu saldo actual: {saldo:.2f} CUP",
                reply_markup=get_balance_keyboard()
            )
            return
        
        context.user_data['esperando'] = 'monto_retiro'
        await query.edit_message_text(
            f"💵 Tu saldo disponible: {saldo:.2f} CUP\n\n"
            f"Envía el monto en CUP que deseas retirar (mínimo {MIN_RETIRO} CUP):",
            reply_markup=get_navigation_keyboard()
        )
    
    elif data == "operations":
        await query.edit_message_text(
            "📊 Tus operaciones activas:",
            reply_markup=get_operations_keyboard(user_id)
        )
    
    elif data == "history":
        await query.edit_message_text(
            "📋 Tu historial de operaciones:",
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
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']}) en {currency}\n\n"
            "Selecciona el tipo de operación:",
            reply_markup=get_trade_keyboard(asset_id, currency)
        )
    
    elif data.startswith("trade_"):
        parts = data.split("_")
        asset_id = parts[1]
        currency = parts[2]
        operation_type = parts[3]
        asset = ASSETS[asset_id]
        
        context.user_data['operacion'] = {
            'asset': asset_id,
            'currency': currency,
            'operation_type': operation_type
        }
        
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
            context.user_data['esperando'] = 'apalancamiento_personalizado'
            context.user_data['operacion'] = {
                'asset': asset_id,
                'currency': currency,
                'operation_type': operation_type
            }
            await query.edit_message_text(
                "🔢 Envía el nivel de apalancamiento personalizado:",
                reply_markup=get_navigation_keyboard()
            )
        else:
            asset_id = parts[1]
            currency = parts[2]
            operation_type = parts[3]
            leverage = int(parts[4])
            
            context.user_data['operacion']['apalancamiento'] = leverage
            context.user_data['esperando'] = 'monto_riesgo'
            
            asset = ASSETS[asset_id]
            await query.edit_message_text(
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Operación: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n"
                f"Apalancamiento: x{leverage}\n\n"
                f"Envía el monto en CUP que deseas arriesgar (mínimo {MIN_RIESGO} CUP):",
                reply_markup=get_navigation_keyboard()
            )
    
    elif data.startswith("op_") or data.startswith("hist_"):
        op_id = int(data.split("_")[1])
        is_history = data.startswith("hist_")
        
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0]
            
            asset = ASSETS[operation['asset']]
            result_text = ""
            
            if is_history:
                result_emoji = "🟢" if operation['result'] == "ganancia" else "🔴" if operation['result'] == "perdida" else "⚪"
                result_text = f"Resultado: {result_emoji} {operation['result'].capitalize() if operation['result'] else 'Sin resultado'}\n"
                if operation['close_price']:
                    result_text += f"Precio de cierre: {operation['close_price']}\n"
                if operation['profit_loss']:
                    result_text += f"Ganancia/Pérdida: {operation['profit_loss']} CUP\n"
            
            message = (
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Operación: {'COMPRA' if operation['operation_type'] == 'buy' else 'VENTA'}\n"
                f"Apalancamiento: x{operation['apalancamiento']}\n"
                f"Precio de entrada: {operation['entry_price']}\n"
                f"Stop Loss: {operation['sl_price']}\n"
                f"Take Profit: {operation['tp_price']}\n"
                f"Monto riesgo: {operation['monto_riesgo']} CUP\n"
                f"{result_text}"
                f"Fecha: {operation['entry_time']}"
            )
            
            await query.edit_message_text(
                message,
                reply_markup=get_operation_detail_keyboard(op_id, is_history)
            )
        except Exception as e:
            logger.error(f"Error obteniendo operación: {e}")
            await query.edit_message_text(
                "❌ Error al obtener los detalles de la operación.",
                reply_markup=get_operations_keyboard(user_id) if not is_history else get_history_keyboard(user_id)
            )
    
    elif data.startswith("close_op_"):
        op_id = int(data.split("_")[2])
        await check_operation(update, context, op_id)
    
    elif data.startswith("check_op_"):
        op_id = int(data.split("_")[2])
        
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            operation = response.data[0]
            
            current_price = get_current_price(operation['asset'], operation['currency'])
            pips_movidos = calcular_pips_movidos(
                operation['entry_price'], 
                current_price, 
                operation['asset']
            )
            
            ganancia_potencial = calcular_ganancia_pips(
                pips_movidos, 
                operation['asset'], 
                CUP_RATE, 
                operation['apalancamiento']
            )
            
            if operation['operation_type'] == 'buy':
                ganancia_potencial = ganancia_potencial if current_price > operation['entry_price'] else -ganancia_potencial
            else:
                ganancia_potencial = ganancia_potencial if current_price < operation['entry_price'] else -ganancia_potencial
            
            asset = ASSETS[operation['asset']]
            await query.edit_message_text(
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Precio actual: {current_price}\n"
                f"Precio entrada: {operation['entry_price']}\n"
                f"Pips movidos: {pips_movidos:.2f}\n"
                f"Ganancia/Pérdida potencial: {ganancia_potencial:.2f} CUP\n\n"
                f"¿Deseas cerrar la operación?",
                reply_markup=get_operation_detail_keyboard(op_id, False)
            )
        except Exception as e:
            logger.error(f"Error comprobando operación: {e}")
            await query.edit_message_text(
                "❌ Error al comprobar la operación.",
                reply_markup=get_operation_detail_keyboard(op_id, False)
            )
    
    elif data.startswith("apr_") or data.startswith("rej_"):
        if user_id != ADMIN_ID:
            await query.answer("❌ Solo los administradores pueden realizar esta acción.")
            return
        
        parts = data.split("_")
        action = parts[0]
        tipo = parts[1]
        solicitud_id = int(parts[2])
        
        if action == "apr":
            # Obtener información de la solicitud
            response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
            solicitud = response.data[0]
            
            if tipo == "deposito":
                # Aprobar depósito - acreditar saldo
                nuevo_saldo = actualizar_saldo(solicitud['user_id'], solicitud['monto'])
                actualizar_solicitud(solicitud_id, "aprobada")
                
                # Notificar al usuario
                try:
                    await context.bot.send_message(
                        chat_id=solicitud['user_id'],
                        text=f"✅ Tu depósito de {solicitud['monto']} CUP ha sido aprobado.\nNuevo saldo: {nuevo_saldo:.2f} CUP"
                    )
                except Exception as e:
                    logger.error(f"Error notificando usuario: {e}")
                
                await query.edit_message_text(
                    f"✅ Depósito aprobado.\nUsuario: {solicitud['user_id']}\nMonto: {solicitud['monto']} CUP\nNuevo saldo: {nuevo_saldo:.2f} CUP"
                )
            
            elif tipo == "retiro":
                # Aprobar retiro - debitar saldo
                saldo_actual = obtener_saldo(solicitud['user_id'])
                if saldo_actual >= solicitud['monto']:
                    nuevo_saldo = actualizar_saldo(solicitud['user_id'], -solicitud['monto'])
                    actualizar_solicitud(solicitud_id, "aprobada")
                    
                    # Notificar al usuario
                    try:
                        await context.bot.send_message(
                            chat_id=solicitud['user_id'],
                            text=f"✅ Tu retiro de {solicitud['monto']} CUP ha sido aprobado.\nNuevo saldo: {nuevo_saldo:.2f} CUP"
                        )
                    except Exception as e:
                        logger.error(f"Error notificando usuario: {e}")
                    
                    await query.edit_message_text(
                        f"✅ Retiro aprobado.\nUsuario: {solicitud['user_id']}\nMonto: {solicitud['monto']} CUP\nNuevo saldo: {nuevo_saldo:.2f} CUP"
                    )
                else:
                    actualizar_solicitud(solicitud_id, "rechazada", "Saldo insuficiente")
                    await query.edit_message_text(
                        f"❌ No se pudo aprobar el retiro. Saldo insuficiente.\n"
                        f"Saldo actual: {saldo_actual} CUP\nMonto solicitado: {solicitud['monto']} CUP"
                    )
        
        elif action == "rej":
            context.user_data['esperando_motivo'] = {
                'solicitud_id': solicitud_id,
                'tipo': tipo
            }
            await query.edit_message_text("📝 Envía el motivo del rechazo:")
    
    elif data.startswith("back_asset_"):
        asset_id = data.split("_")[2]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n\n"
            "Selecciona la moneda para operar:",
            reply_markup=get_currency_keyboard(asset_id)
        )
    
    elif data.startswith("back_trade_"):
        parts = data.split("_")
        asset_id = parts[2]
        currency = parts[3]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']}) en {currency}\n\n"
            "Selecciona el tipo de operación:",
            reply_markup=get_trade_keyboard(asset_id, currency)
        )

# Handler para recibir apalancamiento personalizado
async def recibir_apalancamiento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        leverage = float(text)
        if leverage <= 0:
            await update.message.reply_text("❌ El apalancamiento debe ser mayor a 0.")
            return
        
        context.user_data['operacion']['apalancamiento'] = leverage
        context.user_data['esperando'] = 'monto_riesgo'
        
        operacion = context.user_data['operacion']
        asset = ASSETS[operacion['asset']]
        
        await update.message.reply_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {'COMPRA' if operacion['operation_type'] == 'buy' else 'VENTA'}\n"
            f"Apalancamiento: x{leverage}\n\n"
            f"Envía el monto en CUP que deseas arriesgar (mínimo {MIN_RIESGO} CUP):",
            reply_markup=get_navigation_keyboard()
        )
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido.")

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
            await update.message.reply_text(
                f"❌ Saldo insuficiente. Tu saldo actual es {saldo:.2f} CUP."
            )
            return
        
        context.user_data['operacion']['monto_riesgo'] = monto_riesgo
        context.user_data['esperando'] = 'sl_tp'
        
        operacion = context.user_data['operacion']
        asset = ASSETS[operacion['asset']]
        
        await update.message.reply_text(
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Operación: {'COMPRA' if operacion['operation_type'] == 'buy' else 'VENTA'}\n"
            f"Apalancamiento: x{operacion['apalancamiento']}\n"
            f"Monto riesgo: {monto_riesgo} CUP\n\n"
            "Envía el Stop Loss y Take Profit separados por un guión (-).\n"
            "Ejemplo: 58000-62000",
            reply_markup=get_navigation_keyboard()
        )
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido.")

# Handler para recibir SL/TP
async def set_sl_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        sl_price, tp_price = map(float, text.split('-'))
        
        operacion = context.user_data['operacion']
        asset_id = operacion['asset']
        operation_type = operacion['operation_type']
        leverage = operacion['apalancamiento']
        monto_riesgo = operacion['monto_riesgo']
        
        # Obtener precio actual
        current_price = get_current_price(asset_id, operacion['currency'])
        
        # Validar SL/TP según el tipo de operación
        if operation_type == "buy":
            if sl_price >= current_price or tp_price <= current_price:
                await update.message.reply_text(
                    "❌ Para operaciones de COMPRA:\n"
                    "• El Stop Loss debe ser MENOR que el precio actual\n"
                    "• El Take Profit debe ser MAYOR que el precio actual"
                )
                return
        else:  # sell
            if sl_price <= current_price or tp_price >= current_price:
                await update.message.reply_text(
                    "❌ Para operaciones de VENTA:\n"
                    "• El Stop Loss debe ser MAYOR que el precio actual\n"
                    "• El Take Profit debe ser MENOR que el precio actual"
                )
                return
        
        # Calcular SL máximo permitido
        max_sl_price, max_pips = calcular_max_sl(
            monto_riesgo, asset_id, current_price, operation_type, leverage, CUP_RATE
        )
        
        # Validar que el SL no exceda el riesgo máximo
        if (operation_type == "buy" and sl_price > max_sl_price) or \
           (operation_type == "sell" and sl_price < max_sl_price):
            await update.message.reply_text(
                f"❌ Stop Loss excede el riesgo máximo permitido.\n"
                f"SL máximo: {max_sl_price:.2f}\n"
                f"Pips máximos de riesgo: {max_pips:.2f}\n\n"
                f"Por favor, ajusta tu Stop Loss o reduce el monto de riesgo."
            )
            return
        
        # Guardar la operación en la base de datos
        try:
            operation_data = {
                'user_id': user_id,
                'asset': asset_id,
                'currency': operacion['currency'],
                'operation_type': operation_type,
                'entry_price': current_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'apalancamiento': leverage,
                'monto_riesgo': monto_riesgo,
                'status': 'pendiente',
                'entry_time': datetime.now(timezone.utc).isoformat()
            }
            
            response = supabase.table('operations').insert(operation_data).execute()
            operation_id = response.data[0]['id']
            
            asset = ASSETS[asset_id]
            await update.message.reply_text(
                f"✅ Operación registrada exitosamente!\n\n"
                f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"Tipo: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n"
                f"Precio entrada: {current_price}\n"
                f"Stop Loss: {sl_price}\n"
                f"Take Profit: {tp_price}\n"
                f"Apalancamiento: x{leverage}\n"
                f"Monto riesgo: {monto_riesgo} CUP\n\n"
                f"ID de operación: {operation_id}",
                reply_markup=get_main_keyboard()
            )
            
            # Limpiar datos temporales
            context.user_data.pop('operacion', None)
            context.user_data.pop('esperando', None)
            
        except Exception as e:
            logger.error(f"Error guardando operación: {e}")
            await update.message.reply_text(
                "❌ Error al guardar la operación. Intenta nuevamente.",
                reply_markup=get_main_keyboard()
            )
            
    except ValueError:
        await update.message.reply_text(
            "❌ Formato incorrecto. Usa: precio_sl-precio_tp\nEjemplo: 58000-62000"
        )

# Handler para recibir montos de depósito/retiro
async def recibir_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    try:
        monto = float(text)
        estado_actual = context.user_data.get('esperando')
        
        if estado_actual == 'monto_deposito':
            if monto < MIN_DEPOSITO:
                await update.message.reply_text(
                    f"❌ El monto mínimo para depósito es {MIN_DEPOSITO} CUP."
                )
                return
            
            context.user_data['solicitud'] = {
                'tipo': 'deposito',
                'monto': monto
            }
            context.user_data['esperando'] = 'comprobante_deposito'
            
            await update.message.reply_text(
                f"💵 Monto a depositar: {monto} CUP\n\n"
                "📎 Ahora envía una foto del comprobante de transferencia.",
                reply_markup=get_navigation_keyboard()
            )
            
        elif estado_actual == 'monto_retiro':
            saldo = obtener_saldo(user_id)
            if monto < MIN_RETIRO:
                await update.message.reply_text(
                    f"❌ El monto mínimo para retiro es {MIN_RETIRO} CUP."
                )
                return
            
            if monto > saldo:
                await update.message.reply_text(
                    f"❌ Saldo insuficiente. Tu saldo actual es {saldo:.2f} CUP."
                )
                return
            
            context.user_data['solicitud'] = {
                'tipo': 'retiro',
                'monto': monto
            }
            context.user_data['esperando'] = 'datos_retiro'
            
            await update.message.reply_text(
                f"💵 Monto a retirar: {monto} CUP\n\n"
                "Envía los datos de retiro en el formato:\n"
                "número_tarjeta-número_teléfono\n\n"
                "Ejemplo: 1234567890123456-5351234567",
                reply_markup=get_navigation_keyboard()
            )
            
    except ValueError:
        await update.message.reply_text("❌ Por favor, envía un número válido.")

# Handler para recibir comprobantes y datos de retiro
async def recibir_datos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    user = update.message.from_user
    username = f"@{user.username}" if user.username else "Sin username"
    solicitud = context.user_data.get('solicitud', {})
    tipo = solicitud.get('tipo')
    monto = solicitud.get('monto')
    
    if tipo == 'deposito':
        # Para depósitos, esperamos una foto o texto como comprobante
        if update.message.photo:
            # Es una foto
            file_id = update.message.photo[-1].file_id
            datos = f"Comprobante: {file_id}"
        else:
            # Es texto
            datos = update.message.text
        
        # Crear solicitud de depósito
        solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
        
        await update.message.reply_text(
            "✅ Comprobante recibido. Tu solicitud de depósito ha sido enviada para revisión.",
            reply_markup=get_main_keyboard()
        )
        
        # Enviar notificación al admin
        message = (
            f"📥 Nueva solicitud de {tipo.upper()}\n"
            f"👤 Usuario: {username} (ID: {user_id})\n"
            f"💵 Monto: {monto} CUP\n"
            f"📋 Datos: {datos}\n"
            f"🆔 ID: {solicitud_id}"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=message,
            reply_markup=get_admin_keyboard(solicitud_id, tipo)
        )
        
        # Limpiar estado
        context.user_data.clear()
        
    elif tipo == 'retiro':
        # Para retiros, el texto contiene tarjeta y teléfono
        datos = update.message.text
        
        try:
            # Validar formato: tarjeta-teléfono
            card_number, phone_number = datos.split('-')
            
            # Validar que sean números
            if not (card_number.isdigit() and phone_number.isdigit()):
                await update.message.reply_text(
                    "❌ Formato incorrecto. Ambos valores deben ser numéricos.\n"
                    "Usa: número_tarjeta-número_teléfono"
                )
                return
            
            # Validar longitudes mínimas
            if len(card_number) < 8 or len(phone_number) < 8:
                await update.message.reply_text(
                    "❌ Número de tarjeta o teléfono inválido. Asegúrate de que sean correctos."
                )
                return
            
            # Crear solicitud de retiro
            datos_formateados = f"Tarjeta: {card_number}\nTeléfono: {phone_number}"
            solicitud_id = crear_solicitud(user_id, tipo, monto, datos_formateados)
            
            await update.message.reply_text(
                "✅ Solicitud de retiro enviada. Espera la confirmación de un administrador.",
                reply_markup=get_main_keyboard()
            )
            
            # Enviar notificación al admin
            message = (
                f"📤 Nueva solicitud de RETIRO\n"
                f"👤 Usuario: {username} (ID: {user_id})\n"
                f"💵 Monto: {monto} CUP\n"
                f"📋 Datos: {datos_formateados}"
            )
            
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=message,
                reply_markup=get_admin_keyboard(solicitud_id, tipo)
            )
            
            # Limpiar estado
            context.user_data.clear()
            
        except ValueError:
            await update.message.reply_text(
                "❌ Formato incorrecto. Usa: número_tarjeta-número_teléfono\n"
                "Ejemplo: 1234567890123456-5351234567"
            )

# Handler para recibir motivos de rechazo (admin)
async def recibir_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    motivo = update.message.text.strip()
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Solo los administradores pueden realizar esta acción.")
        return
    
    motivo_data = context.user_data.get('esperando_motivo')
    if not motivo_data:
        await update.message.reply_text("❌ No hay solicitud pendiente de rechazo.")
        return
    
    solicitud_id = motivo_data['solicitud_id']
    tipo = motivo_data['tipo']
    
    # Actualizar solicitud como rechazada
    if actualizar_solicitud(solicitud_id, "rechazada", motivo):
        # Obtener información de la solicitud para notificar al usuario
        response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
        solicitud = response.data[0]
        
        # Notificar al usuario
        try:
            await context.bot.send_message(
                chat_id=solicitud['user_id'],
                text=f"❌ Tu solicitud de {tipo} ha sido rechazada.\nMotivo: {motivo}"
            )
        except Exception as e:
            logger.error(f"Error notificando usuario: {e}")
        
        await update.message.reply_text("✅ Solicitud rechazada y usuario notificado.")
    else:
        await update.message.reply_text("❌ Error al actualizar la solicitud.")
    
    # Limpiar estado
    context.user_data.pop('esperando_motivo', None)

# Función para comprobar operación
async def check_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, op_id: int):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    try:
        # Obtener información de la operación
        response = supabase.table('operations').select('*').eq('id', op_id).execute()
        operation = response.data[0]
        
        # Obtener precio actual
        current_price = get_current_price(operation['asset'], operation['currency'])
        
        # Verificar si se alcanzó SL o TP
        sl_hit = False
        tp_hit = False
        
        if operation['operation_type'] == 'buy':
            sl_hit = current_price <= operation['sl_price']
            tp_hit = current_price >= operation['tp_price']
        else:  # sell
            sl_hit = current_price >= operation['sl_price']
            tp_hit = current_price <= operation['tp_price']
        
        # Calcular ganancia/pérdida
        pips_movidos = calcular_pips_movidos(
            operation['entry_price'], 
            current_price, 
            operation['asset']
        )
        
        ganancia = calcular_ganancia_pips(
            pips_movidos, 
            operation['asset'], 
            CUP_RATE, 
            operation['apalancamiento']
        )
        
        if operation['operation_type'] == 'sell':
            ganancia = -ganancia
        
        # Determinar resultado
        resultado = ""
        if sl_hit:
            resultado = "perdida"
            ganancia = -operation['monto_riesgo']  # Pérdida total del monto de riesgo
        elif tp_hit:
            resultado = "ganancia"
        else:
            resultado = "cerrada"
        
        # Actualizar operación en la base de datos
        update_data = {
            'status': 'cerrada',
            'close_price': current_price,
            'close_time': datetime.now(timezone.utc).isoformat(),
            'profit_loss': ganancia,
            'result': resultado
        }
        
        supabase.table('operations').update(update_data).eq('id', op_id).execute()
        
        # Actualizar saldo si hay ganancia o pérdida
        if resultado in ["ganancia", "perdida"]:
            actualizar_saldo(user_id, ganancia)
        
        asset = ASSETS[operation['asset']]
        resultado_emoji = "🟢" if resultado == "ganancia" else "🔴" if resultado == "perdida" else "⚪"
        
        await query.edit_message_text(
            f"{resultado_emoji} Operación cerrada\n\n"
            f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"Resultado: {resultado.capitalize()}\n"
            f"Precio cierre: {current_price}\n"
            f"Ganancia/Pérdida: {ganancia:.2f} CUP\n\n"
            f"Precio entrada: {operation['entry_price']}\n"
            f"Stop Loss: {operation['sl_price']}\n"
            f"Take Profit: {operation['tp_price']}",
            reply_markup=get_operation_detail_keyboard(op_id, True)
        )
        
    except Exception as e:
        logger.error(f"Error cerrando operación: {e}")
        await query.edit_message_text(
            "❌ Error al cerrar la operación.",
            reply_markup=get_operation_detail_keyboard(op_id, False)
        )

# Comando para establecer saldo (solo admin)
async def set_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Comando solo disponible para el administrador.")
        return
    
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Uso: /setsaldo [user_id] [monto]")
        return
    
    try:
        target_user_id = context.args[0]
        monto = float(context.args[1])
        
        nuevo_saldo = actualizar_saldo(target_user_id, monto)
        await update.message.reply_text(
            f"✅ Saldo actualizado para usuario {target_user_id}.\nNuevo saldo: {nuevo_saldo:.2f} CUP"
        )
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.")
    except Exception as e:
        logger.error(f"Error estableciendo saldo: {e}")
        await update.message.reply_text("❌ Error al actualizar el saldo.")

# Comando para establecer ID de grupo
async def set_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede usar este comando.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /setgroupid [nuevo_group_id]")
        return
    
    nuevo_group_id = context.args[0]
    global GROUP_ID
    GROUP_ID = nuevo_group_id
    
    await update.message.reply_text(f"✅ ID de grupo actualizado a: {GROUP_ID}")

# Comando para obtener ID de chat
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    await update.message.reply_text(f"El ID de este chat es: `{chat_id}`", parse_mode="Markdown")

# Función para procesar selección de apalancamiento
async def process_leverage_selection(query, context, asset_id, currency, operation_type, leverage):
    asset = ASSETS[asset_id]
    price = get_current_price(asset_id, currency)
    
    context.user_data['operacion'] = {
        'asset': asset_id,
        'currency': currency,
        'operation_type': operation_type,
        'apalancamiento': leverage
    }
    context.user_data['esperando'] = 'monto_riesgo'
    
    await query.edit_message_text(
        f"{asset['emoji']} {asset['name']} ({asset['symbol']})\n"
        f"Operación: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n"
        f"Apalancamiento: x{leverage}\n"
        f"Precio actual: {price}\n\n"
        f"Envía el monto en CUP que deseas arriesgar (mínimo {MIN_RIESGO} CUP):",
        reply_markup=get_navigation_keyboard()
    )

# Función unificada para mensajes de texto
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    estado_actual = user_data.get('esperando', '')
    
    if estado_actual == 'monto_deposito' or estado_actual == 'monto_retiro':
        await recibir_monto(update, context)
    
    elif estado_actual == 'comprobante_deposito':
        await recibir_datos(update, context)
    
    elif estado_actual == 'datos_retiro':
        # Procesar datos de retiro (tarjeta y teléfono)
        try:
            card_number, phone_number = text.split('-')
            
            # Validar que sean números
            if not (card_number.isdigit() and phone_number.isdigit()):
                await update.message.reply_text(
                    "❌ Formato incorrecto. Ambos valores deben ser numéricos.\n"
                    "Usa: número_tarjeta-número_teléfono"
                )
                return
            
            # Validar longitudes mínimas
            if len(card_number) < 8 or len(phone_number) < 8:
                await update.message.reply_text(
                    "❌ Número de tarjeta o teléfono inválido. Asegúrate de que sean correctos."
                )
                return
            
            # Crear solicitud de retiro inmediatamente
            solicitud = user_data['solicitud']
            tipo = solicitud['tipo']
            monto = solicitud['monto']
            datos = f"Tarjeta: {card_number}\nTeléfono: {phone_number}"
            
            solicitud_id = crear_solicitud(user_id, tipo, monto, datos)
            
            await update.message.reply_text(
                "✅ Solicitud de retiro enviada. Espera la confirmación de un administrador.",
                reply_markup=get_main_keyboard()
            )
            
            # Enviar notificación al admin
            user = update.message.from_user
            username = f"@{user.username}" if user.username else user.first_name
            
            message = (
                f"📤 Nueva solicitud de RETIRO\n"
                f"👤 Usuario: {username} (ID: {user_id})\n"
                f"💵 Monto: {monto} CUP\n"
                f"📋 Datos: {datos}"
            )
            
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=message,
                reply_markup=get_admin_keyboard(solicitud_id, tipo)
            )
            
            # Limpiar estado
            user_data.clear()
            
        except ValueError:
            await update.message.reply_text(
                "❌ Formato incorrecto. Usa: número_tarjeta-número_teléfono\n"
                "Ejemplo: 1234567890123456-5351234567"
            )
    
    elif estado_actual == 'apalancamiento_personalizado':
        await recibir_apalancamiento(update, context)
    
    elif estado_actual == 'monto_riesgo':
        await recibir_monto_riesgo(update, context)
    
    elif estado_actual == 'sl_tp':
        await set_sl_tp(update, context)
    
    elif 'esperando_motivo' in user_data:
        await recibir_motivo(update, context)
    
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
    job_queue.run_repeating(keep_alive, interval=300, first=10)  # Cada 5 minutos
    
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
