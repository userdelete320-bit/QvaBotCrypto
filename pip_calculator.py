PIP_VALUES = {
    "bitcoin": 0.01,      # 1 pip = 0.01 USD
    "ethereum": 0.01,     # 1 pip = 0.01 USD
    "binance-coin": 0.01,
    "tether": 0.0001,     # 1 pip = 0.0001 USD
    "dai": 0.0001,
    "usd-coin": 0.0001,
    "ripple": 0.0001,
    "cardano": 0.0001,
    "solana": 0.01,
    "dogecoin": 0.000001, # 1 pip = 0.000001 USD
    "polkadot": 0.01,
    "litecoin": 0.01,
    "chainlink": 0.001,   # 1 pip = 0.001 USD
    "bitcoin-cash": 0.01
}

def calcular_valor_pip(asset_id, cup_rate):
    """Calcula el valor de 1 pip en CUP para un activo"""
    pip_value_usd = PIP_VALUES.get(asset_id, 0.01)
    return pip_value_usd * cup_rate

def calcular_ganancia_pips(pips, asset_id, cup_rate):
    """Calcula la ganancia en CUP para un movimiento de pips"""
    valor_pip = calcular_valor_pip(asset_id, cup_rate)
    return pips * valor_pip

def calcular_pips_movidos(precio_inicial, precio_final, asset_id):
    """Calcula los pips movidos entre dos precios"""
    pip_value = PIP_VALUES.get(asset_id, 0.01)
    return abs(precio_final - precio_inicial) / pip_value
