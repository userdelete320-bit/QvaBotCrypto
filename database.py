from supabase import create_client
from datetime import datetime, timezone
from config import SUPABASE_URL, SUPABASE_KEY, MAX_DAILY_CHECKS, MAX_RETRIES, RETRY_DELAY
import logging
import time

logger = logging.getLogger(__name__)

# Reintentos de conexión
def create_supabase_client():
    """Crear cliente de Supabase con manejo de errores"""
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Verificar conexión con una consulta simple
        client.table('balance').select('count').limit(1).execute()
        logger.info("Conexión a Supabase establecida correctamente")
        return client
    except Exception as e:
        logger.error(f"Error creando cliente de Supabase: {e}")
        return None

# Intentar crear el cliente con reintentos
supabase = None
for attempt in range(MAX_RETRIES):
    supabase = create_supabase_client()
    if supabase:
        break
    logger.warning(f"Intento {attempt + 1} de conexión fallido. Reintentando...")
    time.sleep(RETRY_DELAY)

if not supabase:
    logger.error("No se pudo establecer conexión con Supabase después de varios intentos")

def execute_with_retry(func, *args, **kwargs):
    """Ejecutar función con reintentos en caso de error de conexión"""
    for attempt in range(MAX_RETRIES):
        try:
            if not supabase:
                raise Exception("Cliente de Supabase no disponible")
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error en operación de base de datos (intento {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise e

# Funciones de saldo
def obtener_saldo(user_id: str) -> float:
    def _obtener_saldo():
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
    
    return execute_with_retry(_obtener_saldo)

def actualizar_saldo(user_id: str, monto: float) -> float:
    def _actualizar_saldo():
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
    
    return execute_with_retry(_actualizar_saldo)

# Funciones de solicitudes
def crear_solicitud(user_id: str, tipo: str, monto: float, comprobante: str = None, datos: str = None) -> int:
    def _crear_solicitud():
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
    
    return execute_with_retry(_crear_solicitud)

def obtener_solicitud(solicitud_id: int):
    def _obtener_solicitud():
        try:
            response = supabase.table('solicitudes').select('*').eq('id', solicitud_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error obteniendo solicitud: {e}")
            return None
    
    return execute_with_retry(_obtener_solicitud)

def actualizar_solicitud(solicitud_id: int, estado: str, motivo: str = None) -> bool:
    def _actualizar_solicitud():
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
    
    return execute_with_retry(_actualizar_solicitud)

def obtener_solicitudes_pendientes():
    def _obtener_solicitudes_pendientes():
        try:
            response = supabase.table('solicitudes').select('*').eq('estado', 'pendiente').execute()
            return response.data
        except Exception as e:
            logger.error(f"Error obteniendo solicitudes: {e}")
            return []
    
    return execute_with_retry(_obtener_solicitudes_pendientes)

# Gestión de créditos
def check_credits(user_id: str) -> bool:
    def _check_credits():
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            response = supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today).execute()
            if response.data:
                count = response.data[0]["count"]
                return count < MAX_DAILY_CHECKS
            return True
        except Exception as e:
            logger.error(f"Error checking credits: {e}")
            return True
    
    return execute_with_retry(_check_credits)

def log_credit_usage(user_id: str) -> None:
    def _log_credit_usage():
        try:
            today = datetime.now(timezone.utc).date().isoformat()
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
    
    execute_with_retry(_log_credit_usage)

def get_credit_info(user_id: str) -> tuple:
    def _get_credit_info():
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            response = supabase.table("credit_usage").select("count").eq("user_id", user_id).eq("date", today).execute()
            if response.data:
                count = response.data[0]["count"]
                return count, MAX_DAILY_CHECKS - count
            return 0, MAX_DAILY_CHECKS
        except Exception as e:
            logger.error(f"Error getting credit info: {e}")
            return 0, MAX_DAILY_CHECKS
    
    return execute_with_retry(_get_credit_info)

# Operaciones
def crear_operacion(operation_data: dict) -> int:
    def _crear_operacion():
        try:
            response = supabase.table('operations').insert(operation_data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error creando operación: {e}")
            return None
    
    return execute_with_retry(_crear_operacion)

def obtener_operacion(op_id: int):
    def _obtener_operacion():
        try:
            response = supabase.table('operations').select('*').eq('id', op_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error obteniendo operación: {e}")
            return None
    
    return execute_with_retry(_obtener_operacion)

def actualizar_operacion(op_id: int, update_data: dict) -> bool:
    def _actualizar_operacion():
        try:
            supabase.table('operations').update(update_data).eq('id', op_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error actualizando operación: {e}")
            return False
    
    return execute_with_retry(_actualizar_operacion)

def obtener_operaciones_activas(user_id: str):
    def _obtener_operaciones_activas():
        try:
            response = supabase.table('operations').select(
                "id, asset, currency, operation_type, entry_price, apalancamiento"
            ).eq("user_id", user_id).eq("status", "pendiente").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error obteniendo operaciones activas: {e}")
            return []
    
    return execute_with_retry(_obtener_operaciones_activas)

def obtener_historial_operaciones(user_id: str, limit: int = 10):
    def _obtener_historial_operaciones():
        try:
            response = supabase.table('operations').select(
                "id, asset, currency, operation_type, entry_price, result, apalancamiento, exit_price, result_amount, entry_time, exit_time"
            ).eq("user_id", user_id).eq("status", "cerrada").order("entry_time", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error obteniendo historial: {e}")
            return []
    
    return execute_with_retry(_obtener_historial_operaciones)
