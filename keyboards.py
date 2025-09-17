from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ASSETS, APALANCAMIENTOS
from database import obtener_operaciones_activas, obtener_historial_operaciones

# Teclados principales
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
    operations = obtener_operaciones_activas(user_id)
    
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
    operations = obtener_historial_operaciones(user_id)
    
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

def get_welcome_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Empezar a Operar", callback_data="start_trading")]])

def get_navigation_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Menú Principal", callback_data="back_main")],
        [InlineKeyboardButton("💳 Ver Balance", callback_data="balance")]
    ])

def get_confirmation_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data="confirm_trade"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel_trade")
    ]])
