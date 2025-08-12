import os
import logging
import requests
import jwt
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from supabase import create_client, Client
from pip_calculator import calcular_valor_pip, calcular_ganancia_pips, calcular_pips_movidos

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = 5376388604  # Tu ID de administrador
COINCAP_API_KEY = "c0b9354ec2c2d06d6395519f432b056c06f6340b62b72de1cf71a44ed9c6a36e"
COINCAP_API_URL = "https://rest.coincap.io/v3"
MAX_DAILY_CHECKS = 80
JWT_SECRET = os.getenv("JWT_SECRET", "mE9fG7qX2sVpYtRwA1zB4cD5eF6gH7jK8lL9mN0oP1iQ2jR3kS4lT5mU6nV7oW8pX9")
MIN_DEPOSITO = 3000  # Mínimo de depósito en CUP
CUP_RATE = 440  # Tasa fija de USDT a CUP

# Mapeo de activos (solo criptomonedas)
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

# Configurar Supabase
SUPABASE_URL = "https://xowsmpukhedukeoqcreb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhvd3NtcHVraGVkdWtlb3FjcmViIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ4MzkwNDEsImV4cCI6MjA3MDQxNTA0MX0.zy1rCXPfuNQ95Bk0ATTkdF6DGLB9DhG9EjaBr0v3c0M"
supabase_anon = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Función para crear cliente Supabase autenticado con JWT
def get_auth_supabase(user_id: str) -> Client:
    # Crear token JWT
    payload = {
        "sub": user_id,
        "role": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return create_client(SUPABASE_URL, SUPABASE_KEY, {
        'global': {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }
    })

# Gestión de saldo
def obtener_saldo(user_id: str) -> float:
    try:
        auth_supabase = get_auth_supabase(user_id)
        response = auth_supabase.table('balance').select('saldo').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]['saldo']
        else:
            # Si no existe, crea un registro con saldo 0
            auth_supabase.table('balance').insert({'user_id': user_id, 'saldo': 0}).execute()
            return 0.0
    except Exception as e:
        logger.error(f"Error obteniendo saldo: {e}")
        return 0.0

def actualizar_saldo(user_id: str, monto: float) -> float:
    try:
        auth_supabase = get_auth_supabase(user_id)
        saldo_actual = obtener_saldo(user_id)
        nuevo_saldo = saldo_actual + monto
        
        auth_supabase.table('balance').update({'saldo': nuevo_saldo}).eq('user_id', user_id).execute()
        return nuevo_saldo
    except Exception as e:
        logger.error(f"Error actualizando saldo: {e}")
        return saldo_actual

# Crear solicitud de depósito/retiro
def crear_solicitud(user_id: str, tipo: str, monto: float, comprobante: str = None, datos: str = None) -> int:
    try:
        auth_supabase = get_auth_supabase(user_id)
        solicitud_data = {
            'user_id': user_id,
            'tipo': tipo,
            'monto': monto,
            'estado': 'pendiente',
            'fecha_solicitud': datetime.now(timezone.utc).isoformat()
        }
        if comprobante:
            solicitud_data['comprobante'] = comprobante
        if datos:
            solicitud_data['datos'] = datos

        response = auth_supabase.table('solicitudes').insert(solicitud_data).execute()
        return response.data[0]['id'] if response.data else None
    except Exception as e:
        logger.error(f"Error creando solicitud: {e}")
        return None

# Actualizar estado de solicitud
def actualizar_solicitud(solicitud_id: int, estado: str, motivo: str = None, admin_id: str = None) -> bool:
    try:
        auth_supabase = get_auth_supabase(admin_id) if admin_id else get_auth_supabase(ADMIN_ID)
        update_data = {
            'estado': estado,
            'fecha_resolucion': datetime.now(timezone.utc).isoformat()
        }
        if motivo:
            update_data['motivo_rechazo'] = motivo

        auth_supabase.table('solicitudes').update(update_data).eq('id', solicitud_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error actualizando solicitud: {e}")
        return False

# Teclado para admin
def get_admin_keyboard(solicitud_id: int, tipo: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aprobar", callback_data=f"apr_{tipo}_{solicitud_id}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"rej_{tipo}_{solicitud_id}")
        ]
    ])

# Teclado para acciones de balance
def get_balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ Depositar", callback_data="depositar"),
            InlineKeyboardButton("⬇️ Retirar", callback_data="retirar")
        ],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")]
    ])

# Gestión de créditos
def check_credits(user_id: str) -> bool:
    auth_supabase = get_auth_supabase(user_id)
    today = datetime.now(timezone.utc).date()
    try:
        response = auth_supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today.isoformat()).execute()
        if response.data:
            count = response.data[0]["count"]
            return count < MAX_DAILY_CHECKS
        return True
    except Exception as e:
        logger.error(f"Error checking credits: {e}")
        return False

def log_credit_usage(user_id: str) -> None:
    auth_supabase = get_auth_supabase(user_id)
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        response = auth_supabase.table("credit_usage").select("*").eq("user_id", user_id).eq("date", today).execute()
        if response.data:
            record = response.data[0]
            new_count = record["count"] + 1
            auth_supabase.table("credit_usage").update({"count": new_count}).eq("id", record["id"]).execute()
        else:
            auth_supabase.table("credit_usage").insert({
                "user_id": user_id,
                "date": today,
                "count": 1
            }).execute()
    except Exception as e:
        logger.error(f"Error logging credit usage: {e}")

def get_credit_info(user_id: str) -> tuple:
    auth_supabase = get_auth_supabase(user_id)
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        response = auth_supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today).execute()
        if response.data:
            count = response.data[0]["count"]
            return count, MAX_DAILY_CHECKS - count
        return 0, MAX_DAILY_CHECKS
    except Exception as e:
        logger.error(f"Error getting credit info: {e}")
        return 0, MAX_DAILY_CHECKS

