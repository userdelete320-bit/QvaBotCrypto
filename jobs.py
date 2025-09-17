import requests
import logging
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def keep_alive(context: ContextTypes.DEFAULT_TYPE):
    try:
        requests.get("https://google.com", timeout=5)
        logger.info("✅ Keep-alive ejecutado")
    except Exception as e:
        logger.warning(f"⚠️ Keep-alive falló: {e}")
