from supabase import create_client
from datetime import datetime, timezone
from config import SUPABASE_URL, SUPABASE_KEY, MAX_DAILY_CHECKS
import logging

logger = logging.getLogger(__name__)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Funciones de saldo (de saldo.py mejoradas)
def obtener_saldo(user_id: str) -> float:
    try:
        response = supabase.table('balance').select('saldo').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]['saldo']
        else:
            # Si no existe, crea un registro con saldo 0
            supabase.table('balance').insert({'user_id': user_id, 'saldo': 0}).execute()
            return 0.0
    except Exception as e:
        logger.error(f"Error obteniendo saldo: {e}")
        return 0.0

def actualizar_saldo(user_id: str, monto: float) -> float:
    try:
        saldo_actual = obtener_saldo(user_id)
        nuevo_saldo = saldo_actual + monto
        
        response = supabase.table('balance').select('*').eq('user_id', user_id).execute()
        
        if response.data:
            supabase.table('balance').update({'saldo': nuevo_saldo}).eq('user_id', user_id).execute()
        else:
            supabase.table('balance').insert({'user_id': user_id, 'saldo': nuevo_saldo}).execute()
            
        return nuevo_saldo
    except Exception as e:
        logger.error(f"Error actualizando saldo: {e}")
        return saldo_actual

# Funciones de solicitudes (de saldo.py mejoradas)
def crear_solicitud(user_id: str, tipo: str, monto: float, comprobante: str = None, datos: str = None) -> int:
    try:
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

def obtener_solicitudes_pendientes():
    try:
        response = supabase.table('solicitudes').select('*').eq('estado', 'pendiente').execute()
        return response.data
    except Exception as e:
        logger.error(f"Error obteniendo solicitudes: {e}")
        return []

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

# Operaciones
def crear_operacion(operation_data: dict) -> int:
    try:
        response = supabase.table('operations').insert(operation_data).execute()
        return response.data[0]['id'] if response.data else None
    except Exception as e:
        logger.error(f"Error creando operación: {e}")
        return None

def obtener_operacion(op_id: int):
    try:
        response = supabase.table('operations').select('*').eq('id', op_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error obteniendo operación: {e}")
        return None

def actualizar_operacion(op_id: int, update_data: dict) -> bool:
    try:
        supabase.table('operations').update(update_data).eq('id', op_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error actualizando operación: {e}")
        return False

# database.py (agregar esta función)
def obtener_solicitud(solicitud_id: int):
    try:
        response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error obteniendo solicitud: {e}")
        return None

def obtener_operaciones_activas(user_id: str):
    try:
        response = supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price, apalancamiento"
        ).eq("user_id", user_id).eq("status", "pendiente").execute()
        return response.data
    except Exception as e:
        logger.error(f"Error obteniendo operaciones activas: {e}")
        return []

def obtener_historial_operaciones(user_id: str, limit: int = 10):
    try:
        response = supabase.table('operations').select(
            "id, asset, currency, operation_type, entry_price, result, apalancamiento, exit_price, result_amount, entry_time, exit_time"
        ).eq("user_id", user_id).eq("status", "cerrada").order("entry_time", desc=True).limit(limit).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error obteniendo historial: {e}")
        return []