# Obtener precio actual
def get_current_price(asset_id: str, currency: str = "USD") -> float:
    try:
        coincap_id = ASSETS[asset_id]["coincap_id"]
        headers = {
            "Authorization": f"Bearer {COINCAP_API_KEY}",
            "Accept-Encoding": "gzip"
        }
        url = f"{COINCAP_API_URL}/assets/{coincap_id}"
        
        logger.info(f"Requesting CoinCap price: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        logger.info(f"CoinCap response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"CoinCap API error: {response.status_code} - {response.text}")
            return None
        
        data = response.json().get("data", {})
        if not data:
            logger.error("CoinCap response missing 'data' field")
            return None
            
        usd_price = float(data.get("priceUsd", 0))
        logger.info(f"USD price for {coincap_id}: {usd_price}")
        return usd_price
            
    except Exception as e:
        logger.exception(f"EXCEPTION in get_current_price: {e}")
        return None

# Obtener datos históricos
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
        
        logger.info(f"Requesting historical data: {url}?interval={interval}&start={start_ms}&end={end_ms}")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        logger.info(f"Historical response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"History API error: {response.status_code} - {response.text}")
            return None
        
        data = response.json().get("data", [])
        if not data:
            logger.error("Historical response has no data")
            
        return data
    except Exception as e:
        logger.exception(f"EXCEPTION in get_historical_prices: {e}")
        return None

# Analizar si se tocó SL o TP
def analyze_price_history(price_history: list, entry_price: float, sl_price: float, tp_price: float, operation_type: str) -> tuple:
    if not price_history:
        logger.error("No price history to analyze")
        return None, None
        
    sl_touched = False
    tp_touched = False
    sl_time = None
    tp_time = None
    
    logger.info(f"Analyzing {len(price_history)} price points...")
    logger.info(f"Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}, Op: {operation_type}")
    
    for price_point in price_history:
        price = float(price_point.get("priceUsd", 0))
        timestamp = price_point.get("time", 0)
        
        if not price or not timestamp:
            continue
        
        if operation_type == "buy":
            if price <= sl_price and not sl_touched:
                sl_touched = True
                sl_time = datetime.fromtimestamp(timestamp/1000, timezone.utc)
                logger.info(f"SL touched at {price} - {sl_time}")
            if price >= tp_price and not tp_touched:
                tp_touched = True
                tp_time = datetime.fromtimestamp(timestamp/1000, timezone.utc)
                logger.info(f"TP touched at {price} - {tp_time}")
        
        elif operation_type == "sell":
            if price >= sl_price and not sl_touched:
                sl_touched = True
                sl_time = datetime.fromtimestamp(timestamp/1000, timezone.utc)
                logger.info(f"SL touched at {price} - {sl_time}")
            if price <= tp_price and not tp_touched:
                tp_touched = True
                tp_time = datetime.fromtimestamp(timestamp/1000, timezone.utc)
                logger.info(f"TP touched at {price} - {tp_time}")
        
        if sl_touched and tp_touched:
            if sl_time < tp_time:
                logger.info("SL triggered before TP")
                return "SL", sl_time
            else:
                logger.info("TP triggered before SL")
                return "TP", tp_time
    
    if sl_touched:
        logger.info("Only SL triggered")
        return "SL", sl_time
    if tp_touched:
        logger.info("Only TP triggered")
        return "TP", tp_time
    
    logger.info("Neither SL nor TP triggered")
    return None, None

# Generar teclados con mejor organización
def get_main_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    
    # Organizar activos en filas de 3
    asset_buttons = []
    for asset_id, data in ASSETS.items():
        asset_buttons.append(
            InlineKeyboardButton(f"{data['emoji']} {data['symbol']}", callback_data=f"asset_{asset_id}")
        )
    
    # Agrupar en filas de 3 botones
    for i in range(0, len(asset_buttons), 3):
        buttons.append(asset_buttons[i:i+3])
    
    # Botones de acciones
    buttons.append([
        InlineKeyboardButton("📊 Operaciones Activas", callback_data="operations"),
        InlineKeyboardButton("📜 Historial", callback_data="history"),
        InlineKeyboardButton("💳 Balance", callback_data="balance")
    ])
    
    return InlineKeyboardMarkup(buttons)

def get_currency_keyboard(asset_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 USD", callback_data=f"currency_{asset_id}_USD"),
        ],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")]
    ])

def get_trade_keyboard(asset_id: str, currency: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 COMPRAR", callback_data=f"trade_{asset_id}_{currency}_buy"),
            InlineKeyboardButton("🔴 VENDER", callback_data=f"trade_{asset_id}_{currency}_sell")
        ],
        [InlineKeyboardButton("🔙 Atrás", callback_data=f"back_asset_{asset_id}")]
    ])

def get_operations_keyboard(user_id: str) -> InlineKeyboardMarkup:
    auth_supabase = get_auth_supabase(user_id)
    try:
        response = auth_supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price"
        ).eq("user_id", user_id).eq("status", "pendiente").execute()
        operations = response.data
    except Exception as e:
        logger.error(f"Error fetching operations: {e}")
        operations = []
    
    buttons = []
    for op in operations:
        op_id = op['id']
        asset_id = op['asset']
        currency = op['currency']
        op_type = op['operation_type']
        price = op['entry_price']
        asset = ASSETS[asset_id]
        btn_text = f"{asset['emoji']} {asset['symbol']} {'🟢' if op_type == 'buy' else '🔴'} {price:.2f} {currency}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_op_{op_id}")])
    
    buttons.append([
        InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main"),
        InlineKeyboardButton("🔄 Actualizar", callback_data="operations")
    ])
    return InlineKeyboardMarkup(buttons)

def get_history_keyboard(user_id: str) -> InlineKeyboardMarkup:
    auth_supabase = get_auth_supabase(user_id)
    try:
        response = auth_supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price, result"
        ).eq("user_id", user_id).eq("status", "cerrada").order("entry_time", desc=True).limit(10).execute()
        operations = response.data
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        operations = []
    
    buttons = []
    for op in operations:
        op_id = op['id']
        asset_id = op['asset']
        currency = op['currency']
        op_type = op['operation_type']
        price = op['entry_price']
        result = op.get('result', '')
        asset = ASSETS[asset_id]
        
        # Determinar emoji según resultado
        if result == "profit":
            result_emoji = "✅"
        elif result == "loss":
            result_emoji = "❌"
        else:
            result_emoji = "🟣"  # Cerrada manualmente
        
        btn_text = f"{result_emoji} {asset['emoji']} {asset['symbol']} {'🟢' if op_type == 'buy' else '🔴'} {price:.2f} {currency}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_hist_{op_id}")])
    
    buttons.append([
        InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main"),
        InlineKeyboardButton("🔄 Actualizar", callback_data="history")
    ])
    return InlineKeyboardMarkup(buttons)

