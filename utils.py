import requests
from datetime import datetime, timedelta
from config import COINCAP_API_KEY, COINCAP_API_URL, ASSETS, PIP_VALUES, CUP_RATE
import logging

logger = logging.getLogger(__name__)

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

# Funciones de cálculo de pips (de pip_calculator.py)
def calcular_valor_pip(asset_id, cup_rate=CUP_RATE):
    """Calcula el valor de 1 pip en CUP para un activo"""
    pip_value_usd = PIP_VALUES.get(asset_id, 0.01)
    return pip_value_usd * cup_rate

def calcular_ganancia_pips(pips, asset_id, cup_rate=CUP_RATE, apalancamiento=1):
    """Calcula la ganancia en CUP para un movimiento de pips"""
    valor_pip = calcular_valor_pip(asset_id, cup_rate)
    return pips * valor_pip * apalancamiento

def calcular_pips_movidos(precio_inicial, precio_final, asset_id):
    """Calcula los pips movidos entre dos precios"""
    pip_value = PIP_VALUES.get(asset_id, 0.01)
    return abs(precio_final - precio_inicial) / pip_value

def calcular_max_sl(monto_riesgo, asset_id, entry_price, operation_type, leverage, cup_rate=CUP_RATE):
    valor_pip = calcular_valor_pip(asset_id, cup_rate) * leverage
    max_pips = monto_riesgo / valor_pip
    return max_pips

def analyze_price_history(price_history, entry_price, sl_price, tp_price, operation_type):
    if not price_history:
        return None, None
        
    max_price = max(price[1] for price in price_history)
    min_price = min(price[1] for price in price_history)
    
    if operation_type == "buy":
        if min_price <= sl_price:
            return "sl", min_price
        elif max_price >= tp_price:
            return "tp", max_price
    else:
        if max_price >= sl_price:
            return "sl", max_price
        elif min_price <= tp_price:
            return "tp", min_price
            
    return None, None
