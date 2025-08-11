import os
import logging
import requests
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

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")
COINCAP_API_KEY = "c0b9354ec2c2d06d6395519f432b056c06f6340b62b72de1cf71a44ed9c6a36e"
COINCAP_API_URL = "https://rest.coincap.io/v3"
MAX_DAILY_CHECKS = 10

# Mapeo de activos con emojis
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
    "dogecoin": {"symbol": "DOGE", "name": "Dogecoin", "coincap_id": "dogecoin", "emoji": "🐶"}
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

# Gestión de créditos
def check_credits(user_id):
    today = datetime.utcnow().date()
    try:
        response = supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today.isoformat()).execute()
        if response.data:
            count = response.data[0]["count"]
            return count < MAX_DAILY_CHECKS
        return True
    except Exception as e:
        logger.error(f"Error checking credits: {e}")
        return False

def log_credit_usage(user_id):
    today = datetime.utcnow().date().isoformat()
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

def get_credit_info(user_id):
    today = datetime.utcnow().date().isoformat()
    try:
        response = supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today).execute()
        if response.data:
            count = response.data[0]["count"]
            return count, MAX_DAILY_CHECKS - count
        return 0, MAX_DAILY_CHECKS
    except Exception as e:
        logger.error(f"Error getting credit info: {e}")
        return 0, MAX_DAILY_CHECKS

# Obtener precio actual
def get_current_price(asset_id, currency="USD"):
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
        
        if currency == "EUR":
            logger.info("Converting to EUR...")
            eur_response = requests.get(
                f"{COINCAP_API_URL}/rates?search=EUR", 
                headers=headers
            )
            if eur_response.status_code != 200:
                logger.error(f"EUR conversion error: {eur_response.status_code} - {eur_response.text}")
                return None
                
            eur_data = eur_response.json().get("data", [])
            if not eur_data:
                logger.error("EUR response missing 'data' field")
                return None
                
            eur_rate = None
            for rate in eur_data:
                if rate.get("symbol") == "EUR":
                    eur_rate = float(rate.get("rateUsd", 0))
                    break
                    
            if eur_rate is None:
                logger.error("EUR rate not found in response")
                return None
                
            logger.info(f"EUR conversion rate: {eur_rate}")
            
            if eur_rate == 0:
                logger.error("EUR rate is zero, division error")
                return None
                
            return usd_price / eur_rate
        else:
            return usd_price
            
    except Exception as e:
        logger.exception(f"EXCEPTION in get_current_price: {e}")
        return None

# Obtener datos históricos
def get_historical_prices(asset_id, start_time, end_time, interval="m1"):
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
def analyze_price_history(price_history, entry_price, sl_price, tp_price, operation_type):
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

# Generar teclados
def get_main_keyboard():
    buttons = []
    for asset_id, data in ASSETS.items():
        buttons.append([InlineKeyboardButton(f"{data['emoji']} {data['symbol']}", callback_data=f"asset_{asset_id}")])
    buttons.append([InlineKeyboardButton("📊 Operaciones Activas", callback_data="operations")])
    buttons.append([InlineKeyboardButton("📜 Historial Operaciones", callback_data="history")])
    return InlineKeyboardMarkup(buttons)

def get_currency_keyboard(asset_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 USD", callback_data=f"currency_{asset_id}_USD")],
        [InlineKeyboardButton("💶 EUR", callback_data=f"currency_{asset_id}_EUR")],
        [InlineKeyboardButton("🔙 Atrás", callback_data="back_main")]
    ])

def get_trade_keyboard(asset_id, currency):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 COMPRAR", callback_data=f"trade_{asset_id}_{currency}_buy"),
            InlineKeyboardButton("🔴 VENDER", callback_data=f"trade_{asset_id}_{currency}_sell")
        ],
        [InlineKeyboardButton("🔙 Atrás", callback_data=f"back_asset_{asset_id}")]
    ])