def get_operation_detail_keyboard(op_id: int, is_history: bool = False) -> InlineKeyboardMarkup:
    if is_history:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 A Historial", callback_data="history")]
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Cerrar Operación", callback_data=f"close_op_{op_id}"),
                InlineKeyboardButton("📈 Comprobar", callback_data=f"check_op_{op_id}")
            ],
            [
                InlineKeyboardButton("🛑 Modificar SL", callback_data=f"mod_sl_{op_id}"),
                InlineKeyboardButton("🎯 Modificar TP", callback_data=f"mod_tp_{op_id}")
            ],
            [InlineKeyboardButton("🔙 A Operaciones", callback_data="operations")]
        ])

# Nuevo teclado de bienvenida
def get_welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Empezar a Operar", callback_data="start_trading")]
    ])

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    welcome_message = (
        "🌟 *Bienvenido al Sistema de Trading QVA Crypto* 🌟\n\n"
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
    
    await update.message.reply_text(
        welcome_message,
        parse_mode="Markdown",
        reply_markup=get_welcome_keyboard()
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    data = query.data
    
    # Nuevo flujo de inicio
    if data == "start_trading":
        await query.edit_message_text(
            "💰 *Sistema de Trading de Criptomonedas* 💰\nSelecciona un activo:",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    
    if data == "back_main":
        await query.edit_message_text(
            "💰 *Sistema de Trading de Criptomonedas* 💰\nSelecciona un activo:",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    elif data.startswith("asset_"):
        asset_id = data.split('_')[1]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"Selecciona la moneda para {asset['name']}:",
            reply_markup=get_currency_keyboard(asset_id)
        )
    
    elif data.startswith("currency_"):
        _, asset_id, currency = data.split('_')
        asset = ASSETS[asset_id]
        logger.info(f"Getting price for {asset_id} in {currency}")
        price = get_current_price(asset_id, currency)
        
        if price is None:
            logger.error(f"Failed to get price for {asset_id}")
            await query.edit_message_text("⚠️ Error al obtener precio. Intenta nuevamente.")
            return
            
        # Calcular valor de pip en CUP
        valor_pip_cup = calcular_valor_pip(asset_id, CUP_RATE)
            
        await query.edit_message_text(
            f"*{asset['emoji']} {asset['name']} ({asset['symbol']})*\n"
            f"💱 Precio actual: `{price:,.2f} {currency}`\n"
            f"💰 Valor de 1 pip: `{valor_pip_cup:.2f} CUP`\n\n"
            "Selecciona el tipo de operación:",
            parse_mode="Markdown",
            reply_markup=get_trade_keyboard(asset_id, currency)
        )
    
    elif data.startswith("trade_"):
        _, asset_id, currency, operation_type = data.split('_')
        asset = ASSETS[asset_id]
        logger.info(f"Starting trade: {asset_id} {currency} {operation_type}")
        price = get_current_price(asset_id, currency)
        
        if price is None:
            logger.error(f"Price check failed for trade start")
            await query.edit_message_text("⚠️ Error al obtener precio. Intenta nuevamente.")
            return
        
        try:
            auth_supabase = get_auth_supabase(user_id)
            operation_data = {
                "user_id": user_id,
                "asset": asset_id,
                "currency": currency,
                "operation_type": operation_type,
                "entry_price": price,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "status": "pendiente"
            }
            response = auth_supabase.table('operations').insert(operation_data).execute()
            if response.data:
                op_id = response.data[0]['id']
                context.user_data['pending_operation'] = {
                    'id': op_id,
                    'asset_id': asset_id,
                    'currency': currency,
                    'operation_type': operation_type,
                    'entry_price': price
                }
                logger.info(f"Operation saved: ID {op_id}")
            else:
                raise Exception("No data in response")
        except Exception as e:
            logger.error(f"Error saving operation: {e}")
            await query.edit_message_text("⚠️ Error al guardar la operación. Intenta nuevamente.")
            return
        
        await query.edit_message_text(
            f"✅ *Operación registrada exitosamente!*\n\n"
            f"• Activo: {asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"• Tipo: {'🟢 COMPRA' if operation_type == 'buy' else '🔴 VENTA'}\n"
            f"• Precio: {price:.2f} {currency}\n\n"
            f"Ahora, por favor establece el Stop Loss (SL) y Take Profit (TP).\n\n"
            f"Envía el mensaje en el formato:\n"
            f"SL [precio]\n"
            f"TP [precio]\n\n"
            f"Ejemplo:\n"
            f"SL {price*0.95:.2f}\n"
            f"TP {price*1.05:.2f}",
            parse_mode="Markdown"
        )
    
    elif data == "operations":
        await query.edit_message_text(
            "📊 *Tus Operaciones Activas* 📊",
            parse_mode="Markdown",
            reply_markup=get_operations_keyboard(user_id))
    
    elif data == "history":
        await query.edit_message_text(
            "📜 *Historial de Operaciones Cerradas* 📜",
            parse_mode="Markdown",
            reply_markup=get_history_keyboard(user_id))
    
    elif data == "balance":
        saldo = obtener_saldo(user_id)
        await query.edit_message_text(
            f"💳 *Tu Saldo Actual*: `{saldo:.2f} CUP`\n\n"
            "Selecciona una opción:",
            parse_mode="Markdown",
            reply_markup=get_balance_keyboard()
        )
    
    elif data == "depositar":
        context.user_data['solicitud'] = {'tipo': 'deposito'}
        await query.edit_message_text(
            "💸 *Depósito*\n\n"
            f"Por favor, ingresa el monto a depositar (mínimo {MIN_DEPOSITO} CUP):",
            parse_mode="Markdown"
        )
    
    elif data == "retirar":
        saldo = obtener_saldo(user_id)
        if saldo <= 0:
            await query.edit_message_text(
                "⚠️ No tienes saldo disponible para retirar.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Atrás", callback_data="balance")]])
            )
            return
        context.user_data['solicitud'] = {'tipo': 'retiro'}
        await query.edit_message_text(
            "💸 *Retiro*\n\n"
            "Por favor, ingresa el monto a retirar:",
            parse_mode="Markdown"
        )
    
    elif data.startswith("view_op_") or data.startswith("view_hist_"):
        is_history = data.startswith("view_hist_")
        op_id = data.split('_')[2]
        logger.info(f"Viewing operation: {op_id}")
        try:
            auth_supabase = get_auth_supabase(user_id)
            response = auth_supabase.table('operations').select("*").eq("id", op_id).execute()
            op_data = response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fetching operation: {e}")
            op_data = None
        
        if not op_data or op_data['status'] == 'cerrada':
            await query.edit_message_text("⚠️ Operación no encontrada o ya cerrada.")
            return
            
        # Verificar que la operación pertenece al usuario
        if op_data['user_id'] != user_id:
            await query.edit_message_text("⚠️ No tienes permiso para ver esta operación")
            return
            
        asset_id = op_data['asset']
        currency = op_data['currency']
        op_type = op_data['operation_type']
        price = op_data['entry_price']
        entry_time = datetime.fromisoformat(op_data['entry_time']).strftime("%Y-%m-%d %H:%M:%S")
        asset = ASSETS[asset_id]
        
        sl_info = f"🛑 SL: {op_data['stop_loss']:.4f}" if op_data.get('stop_loss') else "🛑 SL: No establecido"
        tp_info = f"🎯 TP: {op_data['take_profit']:.4f}" if op_data.get('take_profit') else "🎯 TP: No establecido"
        
        status = op_data.get('status', 'pendiente')
        status_emoji = "🟡 PENDIENTE" if status == "pendiente" else "🔴 CERRADA"
        
        # Información de cierre
        close_info = ""
        if 'exit_price' in op_data and op_data['exit_price']:
            close_info = f"\n• Precio salida: {op_data['exit_price']:.4f} {currency}"
        
        if 'exit_time' in op_data and op_data['exit_time']:
            close_time = datetime.fromisoformat(op_data['exit_time']).strftime("%Y-%m-%d %H:%M:%S")
            close_info += f"\n• Hora salida: {close_time}"
        
        # Información de resultado
        result_info = ""
        if op_data.get('result') == "profit":
            result_info = "\n🏆 Resultado: ✅ GANADA"
        elif op_data.get('result') == "loss":
            result_info = "\n🏆 Resultado: ❌ PERDIDA"
        elif op_data.get('result') == "manual":
            result_info = "\n🏆 Resultado: 🟣 CERRADA MANUALMENTE"
        
        # Si la operación está pendiente, mostrar monto riesgo
        monto_riesgo_info = ""
        if status == "pendiente" and op_data.get('monto_riesgo'):
            monto_riesgo_info = f"\n• Monto arriesgado: {op_data['monto_riesgo']:.2f} CUP"
        
        message = (
            f"*Detalle de Operación* #{op_id}\n\n"
            f"• Activo: {asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"• Tipo: {'🟢 COMPRA' if op_type == 'buy' else '🔴 VENTA'}\n"
            f"• Precio entrada: {price:.4f} {currency}\n"
            f"• Hora entrada: {entry_time}\n"
            f"• {sl_info}\n"
            f"• {tp_info}"
            f"{monto_riesgo_info}"
            f"{close_info}\n\n"
            f"Estado: {status_emoji}{result_info}"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=get_operation_detail_keyboard(op_id, is_history))
    
    elif data.startswith("check_op_"):
        op_id = data.split('_')[2]
        logger.info(f"Checking operation: {op_id}")
        await check_operation(update, context, op_id)
    
    elif data.startswith("close_op_"):
        op_id = data.split('_')[2]
        logger.info(f"Closing operation: {op_id}")
        try:
            auth_supabase = get_auth_supabase(user_id)
            # Obtener operación
            response = auth_supabase.table('operations').select("*").eq("id", op_id).execute()
            op_data = response.data[0] if response.data else None
            
            if not op_data:
                await query.edit_message_text("⚠️ Operación no encontrada.")
                return
                
            # Verificar propiedad
            if op_data['user_id'] != user_id:
                await query.edit_message_text("⚠️ No tienes permiso para cerrar esta operación.")
                return
                
            asset_id = op_data['asset']
            currency = op_data['currency']
            
            # Obtener precio actual
            current_price = get_current_price(asset_id, currency)
            if current_price is None:
                await query.edit_message_text("⚠️ Error al obtener precio actual.")
                return
            
            # Calcular pips movidos
            pips_movidos = calcular_pips_movidos(op_data['entry_price'], current_price, asset_id)
            # Calcular ganancia/pérdida en CUP
            cambio_cup = calcular_ganancia_pips(pips_movidos, asset_id, CUP_RATE)
            # Para ventas, la dirección es inversa
            if op_data['operation_type'] == "sell":
                cambio_cup = -cambio_cup
            
            # Actualizar operación como cerrada manualmente
            auth_supabase.table('operations').update({
                "status": "cerrada",
                "result": "manual",
                "exit_price": current_price,
                "exit_time": datetime.now(timezone.utc).isoformat()
            }).eq("id", op_id).execute()
            
            # Actualizar saldo del usuario
            actualizar_saldo(user_id, cambio_cup)
            
            await query.edit_message_text(
                f"✅ *Operación #{op_id} cerrada exitosamente!*\n"
                f"• Precio de cierre: {current_price:.4f} {currency}\n"
                f"• Pips movidos: {pips_movidos:.1f}\n"
                f"• {'Ganancia' if cambio_cup >= 0 else 'Pérdida'}: {abs(cambio_cup):.2f} CUP",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Error closing operation: {e}")
            await query.edit_message_text("⚠️ Error al cerrar la operación.")
    
    elif data.startswith("mod_sl_") or data.startswith("mod_tp_"):
        op_id = data.split('_')[2]
        mod_type = "SL" if "sl" in data else "TP"
        
        try:
            auth_supabase = get_auth_supabase(user_id)
            # Obtener operación
            response = auth_supabase.table('operations').select("*").eq("id", op_id).execute()
            op_data = response.data[0] if response.data else None
            
            if not op_data:
                await query.edit_message_text("⚠️ Operación no encontrada.")
                return
                
            # Verificar propiedad
            if op_data['user_id'] != user_id:
                await query.edit_message_text("⚠️ No tienes permiso para modificar esta operación.")
                return
                
            # Verificar que está pendiente
            if op_data['status'] != 'pendiente':
                await query.edit_message_text("⚠️ Solo puedes modificar operaciones activas.")
                return
                
            context.user_data['modifying'] = {
                'op_id': op_id,
                'type': mod_type
            }
            
            # Obtener precio actual para sugerencia
            current_price = get_current_price(op_data['asset'], op_data['currency'])
            asset = ASSETS[op_data['asset']]
            
            if current_price:
                if mod_type == "SL":
                    if op_data['operation_type'] == "buy":
                        suggestion = current_price * 0.98  # 2% debajo del precio actual
                    else:  # sell
                        suggestion = current_price * 1.02  # 2% encima del precio actual
                else:  # TP
                    if op_data['operation_type'] == "buy":
                        suggestion = current_price * 1.02  # 2% encima del precio actual
                    else:  # sell
                        suggestion = current_price * 0.98  # 2% debajo del precio actual
                    
                suggestion_msg = f"\nSugerencia: `{mod_type} {suggestion:.4f}`"
            else:
                suggestion_msg = ""
            
            await query.edit_message_text(
                f"✏️ *Modificando {mod_type} para {asset['name']}*\n\n"
                f"Envía el nuevo valor para el {mod_type}.\n"
                f"Formato: `{mod_type} [precio]`{suggestion_msg}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error preparing modification: {e}")
            await query.edit_message_text("⚠️ Error al preparar la modificación.")
    
    elif data.startswith("back_asset_"):
        asset_id = data.split('_')[2]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"Selecciona la moneda para {asset['name']}:",
            reply_markup=get_currency_keyboard(asset_id))

    # Manejar aprobaciones/rechazos del admin
    elif data.startswith("apr_") or data.startswith("rej_"):
        if user_id != ADMIN_ID:
            await query.answer("⚠️ Solo el administrador puede realizar esta acción", show_alert=True)
            return
            
        partes = data.split('_')
        accion = partes[0]  # apr o rej
        tipo = partes[1]    # deposito o retiro
        solicitud_id = int(partes[2])
        
        # Obtener la solicitud
        try:
            auth_supabase = get_auth_supabase(ADMIN_ID)
            response = auth_supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
            solicitud = response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error obteniendo solicitud: {e}")
            solicitud = None
        
        if not solicitud:
            await query.edit_message_text("⚠️ Solicitud no encontrada.")
            return
        
        if accion == 'apr':
            # Aprobar solicitud
            if tipo == 'deposito':
                # Actualizar saldo
                nuevo_saldo = actualizar_saldo(solicitud['user_id'], solicitud['monto'])
                estado = 'aprobado'
                mensaje_user = f"✅ Tu depósito de {solicitud['monto']:.2f} CUP ha sido aprobado. Nuevo saldo: {nuevo_saldo:.2f} CUP."
            else:  # retiro
                # Verificar que aún tenga saldo suficiente
                saldo_actual = obtener_saldo(solicitud['user_id'])
                if saldo_actual < solicitud['monto']:
                    mensaje_admin = "⚠️ El usuario ya no tiene saldo suficiente para este retiro."
                    await query.edit_message_text(mensaje_admin)
                    actualizar_solicitud(solicitud_id, 'rechazado', 'Saldo insuficiente')
                    
                    # Notificar al usuario
                    await context.bot.send_message(
                        chat_id=solicitud['user_id'],
                        text=f"❌ Tu retiro de {solicitud['monto']:.2f} CUP fue rechazado. Motivo: Saldo insuficiente."
                    )
                    return
                
                # Actualizar saldo
                nuevo_saldo = actualizar_saldo(solicitud['user_id'], -solicitud['monto'])
                estado = 'aprobado'
                mensaje_user = f"✅ Tu retiro de {solicitud['monto']:.2f} CUP ha sido aprobado. El dinero será transferido pronto."
            
            # Actualizar estado de solicitud
            actualizar_solicitud(solicitud_id, estado)
            
            # Notificar al usuario
            await context.bot.send_message(
                chat_id=solicitud['user_id'],
                text=mensaje_user
            )
            
            await query.edit_message_text(f"✅ Solicitud {solicitud_id} aprobada.")
            
        else:  # rej
            # Pedir motivo de rechazo
            context.user_data['rechazo'] = {
                'solicitud_id': solicitud_id,
                'tipo': tipo,
                'user_id': solicitud['user_id']
            }
            await query.edit_message_text("📝 Por favor, envía el motivo del rechazo:")

