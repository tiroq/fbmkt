"""
Utility functions for text processing, price parsing, and logging.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple


def init_logger(
    name: str = "fbmkt",
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    log_file: Optional[str] = "fbmkt.log"
) -> logging.Logger:
    """Initialize logger with console and optional file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    console_level_num = getattr(logging, console_level.upper(), logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(console_level_num)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_file:  # Create file handler only if log_file is provided
        file_level_num = getattr(logging, file_level.upper(), logging.DEBUG)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(file_level_num)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def clean_text(s: Optional[str]) -> str:
    """Clean and normalize text by removing extra whitespace."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_price(price_text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse price text to extract numeric value and currency.
    
    Supports various formats and currencies (THB ฿, USD $, EUR €, GBP £).
    """
    if not price_text:
        return (None, None)
    
    s = price_text.replace(",", "").replace("\xa0", " ")
    m = re.search(r"(฿|\$|€|£)?\s?(\d+(?:\.\d+)?)", s)
    cur = None
    val = None
    
    if m:
        cur = m.group(1)
        try:
            val = float(m.group(2))
        except ValueError:
            val = None
    
    if not cur:
        m2 = re.search(r"\b(THB|USD|EUR|GBP)\b", s, re.I)
        if m2:
            cur = m2.group(1).upper()
    
    symbol_map = {"฿": "THB", "$": "USD", "€": "EUR", "£": "GBP"}
    if cur in symbol_map:
        cur = symbol_map[cur]
    
    return (val, cur)


def to_float(text: str) -> Optional[float]:
    """Safely convert text to float."""
    if not text:
        return None
    try:
        return float(text)
    except:
        return None


def extract_first_number_km(text: str) -> Optional[int]:
    """
    Extract first number that appears to be mileage in kilometers.
    
    Handles various formats like "123,456 km", "123456км", etc.
    """
    if not text:
        return None
    
    t = text.replace(",", " ")
    m = re.search(r"(\d[\d\s]{1,12})\s?(км|km)\b", t, re.I)
    if m:
        num = re.sub(r"\s+", "", m.group(1))
        try:
            return int(num)
        except:
            return None
    
    # Fallback: look for standalone numbers that might be mileage
    m2 = re.search(r"\b(\d{4,7})\b", t)
    if m2:
        try:
            return int(m2.group(1))
        except:
            return None
    
    return None


def build_urls(lat: float, lon: float, radius_km: int, query: Optional[str], category: str) -> list[str]:
    """Build Facebook Marketplace URLs for given search parameters."""
    MARKETPLACE_BASE = "https://www.facebook.com/marketplace"
    params_geo = f"exact=false&latitude={lat}&longitude={lon}&radius_km={radius_km}&locale=en_US"
    
    urls = []
    if category in ("vehicles", "all"):
        urls.append(f"{MARKETPLACE_BASE}/category/vehicles?{params_geo}")
    if category in ("motorcycles", "all"):
        urls.append(f"{MARKETPLACE_BASE}/category/motorcycles?{params_geo}")
    if query:
        q = re.sub(r"\\s+", "%20", query.strip())
        urls.append(f"{MARKETPLACE_BASE}/search/?query={q}&{params_geo}")
    
    # Remove duplicates while preserving order
    uniq, seen = [], set()
    for u in urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    
    return uniq