def get_operations_keyboard(user_id):
    try:
        response = supabase.table('operations').select(
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
    
    buttons.append([InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def get_history_keyboard(user_id):
    try:
        # Obtener todas las operaciones cerradas con su resultado
        response = supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price, result, exit_price, exit_time"
        ).eq("user_id", user_id).eq("status", "cerrada").order("exit_time", desc=True).limit(10).execute()
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
    
    buttons.append([InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def get_operation_detail_keyboard(op_id, is_history=False):
    if is_history:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 A Historial", callback_data="history")]
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Cerrar Operación", callback_data=f"close_op_{op_id}"),
                InlineKeyboardButton("📈 Comprobar Resultado", callback_data=f"check_op_{op_id}")
            ],
            [InlineKeyboardButton("🔙 A Operaciones", callback_data="operations")]
        ])

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💰 *Sistema de Trading de Criptoactivos* 💰\nSelecciona un activo para operar:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    data = query.data
    
    if data == "back_main":
        await query.edit_message_text(
            "💰 *Sistema de Trading de Criptoactivos* 💰\nSelecciona un activo para operar:",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    elif data.startswith("asset_"):
        asset_id = data.split('_')[1]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"{asset['emoji']} Selecciona la moneda para {asset['name']}:",
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
            
        await query.edit_message_text(
            f"*{asset['emoji']} {asset['name']} ({asset['symbol']})*\n"
            f"💱 Precio actual: `{price:,.2f} {currency}`\n\n"
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
            operation_data = {
                "user_id": user_id,
                "asset": asset_id,
                "currency": currency,
                "operation_type": operation_type,
                "entry_price": price,
                "entry_time": datetime.utcnow().isoformat(),
                "status": "pendiente"  # Estado inicial
            }
            response = supabase.table('operations').insert(operation_data).execute()
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
            reply_markup=get_operations_keyboard(user_id)
        )
    
    elif data == "history":
        await query.edit_message_text(
            "📜 *Historial de Operaciones Cerradas* 📜",
            parse_mode="Markdown",
            reply_markup=get_history_keyboard(user_id))
    
    elif data.startswith("view_op_") or data.startswith("view_hist_"):
        is_history = data.startswith("view_hist_")
        op_id = data.split('_')[2]
        logger.info(f"Viewing operation: {op_id}")
        try:
            response = supabase.table('operations').select("*").eq("id", op_id).execute()
            op_data = response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fetching operation: {e}")
            op_data = None
        
        if op_data:
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
            
            message = (
                f"*Detalle de Operación* #{op_id}\n\n"
                f"• Activo: {asset['emoji']} {asset['name']} ({asset['symbol']})\n"
                f"• Tipo: {'🟢 COMPRA' if op_type == 'buy' else '🔴 VENTA'}\n"
                f"• Precio entrada: {price:.4f} {currency}\n"
                f"• Hora entrada: {entry_time}\n"
                f"• {sl_info}\n"
                f"• {tp_info}"
                f"{close_info}\n\n"
                f"Estado: {status_emoji}{result_info}"
            )
            
            await query.edit_message_text(
                message,
                parse_mode="Markdown",
                reply_markup=get_operation_detail_keyboard(op_id, is_history))
        else:
            await query.edit_message_text("⚠️ Operación no encontrada.")
    
    elif data.startswith("check_op_"):
        op_id = data.split('_')[2]
        logger.info(f"Checking operation: {op_id}")
        await check_operation(update, context, op_id)
    
    elif data.startswith("close_op_"):
        op_id = data.split('_')[2]
        logger.info(f"Closing operation: {op_id}")
        try:
            # Obtener precio actual para registrar el cierre
            op_data = supabase.table('operations').select("*").eq("id", op_id).execute().data[0]
            asset_id = op_data['asset']
            currency = op_data['currency']
            current_price = get_current_price(asset_id, currency)
            
            # Actualizar operación como cerrada manualmente
            supabase.table('operations').update({
                "status": "cerrada",
                "result": "manual",
                "exit_price": current_price,
                "exit_time": datetime.utcnow().isoformat()
            }).eq("id", op_id).execute()
        except Exception as e:
            logger.error(f"Error closing operation: {e}")
            await query.edit_message_text("⚠️ Error al cerrar la operación.")
            return
        
        await query.edit_message_text(
            f"✅ *Operación #{op_id} cerrada exitosamente!*\n"
            f"• Precio de cierre: {current_price:.4f} {currency}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    elif data.startswith("back_asset_"):
        asset_id = data.split('_')[2]
        asset = ASSETS[asset_id]
        await query.edit_message_text(
            f"{asset['emoji']} Selecciona la moneda para {asset['name']}:",
            reply_markup=get_currency_keyboard(asset_id))
        

# Handler para recibir SL/TP
async def set_sl_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    logger.info(f"Received SL/TP from user {user_id}: {text}")
    
    if 'pending_operation' not in context.user_data:
        await update.message.reply_text("No hay operaciones pendientes de configuración")
        return
    
    op_data = context.user_data['pending_operation']
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
        supabase.table('operations').update({
            "stop_loss": sl_price,
            "take_profit": tp_price
        }).eq("id", op_data['id']).execute()
        
        await update.message.reply_text(
            f"✅ *Stop Loss y Take Profit configurados!*\n\n"
            f"• Activo: {asset['emoji']} {asset['name']} ({asset['symbol']})\n"
            f"• 🛑 Stop Loss: {sl_price:.4f} {currency}\n"
            f"• 🎯 Take Profit: {tp_price:.4f} {currency}\n\n"
            f"Operación lista para monitoreo.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        del context.user_data['pending_operation']
    except Exception as e:
        logger.error(f"Error setting SL/TP: {e}")
        await update.message.reply_text("⚠️ Error interno al configurar SL/TP.")

# Función para comprobar operación
async def check_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, op_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    if not check_credits(user_id):
        await query.edit_message_text(
            "⚠️ Has alcanzado tu límite diario de consultas. Inténtalo de nuevo mañana.",
            reply_markup=get_operation_detail_keyboard(op_id, False))
        return
    
    try:
        response = supabase.table('operations').select("*").eq("id", op_id).execute()
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
    
    # Convertir a UTC para evitar problemas de zona horaria
    start_time = datetime.fromisoformat(op_data['entry_time']).astimezone(timezone.utc)
    end_time = datetime.utcnow().replace(tzinfo=timezone.utc)
    
    # Para debugging: usar periodo más corto si es necesario
    if (end_time - start_time) > timedelta(hours=24):
        start_time = end_time - timedelta(hours=24)
        logger.info(f"Adjusted start time to last 24 hours for efficiency")
    
    logger.info(f"Getting history from {start_time} to {end_time}")
    price_history = get_historical_prices(op_data['asset'], start_time, end_time, interval="m1")
    if not price_history:
        await query.edit_message_text("⚠️ Error al obtener datos históricos. Inténtalo más tarde.")
        return
    
    result, touch_time = analyze_price_history(
        price_history,
        op_data['entry_price'],
        op_data['stop_loss'],
        op_data['take_profit'],
        op_data['operation_type']
    )
    
    log_credit_usage(user_id)
    
    asset_info = ASSETS[op_data['asset']]
    symbol = asset_info['symbol']
    currency = op_data['currency']
    entry_price = op_data['entry_price']
    
    # Obtener precio actual para mostrar
    current_price = get_current_price(op_data['asset'], op_data['currency'])
    current_price_info = f"💰 Precio actual: {current_price:.4f} {currency}\n" if current_price else ""
    
    # Emoji de tendencia
    trend_emoji = ""
    if current_price:
        if current_price > entry_price:
            trend_emoji = "📈🟢"
        elif current_price < entry_price:
            trend_emoji = "📉🔴"
        else:
            trend_emoji = "➖⚪"
    
    if result == "SL":
        message = (
            f"⚠️ *STOP LOSS ACTIVADO* ⚠️\n\n"
            f"• Operación #{op_id} ({asset_info['emoji']} {symbol})\n"
            f"• Tipo: {'COMPRA' if op_data['operation_type'] == 'buy' else 'VENTA'}\n"
            f"• Precio entrada: {entry_price:.4f} {currency}\n"
            f"• 🛑 Stop Loss: {op_data['stop_loss']:.4f} {currency}\n"
            f"• Tocado el: {touch_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{current_price_info}"
            f"🏆 Resultado: ❌ PERDIDA {trend_emoji}"
        )
        supabase.table('operations').update({
            "status": "cerrada",
            "result": "loss",
            "exit_price": op_data['stop_loss'],
            "exit_time": touch_time.isoformat()
        }).eq("id", op_id).execute()
        
    elif result == "TP":
        message = (
            f"🎯 *TAKE PROFIT ACTIVADO* 🎯\n\n"
            f"• Operación #{op_id} ({asset_info['emoji']} {symbol})\n"
            f"• Tipo: {'COMPRA' if op_data['operation_type'] == 'buy' else 'VENTA'}\n"
            f"• Precio entrada: {entry_price:.4f} {currency}\n"
            f"• 🎯 Take Profit: {op_data['take_profit']:.4f} {currency}\n"
            f"• Tocado el: {touch_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{current_price_info}"
            f"🏆 Resultado: ✅ GANADA {trend_emoji}"
        )
        supabase.table('operations').update({
            "status": "cerrada",
            "result": "profit",
            "exit_price": op_data['take_profit'],
            "exit_time": touch_time.isoformat()
        }).execute()
        
    else:
        if current_price is None:
            await query.edit_message_text("⚠️ Error al obtener precio actual.")
            return
        
        price_diff = current_price - entry_price
        percentage = (price_diff / entry_price) * 100
        
        if op_data['operation_type'] == "sell":
            price_diff = -price_diff
            percentage = -percentage
            
        if price_diff > 0:
            arrow = "⬆️🟢"
            result_status = "GANANCIA"
        elif price_diff < 0:
            arrow = "⬇️🔴"
            result_status = "PÉRDIDA"
        else:
            arrow = "➖⚪"
            result_status = "SIN CAMBIO"
        
        message = (
            f"📊 *Estado Actual de la Operación* #{op_id}\n\n"
            f"• Activo: {asset_info['emoji']} {symbol}\n"
            f"• Tipo: {'VENTA' if op_data['operation_type'] == 'sell' else 'COMPRA'}\n"
            f"• Precio entrada: {entry_price:.4f} {currency}\n"
            f"• 💰 Precio actual: {current_price:.4f} {currency} {arrow}\n"
            f"• Diferencia: {price_diff:+.4f} {currency}\n"
            f"• Porcentaje: {percentage:+.2f}%\n\n"
            f"🏆 Resultado: {result_status}\n\n"
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, set_sl_tp))
    
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