# Handler para recibir SL/TP iniciales
async def set_sl_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    logger.info(f"Received SL/TP from user {user_id}: {text}")
    
    if 'pending_operation' not in context.user_data:
        return
    
    op_data = context.user_data['pending_operation']
    op_id = op_data['id']
    
    # Verificar propiedad de la operación
    try:
        auth_supabase = get_auth_supabase(user_id)
        response = auth_supabase.table('operations').select('user_id, status').eq('id', op_id).execute()
        if not response.data:
            await update.message.reply_text("❌ Operación no encontrada")
            del context.user_data['pending_operation']
            return
            
        op_db = response.data[0]
        if op_db['user_id'] != user_id:
            await update.message.reply_text("❌ Operación no pertenece a este usuario")
            del context.user_data['pending_operation']
            return
            
        if op_db['status'] != 'pendiente':
            await update.message.reply_text("❌ Operación ya no está pendiente")
            del context.user_data['pending_operation']
            return
    except Exception as e:
        logger.error(f"Verificación de propiedad fallida: {e}")
        return
    
    asset_id = op_data['asset_id']
    currency = op_data['currency']
    operation_type = op_data['operation_type']
    entry_price = op_data['entry_price']
    asset = ASSETS[asset_id]
    
    lines = text.split('\n')
    if len(lines) < 2:
        await update.message.reply_text("Formato incorrecto. Por favor usa:\nSL [precio]\nTP [precio]")
        return
    
    sl_line = lines[0].strip().upper()
    tp_line = lines[1].strip().upper()
    
    if not sl_line.startswith("SL ") or not tp_line.startswith("TP "):
        await update.message.reply_text("Formato incorrecto. Por favor comienza con 'SL' y 'TP'.")
        return
    
    try:
        sl_price = float(sl_line[2:].strip())
        tp_price = float(tp_line[2:].strip())
    except ValueError:
        await update.message.reply_text("Precios inválidos. Asegúrate de que sean números.")
        return
    
    if operation_type == "buy":
        if sl_price >= entry_price:
            await update.message.reply_text(f"❌ Para COMPRA, el Stop Loss debe ser menor que el precio de entrada ({entry_price:.4f})")
            return
        if tp_price <= entry_price:
            await update.message.reply_text(f"❌ Para COMPRA, el Take Profit debe ser mayor que el precio de entrada ({entry_price:.4f})")
            return
    else:
        if sl_price <= entry_price:
            await update.message.reply_text(f"❌ Para VENTA, el Stop Loss debe ser mayor que el precio de entrada ({entry_price:.4f})")
            return
        if tp_price >= entry_price:
            await update.message.reply_text(f"❌ Para VENTA, el Take Profit debe ser menor que el precio de entrada ({entry_price:.4f})")
            return
    
    try:
        auth_supabase = get_auth_supabase(user_id)
        auth_supabase.table('operations').update({
            "stop_loss": sl_price,
            "take_profit": tp_price
        }).eq("id", op_id).execute()
        
        # Calcular pips entre entrada y SL/TP
        pips_to_sl = calcular_pips_movidos(entry_price, sl_price, asset_id)
        pips_to_tp = calcular_pips_movidos(entry_price, tp_price, asset_id)
        
        # Calcular valores en CUP
        sl_cup = calcular_ganancia_pips(pips_to_sl, asset_id, CUP_RATE)
        tp_cup = calcular_ganancia_pips(pips_to_tp, asset_id, CUP_RATE)
        
        await update.message.reply_text(
            f"✅ *Stop Loss y Take Profit configurados!*\n\n"
            f"• Activo: {asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"• 🛑 Stop Loss: {sl_price:.4f} {currency} ({pips_to_sl:.1f} pips = {sl_cup:.2f} CUP)\n"
            f"• 🎯 Take Profit: {tp_price:.4f} {currency} ({pips_to_tp:.1f} pips = {tp_cup:.2f} CUP)\n\n"
            f"Ahora, por favor ingresa el monto que deseas arriesgar en CUP:",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error setting SL/TP: {e}")
        await update.message.reply_text("⚠️ Error interno al configurar SL/TP.")

# Handler para recibir monto de riesgo
async def recibir_monto_riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    if 'pending_operation' not in context.user_data:
        return
    
    try:
        monto_riesgo = float(text)
        if monto_riesgo <= 0:
            await update.message.reply_text("⚠️ Monto inválido. Por favor ingresa un número positivo:")
            return
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Por favor ingresa un número:")
        return
    
    op_data = context.user_data['pending_operation']
    op_id = op_data['id']
    
    # Guardar el monto de riesgo en la operación
    try:
        auth_supabase = get_auth_supabase(user_id)
        auth_supabase.table('operations').update({
            "monto_riesgo": monto_riesgo
        }).eq("id", op_id).execute()
        
        # Guardar en contexto para uso posterior
        context.user_data['pending_operation']['monto_riesgo'] = monto_riesgo
        
        # Calcular valor de pip en CUP
        valor_pip_cup = calcular_valor_pip(op_data['asset_id'], CUP_RATE)
        
        await update.message.reply_text(
            f"✅ *Monto de riesgo configurado!*\n\n"
            f"• Monto arriesgado: {monto_riesgo:.2f} CUP\n"
            f"• Valor por pip: {valor_pip_cup:.2f} CUP\n"
            f"• Ganancia/pérdida por pip: {valor_pip_cup:.2f} CUP\n\n"
            f"Operación lista para monitoreo.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        del context.user_data['pending_operation']
    except Exception as e:
        logger.error(f"Error setting risk amount: {e}")
        await update.message.reply_text("⚠️ Error al guardar el monto de riesgo.")

# Handler para recibir montos de depósito/retiro
async def recibir_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    if 'solicitud' not in context.user_data:
        return
    
    solicitud = context.user_data['solicitud']
    tipo = solicitud['tipo']
    
    try:
        monto = float(text)
        if tipo == 'deposito' and monto < MIN_DEPOSITO:
            await update.message.reply_text(f"⚠️ El monto mínimo de depósito es {MIN_DEPOSITO} CUP. Intenta nuevamente:")
            return
        if tipo == 'retiro':
            saldo = obtener_saldo(user_id)
            if monto > saldo:
                await update.message.reply_text(f"⚠️ Saldo insuficiente. Tu saldo actual es: {saldo:.2f} CUP. Ingresa un monto válido:")
                return
            if monto <= 0:
                await update.message.reply_text("⚠️ Monto inválido. Ingresa un monto positivo:")
                return
        
        # Guardar el monto
        context.user_data['solicitud']['monto'] = monto
        
        if tipo == 'deposito':
            await update.message.reply_text(
                "📤 Por favor, envía la captura de pantalla del comprobante de depósito."
            )
        else:  # retiro
            await update.message.reply_text(
                "📤 Por favor, envía tus datos en el formato:\n\n"
                "Tarjeta: [número de tarjeta]\n"
                "Teléfono: [número de teléfono]"
            )
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Por favor ingresa un número:")

# Handler para recibir comprobantes y datos de retiro
async def recibir_datos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    solicitud = context.user_data.get('solicitud', {})
    tipo = solicitud.get('tipo')
    monto = solicitud.get('monto')
    
    if not tipo or not monto:
        await update.message.reply_text("⚠️ Error en el proceso. Por favor comienza nuevamente.")
        return
    
    if tipo == 'deposito' and update.message.photo:
        # Guardar la mejor calidad de foto (última en la lista)
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = file.file_path
        
        # Crear solicitud
        solicitud_id = crear_solicitud(user_id, 'deposito', monto, comprobante=file_path)
        
        if solicitud_id:
            # Notificar al admin
            keyboard = get_admin_keyboard(solicitud_id, 'deposito')
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=file_path,
                caption=f"📥 *Nueva solicitud de depósito*\n\n"
                        f"• ID Usuario: `{user_id}`\n"
                        f"• Monto: `{monto:.2f} CUP`\n"
                        f"• ID Solicitud: `{solicitud_id}`",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            await update.message.reply_text(
                "✅ Solicitud de depósito enviada. Espera la confirmación del administrador.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text("⚠️ Error al crear la solicitud. Intenta nuevamente.")
        
        del context.user_data['solicitud']
    
    elif tipo == 'retiro' and update.message.text:
        datos = update.message.text.strip()
        # Crear solicitud
        solicitud_id = crear_solicitud(user_id, 'retiro', monto, datos=datos)
        
        if solicitud_id:
            # Notificar al admin
            keyboard = get_admin_keyboard(solicitud_id, 'retiro')
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📤 *Nueva solicitud de retiro*\n\n"
                     f"• ID Usuario: `{user_id}`\n"
                     f"• Monto: `{monto:.2f} CUP`\n"
                     f"• Datos:\n`{datos}`\n"
                     f"• ID Solicitud: `{solicitud_id}`",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            await update.message.reply_text(
                "✅ Solicitud de retiro enviada. Espera la confirmación del administrador.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text("⚠️ Error al crear la solicitud. Intenta nuevamente.")
        
        del context.user_data['solicitud']

# Handler para recibir motivos de rechazo (admin)
async def recibir_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    motivo = update.message.text.strip()
    
    if user_id != ADMIN_ID or 'rechazo' not in context.user_data:
        return
    
    rechazo = context.user_data['rechazo']
    solicitud_id = rechazo['solicitud_id']
    tipo = rechazo['tipo']
    user_id_destino = rechazo['user_id']
    
    # Actualizar solicitud
    actualizar_solicitud(solicitud_id, 'rechazado', motivo)
    
    # Notificar al usuario
    tipo_texto = "depósito" if tipo == 'deposito' else "retiro"
    await context.bot.send_message(
        chat_id=user_id_destino,
        text=f"❌ Tu solicitud de {tipo_texto} fue rechazada. Motivo:\n\n{motivo}"
    )
    
    await update.message.reply_text("✅ Rechazo registrado y notificado al usuario.")
    del context.user_data['rechazo']

# Función para comprobar operación (con SL/TP visibles)
async def check_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, op_id: int):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    if not check_credits(user_id):
        await query.edit_message_text(
            "⚠️ Has alcanzado tu límite diario de consultas. Inténtalo de nuevo mañana.",
            reply_markup=get_operation_detail_keyboard(op_id, False))
        return
    
    try:
        auth_supabase = get_auth_supabase(user_id)
        response = auth_supabase.table('operations').select("*").eq("id", op_id).execute()
        op_data = response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error fetching operation: {e}")
        op_data = None
    
    if not op_data or op_data['status'] == 'cerrada':
        await query.edit_message_text("⚠️ Operación no encontrada o ya cerrada.")
        return
    
    if not op_data.get('stop_loss') or not op_data.get('take_profit'):
        await query.edit_message_text("⚠️ Esta operación no tiene SL/TP configurados.")
        return
    
    # Verificar propiedad
    if op_data['user_id'] != user_id:
        await query.edit_message_text("⚠️ No tienes permiso para comprobar esta operación.")
        return
    
    # Convertir a UTC para evitar problemas de zona horaria
    start_time = datetime.fromisoformat(op_data['entry_time']).astimezone(timezone.utc)
    end_time = datetime.now(timezone.utc)
    
    # Para debugging: usar periodo más corto si es necesario
    if (end_time - start_time) > timedelta(hours=24):
        start_time = end_time - timedelta(hours=24)
        logger.info(f"Adjusted start time to last 24 hours for efficiency")
    
    logger.info(f"Getting history from {start_time} to {end_time}")
    price_history = get_historical_prices(op_data['asset'], start_time, end_time, interval="m1")
    if not price_history:
        await query.edit_message_text("⚠️ Error al obtener datos históricos. Inténtalo más tarde.")
        return
    
    # Obtener precio actual para detección en tiempo real
    current_price = get_current_price(op_data['asset'], op_data['currency'])
    if current_price is None:
        await query.edit_message_text("⚠️ Error al obtener precio actual.")
        return
    
    # Primero verificar si el precio ACTUAL alcanza SL/TP
    operation_type = op_data['operation_type']
    sl_price = op_data['stop_loss']
    tp_price = op_data['take_profit']
    current_touch = None
    
    if operation_type == "buy":
        if current_price <= sl_price:
            current_touch = ("SL", datetime.now(timezone.utc))
            logger.info(f"Precio ACTUAL activó SL a {current_price}")
        elif current_price >= tp_price:
            current_touch = ("TP", datetime.now(timezone.utc))
            logger.info(f"Precio ACTUAL activó TP a {current_price}")
    else:  # sell
        if current_price >= sl_price:
            current_touch = ("SL", datetime.now(timezone.utc))
            logger.info(f"Precio ACTUAL activó SL a {current_price}")
        elif current_price <= tp_price:
            current_touch = ("TP", datetime.now(timezone.utc))
            logger.info(f"Precio ACTUAL activó TP a {current_price}")
    
    # Si no se activó con el precio actual, analizar histórico
    if current_touch:
        result, touch_time = current_touch
    else:
        result, touch_time = analyze_price_history(
            price_history,
            op_data['entry_price'],
            sl_price,
            tp_price,
            operation_type
        )
    
    log_credit_usage(user_id)
    
    asset_info = ASSETS[op_data['asset']]
    symbol = asset_info['symbol']
    currency = op_data['currency']
    entry_price = op_data['entry_price']
    
    # Calcular pips movidos desde la entrada hasta el precio actual
    pips_movidos = calcular_pips_movidos(entry_price, current_price, op_data['asset'])
    # Calcular ganancia/pérdida en CUP
    cambio_cup = calcular_ganancia_pips(pips_movidos, op_data['asset'], CUP_RATE)
    # Para ventas, la dirección es inversa
    if operation_type == "sell":
        cambio_cup = -cambio_cup
    
    # Emoji de tendencia
    trend_emoji = "📈🟢" if cambio_cup >= 0 else "📉🔴"
    
    # Calcular distancia a SL y TP
    if operation_type == "buy":
        to_sl = entry_price - sl_price
        to_tp = tp_price - entry_price
        current_to_sl = current_price - sl_price
        current_to_tp = tp_price - current_price
    else:  # sell
        to_sl = sl_price - entry_price
        to_tp = entry_price - tp_price
        current_to_sl = sl_price - current_price
        current_to_tp = current_price - tp_price
    
    # Calcular pips a SL y TP
    pips_to_sl = calcular_pips_movidos(entry_price, sl_price, op_data['asset'])
    pips_to_tp = calcular_pips_movidos(entry_price, tp_price, op_data['asset'])
    current_pips_to_sl = calcular_pips_movidos(current_price, sl_price, op_data['asset'])
    current_pips_to_tp = calcular_pips_movidos(current_price, tp_price, op_data['asset'])
    
    # Calcular porcentajes de avance hacia SL/TP
    sl_percentage = (current_pips_to_sl / pips_to_sl) * 100 if pips_to_sl != 0 else 0
    tp_percentage = (current_pips_to_tp / pips_to_tp) * 100 if pips_to_tp != 0 else 0
    
    # Determinar precio de salida
    exit_price = None
    if result == "SL":
        exit_price = sl_price
    elif result == "TP":
        exit_price = tp_price
    
    if result == "SL":
        # Calcular pérdida (pips hasta SL)
        pips_result = pips_to_sl
        perdida_cup = calcular_ganancia_pips(pips_result, op_data['asset'], CUP_RATE)
        # Para ventas, la dirección es inversa
        if operation_type == "sell":
            perdida_cup = -perdida_cup
        
        # Actualizar saldo
        actualizar_saldo(user_id, perdida_cup)
        
        # Actualizar operación como cerrada
        update_data = {
            "status": "cerrada",
            "result": "loss",
            "exit_price": exit_price,
            "exit_time": touch_time.isoformat()
        }
        auth_supabase = get_auth_supabase(user_id)
        auth_supabase.table('operations').update(update_data).eq("id", op_id).execute()
        
        message = (
            f"⚠️ *STOP LOSS ACTIVADO* ⚠️\n\n"
            f"• Operación #{op_id} ({asset_info['emoji']} {symbol})\n"
            f"• Tipo: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n"
            f"• Precio entrada: {entry_price:.4f}\n"
            f"• Precio salida: {exit_price:.4f}\n"
            f"• Pips movidos: {pips_result:.1f}\n"
            f"• Monto arriesgado: {op_data.get('monto_riesgo',0):.2f} CUP\n\n"
            f"🏆 Resultado: ❌ PÉRDIDA de {abs(perdida_cup):.2f} CUP"
        )
        
    elif result == "TP":
        # Calcular ganancia (pips hasta TP)
        pips_result = pips_to_tp
        ganancia_cup = calcular_ganancia_pips(pips_result, op_data['asset'], CUP_RATE) * 0.8  # 80% de ganancia
        # Para ventas, la dirección es inversa
        if operation_type == "sell":
            ganancia_cup = -ganancia_cup
        
        # Actualizar saldo
        actualizar_saldo(user_id, ganancia_cup)
        
        # Actualizar operación como cerrada
        update_data = {
            "status": "cerrada",
            "result": "profit",
            "exit_price": exit_price,
            "exit_time": touch_time.isoformat()
        }
        auth_supabase = get_auth_supabase(user_id)
        auth_supabase.table('operations').update(update_data).eq("id", op_id).execute()
        
        message = (
            f"🎯 *TAKE PROFIT ACTIVADO* 🎯\n\n"
            f"• Operación #{op_id} ({asset_info['emoji']} {symbol})\n"
            f"• Tipo: {'COMPRA' if operation_type == 'buy' else 'VENTA'}\n"
            f"• Precio entrada: {entry_price:.4f}\n"
            f"• Precio salida: {exit_price:.4f}\n"
            f"• Pips movidos: {pips_result:.1f}\n"
            f"• Monto arriesgado: {op_data.get('monto_riesgo',0):.2f} CUP\n\n"
            f"🏆 Resultado: ✅ GANANCIA de {abs(ganancia_cup):.2f} CUP"
        )
        
    else:
        # Mostrar SL y TP en el estado actual
        sl_tp_info = (
            f"• 🛑 Stop Loss: {sl_price:.4f} {currency}\n"
            f"   - Distancia: {current_to_sl:.4f} (queda {current_pips_to_sl:.1f} pips, {sl_percentage:.1f}%)\n"
            f"• 🎯 Take Profit: {tp_price:.4f} {currency}\n"
            f"   - Distancia: {current_to_tp:.4f} (queda {current_pips_to_tp:.1f} pips, {tp_percentage:.1f}%)\n"
        )
        
        message = (
            f"📊 *Estado Actual de la Operación* #{op_id}\n\n"
            f"• Activo: {asset_info['emoji']} {symbol}\n"
            f"• Tipo: {'VENTA' if operation_type == 'sell' else 'COMPRA'}\n"
            f"• Precio entrada: {entry_price:.4f} {currency}\n"
            f"• 💰 Precio actual: {current_price:.4f} {currency} {trend_emoji}\n"
            f"• Pips movidos: {pips_movidos:.1f}\n"
            f"• Cambio: {cambio_cup:+.2f} CUP\n"
            f"• Monto arriesgado: {op_data.get('monto_riesgo',0):.2f} CUP\n\n"
            f"{sl_tp_info}\n"
            f"ℹ️ No se ha alcanzado Stop Loss ni Take Profit."
        )
    
    used, remaining = get_credit_info(user_id)
    credit_info = f"\n\n📊 Consultas usadas hoy: {used}/{MAX_DAILY_CHECKS} ({remaining} restantes)"
    
    await query.edit_message_text(
        message + credit_info,
        parse_mode="Markdown",
        reply_markup=get_operation_detail_keyboard(op_id, False))
    

# Main con webhook para Render
def main():
    # Obtener configuración de Render
    PORT = int(os.environ.get('PORT', 10000))
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://qvabotcrypto.onrender.com')
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Agregar handlers en orden de prioridad
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_monto_riesgo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, set_sl_tp))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_monto))
    application.add_handler(MessageHandler(filters.PHOTO, recibir_datos))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_datos))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_motivo))
    
    logger.info("🤖 Iniciando Bot de Trading en modo Webhook")
    logger.info(f"🔗 URL del webhook: {WEBHOOK_URL}/{TOKEN}")
    logger.info(f"🔌 Escuchando en puerto: {PORT}")
    
    # Configurar webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
        cert=None,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
