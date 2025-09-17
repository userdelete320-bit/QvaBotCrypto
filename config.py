import os

# Configuración
TOKEN = os.getenv("8102571019:AAGgI6bQflrd8T9snd9kO4_Es7eQCg2cBmo")
ADMIN_ID = "5376388604"
COINCAP_API_KEY = "c0b9354ec2c2d06d6395519f432b056c06f6340b62b72de1cf71a44ed9c6a36e"
COINCAP_API_URL = "https://rest.coincap.io/v3"
MAX_DAILY_CHECKS = 80
MIN_DEPOSITO = 5000
MIN_RIESGO = 5000
MIN_RETIRO = 6500
CUP_RATE = 440
CONFIRMATION_NUMBER = "59190241"
CARD_NUMBER = "9227 0699 9532 8054"
GROUP_ID = os.getenv("GROUP_ID", "-1002479699968")

# Mapeo de activos
ASSETS = {
    "bitcoin": {"symbol": "BTC", "name": "Bitcoin", "coincap_id": "bitcoin", "emoji": "🪙"},
    "ethereum": {"symbol": "ETH", "name": "Ethereum", "coincap_id": "ethereum", "emoji": "🔶"},
    "binance-coin": {"symbol": "BNB", "name": "Binance Coin", "coincap_id": "binance-coin", "emoji": "💎"},
    "tether": {"symbol": "USDT", "name": "Tether", "coincap_id": "tether", "emoji": "🔗"},
    "dai": {"symbol": "DAI", "name": "Dai", "coincap_id": "dai", "emoji": "🏦"},
    "usd-coin": {"symbol": "USDC", "name": "USD Coin", "coincap_id": "usd-coin", "emoji": "💵"},
    "ripple": {"symbol": "XRP", "name": "Ripple", "coincap_id": "ripple", "emoji": "✳️"},
    "cardano": {"symbol": "ADA", "name": "Cardano", "coincap_id": "cardano", "emoji": "🃏"},
    "solana": {"symbol": "SOL", "name": "Solana", "coincap_id": "solana", "emoji": "☀️"},
    "dogecoin": {"symbol": "DOGE", "name": "Dogecoin", "coincap_id": "dogecoin", "emoji": "🐕"},
    "polkadot": {"symbol": "DOT", "name": "Polkadot", "coincap_id": "polkadot", "emoji": "🔴"},
    "litecoin": {"symbol": "LTC", "name": "Litecoin", "coincap_id": "litecoin", "emoji": "🔶"},
    "chainlink": {"symbol": "LINK", "name": "Chainlink", "coincap_id": "chainlink", "emoji": "🔗"},
    "bitcoin-cash": {"symbol": "BCH", "name": "Bitcoin Cash", "coincap_id": "bitcoin-cash", "emoji": "💰"}
}

# Valores de pip (de pip_calculator.py)
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

# Niveles de apalancamiento
APALANCAMIENTOS = [5, 10, 20, 50, 100]

# Configuración de Supabase
SUPABASE_URL = "https://xowsmpukhedukeoqcreb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhvd3NtcHVraGVkdWtlb3FjcmViIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ4MzkwNDEsImV4cCI6MjA3MDQxNTA0MX0.zy1rCXPfuNQ95Bk0ATTkdF6DGLB9DhG9EjaBr0v3c0M"
