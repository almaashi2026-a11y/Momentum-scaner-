"""
نقطة الدخول الرئيسية للسكانر.

يشغّل:
  - Flask app صغير (للـ health check ولـ Render keep-alive ولـ /status)
  - حلقة سكان بالخلفية (thread منفصل) تعمل كل SCAN_INTERVAL_SECONDS

Stage 1 (Yahoo) -> فلترة آلاف الرموز -> مرشحين
Stage 2 (Finnhub) -> تحليل دقيق على المرشحين -> تأكيد نهائي
تأكيد -> فحص cooldown -> إرسال تنبيه Telegram
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify

from scanner.symbols import get_symbol_universe
from scanner.stage1_yahoo import run_stage1_scan
from scanner.stage2_finnhub import run_stage2_analysis
from telegram_bot import send_telegram_alert
from storage import should_send_alert, mark_alert_sent, save_scan_status, load_scan_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ====== الإعدادات من Environment Variables ======
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))  # 5 دقائق افتراضياً

# قفل لمنع تشغيل دورتين بنفس الوقت
_scan_lock = threading.Lock()
_scan_running = False


def run_single_scan_cycle():
    """دورة سكان واحدة كاملة: Stage 1 -> Stage 2 -> تنبيهات."""
    global _scan_running

    if not _scan_lock.acquire(blocking=False):
        logger.warning("دورة سكان سابقة لا تزال تعمل - تجاهل هذي الدورة")
        return

    _scan_running = True
    cycle_start = time.time()

    try:
        if not FINNHUB_API_KEY:
            logger.error("FINNHUB_API_KEY غير موجود - لا يمكن إجراء Stage 2")
            save_scan_status({
                "status": "error",
                "error": "FINNHUB_API_KEY غير موجود",
                "last_scan_time": datetime.now(timezone.utc).isoformat(),
            })
            return

        symbols = get_symbol_universe()
        logger.info(f"=== دورة سكان جديدة: {len(symbols)} رمز ===")

        stage1_candidates = run_stage1_scan(symbols)
        # نحدد أفضل المرشحين فقط لـ Stage 2 لتفادي rate limits
        top_candidates = stage1_candidates[:50]

        confirmed_results = run_stage2_analysis(top_candidates, FINNHUB_API_KEY)

        alerts_sent = []
        for result in confirmed_results:
            symbol = result["symbol"]
            if should_send_alert(symbol):
                if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                    sent = send_telegram_alert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, result)
                    if sent:
                        mark_alert_sent(symbol)
                        alerts_sent.append(symbol)
                else:
                    logger.warning("Telegram غير مهيأ - تجاهل إرسال التنبيه")
            else:
                logger.info(f"{symbol} مؤكد لكن ضمن فترة cooldown - لا تنبيه جديد")

        cycle_duration = round(time.time() - cycle_start, 1)
        status = {
            "status": "ok",
            "last_scan_time": datetime.now(timezone.utc).isoformat(),
            "symbols_scanned": len(symbols),
            "stage1_candidates": len(stage1_candidates),
            "stage2_confirmed": len(confirmed_results),
            "alerts_sent": alerts_sent,
            "cycle_duration_seconds": cycle_duration,
        }
        save_scan_status(status)
        logger.info(f"=== انتهت الدورة في {cycle_duration} ثانية | "
                    f"مرشحين: {len(stage1_candidates)} | مؤكد: {len(confirmed_results)} | "
                    f"تنبيهات جديدة: {len(alerts_sent)} ===")

    except Exception as e:
        logger.exception(f"خطأ غير متوقع في دورة السكان: {e}")
        save_scan_status({
            "status": "error",
            "error": str(e),
            "last_scan_time": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        _scan_running = False
        _scan_lock.release()


def background_scan_loop():
    """حلقة لا نهائية تشغّل دورة سكان كل SCAN_INTERVAL_SECONDS."""
    logger.info(f"بدء حلقة السكان بالخلفية - كل {SCAN_INTERVAL_SECONDS} ثانية")
    while True:
        run_single_scan_cycle()
        time.sleep(SCAN_INTERVAL_SECONDS)


@app.route("/")
def index():
    return jsonify({
        "service": "nasdaq-momentum-scanner",
        "status": "running",
        "scan_interval_seconds": SCAN_INTERVAL_SECONDS,
    })


@app.route("/status")
def status():
    return jsonify(load_scan_status())


@app.route("/scan-now", methods=["POST", "GET"])
def trigger_scan_now():
    """نقطة دخول لتشغيل دورة فورية يدوياً (مفيدة مع cron-job.org أيضاً)."""
    if _scan_running:
        return jsonify({"status": "already_running"}), 409

    threading.Thread(target=run_single_scan_cycle, daemon=True).start()
    return jsonify({"status": "triggered"})


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


# بدء حلقة السكان بالخلفية مرة واحدة عند تشغيل التطبيق
_background_thread = threading.Thread(target=background_scan_loop, daemon=True)
_background_thread.start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
