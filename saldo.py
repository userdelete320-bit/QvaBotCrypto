import os
import logging
from datetime import datetime
from supabase import create_client, Client
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Configuración
SUPABASE_URL = "https://xowsmpukhedukeoqcreb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhvd3NtcHVraGVkdWtlb3FjcmViIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ4MzkwNDEsImV4cCI6MjA3MDQxNTA0MX0.zy1rCXPfuNQ95Bk0ATTkdF6DGLB9DhG9EjaBr0v3c0M"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Obtener saldo del usuario
def obtener_saldo(user_id):
    try:
        response = supabase.table('balance').select('saldo').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]['saldo']
        else:
            # Si no existe, crea un registro con saldo 0
            supabase.table('balance').insert({'user_id': user_id, 'saldo': 0}).execute()
            return 0
    except Exception as e:
        logger.error(f"Error obteniendo saldo: {e}")
        return 0

# Crear solicitud de depósito/retiro
def crear_solicitud(user_id, tipo, monto, comprobante=None, datos=None):
    try:
        solicitud_data = {
            'user_id': user_id,
            'tipo': tipo,
            'monto': monto,
            'estado': 'pendiente',
            'fecha_solicitud': datetime.utcnow().isoformat()
        }
        if comprobante:
            solicitud_data['comprobante'] = comprobante
        if datos:
            solicitud_data['datos'] = datos

        response = supabase.table('solicitudes').insert(solicitud_data).execute()
        return response.data[0]['id'] if response.data else None
    except Exception as e:
        logger.error(f"Error creando solicitud: {e}")
        return None

# Actualizar saldo del usuario
def actualizar_saldo(user_id, monto):
    try:
        saldo_actual = obtener_saldo(user_id)
        nuevo_saldo = saldo_actual + monto
        
        supabase.table('balance').update({'saldo': nuevo_saldo}).eq('user_id', user_id).execute()
        return nuevo_saldo
    except Exception as e:
        logger.error(f"Error actualizando saldo: {e}")
        return None

# Obtener solicitudes pendientes
def obtener_solicitudes_pendientes():
    try:
        response = supabase.table('solicitudes').select('*').eq('estado', 'pendiente').execute()
        return response.data
    except Exception as e:
        logger.error(f"Error obteniendo solicitudes: {e}")
        return []

# Actualizar estado de solicitud
def actualizar_solicitud(solicitud_id, estado, motivo=None):
    try:
        update_data = {
            'estado': estado,
            'fecha_resolucion': datetime.utcnow().isoformat()
        }
        if motivo:
            update_data['motivo_rechazo'] = motivo

        supabase.table('solicitudes').update(update_data).eq('id', solicitud_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error actualizando solicitud: {e}")
        return False

# Teclado para admin
def get_admin_keyboard(solicitud_id, tipo):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aprobar", callback_data=f"apr_{tipo}_{solicitud_id}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"rej_{tipo}_{solicitud_id}")
        ]
    ])

# Teclado para acciones de balance
def get_balance_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ Depositar", callback_data="depositar"),
            InlineKeyboardButton("⬇️ Retirar", callback_data="retirar")
        ],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="back_main")]
    ])
