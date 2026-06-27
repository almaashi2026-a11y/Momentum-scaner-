"""
إدارة قائمة رموز NASDAQ.
نستخدم مصدرين:
1. ملف ثابت (NASDAQ-listed) محدّث بشكل دوري كـ fallback
2. تحميل ديناميكي من NASDAQ FTP (nasdaqlisted.txt) عند توفر الإنترنت

السعر بين 0.20 و 10 دولار يتم فلترته في Stage 1 (لأن قائمة الرموز
لا تحتوي على السعر، السعر يأتي من Yahoo Finance).
"""

import logging
import urllib.request
import io

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"

FALLBACK_SYMBOLS = [
    "SIRI", "PLUG", "SOFI", "NIO", "RIOT", "MARA", "FCEL", "CLOV", "WKHS",
    "GSAT", "OPEN", "VINC", "SAGT", "INLF", "FCUV", "AZTR", "CAST", "BBAI",
    "MULN", "PHUN", "ATER", "PROK", "TOPS", "SHIP", "CTRM", "NAKD",
]


def fetch_all_nasdaq_symbols() -> list[str]:
    """يجلب كل رموز NASDAQ المتداولة من ملف NASDAQ الرسمي."""
    try:
        req = urllib.request.Request(
            NASDAQ_LISTED_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")

        symbols = []
        lines = raw.splitlines()
        for line in lines[1:]:
            if line.startswith("File Creation Time"):
                continue
            parts = line.split("|")
            if len(parts) < 4:
                continue
            symbol, test_issue = parts[0], parts[3]
            if test_issue == "Y":
                continue
            if "$" in symbol or "." in symbol:
                continue
            symbols.append(symbol.strip())

        logger.info(f"تم تحميل {len(symbols)} رمز من NASDAQ")
        return symbols

    except Exception as e:
        logger.warning(f"فشل تحميل قائمة الرموز الديناميكية: {e}")
        return []


def get_symbol_universe() -> list[str]:
    """يرجع قائمة الرموز التي سيتم فحصها في Stage 1."""
    symbols = fetch_all_nasdaq_symbols()
    if not symbols:
        logger.warning("استخدام قائمة fallback الثابتة")
        return FALLBACK_SYMBOLS
    return symbols
