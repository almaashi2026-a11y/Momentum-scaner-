"""
Stage 2: تحليل عميق ودقيق على المرشحين القادمين من Stage 1 فقط (~30-50 رمز).

شروط التأكيد النهائي (momentum breakout):
  1. EMA9 يقطع فوق VWAP
  2. RVOL > 2x
  3. تغيّر السعر >= +5% في آخر 15 دقيقة
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

RVOL_THRESHOLD = 2.0
PRICE_CHANGE_15MIN_THRESHOLD = 5.0
EMA_PERIOD = 9

REQUEST_DELAY_SECONDS = 1.05


def _get_candles(symbol: str, api_key: str, resolution: str = "1", lookback_minutes: int = 120):
    """يجلب شموع دقيقة واحدة لآخر lookback_minutes دقيقة."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=lookback_minutes)

    url = f"{FINNHUB_BASE_URL}/stock/candle"
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "from": int(start.timestamp()),
        "to": int(now.timestamp()),
        "token": api_key,
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code == 429:
        raise RuntimeError("Finnhub rate limit (429) - تم تجاوز الحد المسموح")

    response.raise_for_status()
    data = response.json()

    if data.get("s") != "ok":
        return None

    return data


def _calculate_ema(values: list[float], period: int) -> list[float]:
    """يحسب EMA لقائمة أسعار."""
    if len(values) < period:
        return []

    ema_values = []
    multiplier = 2 / (period + 1)

    sma = sum(values[:period]) / period
    ema_values.append(sma)

    for price in values[period:]:
        new_ema = (price - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(new_ema)

    return ema_values


def _calculate_vwap(candles: dict) -> float:
    """يحسب VWAP التراكمي لليوم الحالي بناءً على شموع الدقيقة."""
    closes, highs, lows, volumes = candles["c"], candles["h"], candles["l"], candles["v"]

    cumulative_pv = 0.0
    cumulative_volume = 0.0

    for h, l, c, v in zip(highs, lows, closes, volumes):
        typical_price = (h + l + c) / 3
        cumulative_pv += typical_price * v
        cumulative_volume += v

    if cumulative_volume == 0:
        return 0.0

    return cumulative_pv / cumulative_volume


def analyze_symbol(symbol: str, api_key: str) -> dict | None:
    """يحلل رمز واحد بدقة ويرجع نتيجة التحليل إذا حقق كل الشروط."""
    try:
        candles = _get_candles(symbol, api_key, resolution="1", lookback_minutes=120)
        if not candles or len(candles.get("c", [])) < EMA_PERIOD + 1:
            return None

        closes = candles["c"]
        volumes = candles["v"]

        ema9_series = _calculate_ema(closes, EMA_PERIOD)
        if not ema9_series:
            return None
        ema9_current = ema9_series[-1]
        vwap_current = _calculate_vwap(candles)

        ema_above_vwap = ema9_current > vwap_current

        recent_volume = sum(volumes[-15:]) if len(volumes) >= 15 else sum(volumes)
        avg_volume_per_15min = (sum(volumes) / len(volumes)) * 15 if volumes else 0
        rvol = (recent_volume / avg_volume_per_15min) if avg_volume_per_15min > 0 else 0

        if len(closes) >= 16:
            price_15min_ago = closes[-16]
        else:
            price_15min_ago = closes[0]
        price_now = closes[-1]
        price_change_15min_pct = (
            ((price_now - price_15min_ago) / price_15min_ago) * 100
            if price_15min_ago > 0 else 0
        )

        conditions_met = (
            ema_above_vwap
            and rvol >= RVOL_THRESHOLD
            and price_change_15min_pct >= PRICE_CHANGE_15MIN_THRESHOLD
        )

        result = {
            "symbol": symbol,
            "price": price_now,
            "ema9": round(ema9_current, 4),
            "vwap": round(vwap_current, 4),
            "ema_above_vwap": ema_above_vwap,
            "rvol": round(rvol, 2),
            "price_change_15min_pct": round(price_change_15min_pct, 2),
            "confirmed": conditions_met,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return result if conditions_met else None

    except RuntimeError as e:
        logger.warning(f"Stage 2 [{symbol}]: {e}")
        return None
    except Exception as e:
        logger.warning(f"Stage 2 [{symbol}]: فشل التحليل - {e}")
        return None


def run_stage2_analysis(candidates: list[dict], api_key: str) -> list[dict]:
    """يطبق التحليل الدقيق على مرشحي Stage 1 بشكل متسلسل مع تأخير بسيط."""
    confirmed = []
    logger.info(f"Stage 2: بدء التحليل الدقيق على {len(candidates)} مرشح")

    for i, candidate in enumerate(candidates):
        symbol = candidate["symbol"]
        result = analyze_symbol(symbol, api_key)

        if result:
            result["stage1_price_change_pct"] = candidate.get("price_change_pct")
            confirmed.append(result)
            logger.info(f"Stage 2: تأكيد {symbol} - RVOL={result['rvol']}, "
                        f"15min_change={result['price_change_15min_pct']}%")

        if i < len(candidates) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    logger.info(f"Stage 2: انتهى التحليل، {len(confirmed)} رمز مؤكد")
    return confirmed
