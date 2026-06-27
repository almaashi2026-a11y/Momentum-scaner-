"""
تخزين بسيط مبني على JSON (مع قفل ملف) لتتبع:
  - آخر مرة تم التنبيه فيها عن كل رمز (لمنع تكرار التنبيهات)
  - سجل آخر دورة سكان (للمراقبة عبر /status)

Render's free/starter tier disk قد يكون ephemeral عند إعادة النشر،
لكن يبقى ثابت بين دورات السكانر العادية أثناء تشغيل نفس الـ instance.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "/tmp/scanner_data")
ALERTS_FILE = os.path.join(DATA_DIR, "sent_alerts.json")
STATUS_FILE = os.path.join(DATA_DIR, "last_scan_status.json")

ALERT_COOLDOWN_MINUTES = 60

_lock = threading.Lock()


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str, default):
    _ensure_data_dir()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"فشل قراءة {path}: {e}")
        return default


def _save_json(path: str, data):
    _ensure_data_dir()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"فشل حفظ {path}: {e}")


def should_send_alert(symbol: str) -> bool:
    """يتحقق إذا كان يجب إرسال تنبيه عن هذا الرمز (لم يُرسل تنبيه له مؤخراً)."""
    with _lock:
        alerts = _load_json(ALERTS_FILE, {})
        last_sent_str = alerts.get(symbol)

        if not last_sent_str:
            return True

        last_sent = datetime.fromisoformat(last_sent_str)
        cooldown_until = last_sent + timedelta(minutes=ALERT_COOLDOWN_MINUTES)

        return datetime.now(timezone.utc) >= cooldown_until


def mark_alert_sent(symbol: str):
    """يسجل أن تنبيه تم إرساله الآن لهذا الرمز."""
    with _lock:
        alerts = _load_json(ALERTS_FILE, {})
        alerts[symbol] = datetime.now(timezone.utc).isoformat()
        _save_json(ALERTS_FILE, alerts)


def save_scan_status(status: dict):
    """يحفظ ملخص آخر دورة سكان (لعرضها عبر /status)."""
    with _lock:
        _save_json(STATUS_FILE, status)


def load_scan_status() -> dict:
    """يرجع ملخص آخر دورة سكان."""
    with _lock:
        return _load_json(STATUS_FILE, {
            "status": "لم يبدأ السكانر أي دورة بعد",
            "last_scan_time": None,
        })
