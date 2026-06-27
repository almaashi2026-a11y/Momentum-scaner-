"""
إرسال تنبيهات momentum breakout عبر Telegram bot.
"""

import logging

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_alert(bot_token: str, chat_id: str, result: dict) -> bool:
    """يرسل رسالة تنبيه منسقة عن رمز مؤكد momentum breakout."""
    symbol = result["symbol"]
    price = result["price"]
    rvol = result["rvol"]
    change_15min = result["price_change_15min_pct"]
    ema9 = result["ema9"]
    vwap = result["vwap"]

    message = (
        f"🚀 *تنبيه Momentum Breakout*\n\n"
        f"*الرمز:* `{symbol}`\n"
        f"*السعر الحالي:* ${price:.2f}\n"
        f"*التغيّر (15 دقيقة):* +{change_15min:.2f}%\n"
        f"*RVOL:* {rvol:.2f}x\n"
        f"*EMA9:* ${ema9:.4f} (أعلى من VWAP ${vwap:.4f})\n\n"
        f"⚠️ تذكير: تأكد من تحليلك الخاص قبل الدخول - هذا تنبيه آلي وليس نصيحة استثمارية."
    )

    url = TELEGRAM_API_BASE.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"تم إرسال تنبيه Telegram لـ {symbol}")
        return True
    except Exception as e:
        logger.error(f"فشل إرسال تنبيه Telegram لـ {symbol}: {e}")
        return False


def send_telegram_text(bot_token: str, chat_id: str, text: str) -> bool:
    """يرسل رسالة نصية عامة (مثل تنبيهات الأخطاء أو ملخص الدورة)."""
    url = TELEGRAM_API_BASE.format(token=bot_token)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"فشل إرسال رسالة Telegram: {e}")
        return False
