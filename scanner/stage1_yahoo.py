"""
Stage 1: مسح أولي واسع لكل رموز NASDAQ باستخدام Yahoo Finance.

الهدف: تصفية آلاف الرموز بسرعة للوصول لقائمة مرشحين صغيرة (~30-50 رمز)
تستوفي الشروط الأساسية:
  - السعر بين 0.20 و 10 دولار
  - حجم تداول اليوم مرتفع بشكل غير طبيعي (مؤشر مبدئي على RVOL)
  - تغيّر سعر إيجابي ملحوظ

لا نحسب هنا EMA9/VWAP الدقيقة - هذا يتم في Stage 2 (Finnhub) لأنه أدق
وأقل استهلاكاً لو طبقناه على آلاف الرموز.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

logger = logging.getLogger(__name__)

PRICE_MIN = 0.20
PRICE_MAX = 10.0
MIN_PRICE_CHANGE_PCT = 3.0
MIN_VOLUME_RATIO = 1.5
MAX_WORKERS = 20
BATCH_SIZE = 200


def _scan_batch(symbols_batch: list[str]) -> list[dict]:
    """يفحص دفعة من الرموز دفعة واحدة عبر yf.Tickers لتقليل عدد الطلبات."""
    results = []
    try:
        tickers_str = " ".join(symbols_batch)
        tickers = yf.Tickers(tickers_str)

        for symbol in symbols_batch:
            try:
                ticker = tickers.tickers.get(symbol)
                if ticker is None:
                    continue

                fast_info = ticker.fast_info
                price = fast_info.get("lastPrice")
                prev_close = fast_info.get("previousClose")
                volume = fast_info.get("lastVolume")
                avg_volume = fast_info.get("threeMonthAverageVolume")

                if not price or not prev_close or price <= 0:
                    continue
                if price < PRICE_MIN or price > PRICE_MAX:
                    continue

                price_change_pct = ((price - prev_close) / prev_close) * 100
                if price_change_pct < MIN_PRICE_CHANGE_PCT:
                    continue

                if avg_volume and volume:
                    volume_ratio = volume / avg_volume
                    if volume_ratio < MIN_VOLUME_RATIO:
                        continue
                else:
                    volume_ratio = None

                results.append({
                    "symbol": symbol,
                    "price": price,
                    "prev_close": prev_close,
                    "price_change_pct": round(price_change_pct, 2),
                    "volume": volume,
                    "avg_volume": avg_volume,
                    "volume_ratio_est": round(volume_ratio, 2) if volume_ratio else None,
                })

            except Exception:
                continue

    except Exception as e:
        logger.warning(f"فشل فحص دفعة من {len(symbols_batch)} رمز: {e}")

    return results


def run_stage1_scan(symbols: list[str]) -> list[dict]:
    """يفحص كل الرموز المعطاة على دفعات متوازية، ويرجع قائمة المرشحين."""
    batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    candidates = []

    logger.info(f"Stage 1: بدء فحص {len(symbols)} رمز على {len(batches)} دفعة")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_scan_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            try:
                batch_results = future.result()
                candidates.extend(batch_results)
            except Exception as e:
                logger.warning(f"فشل دفعة كاملة: {e}")

    candidates.sort(key=lambda x: x["price_change_pct"], reverse=True)

    logger.info(f"Stage 1: انتهى الفحص، {len(candidates)} مرشح تجاوز الفلتر الأولي")
    return candidates
