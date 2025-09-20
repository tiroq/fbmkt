"""
Export utilities for Facebook Marketplace scraper.
"""
import json
import sqlite3
from typing import List, Optional

import pandas as pd

from models import Listing


def export_new_since_run(conn: sqlite3.Connection, run_started_iso: str) -> pd.DataFrame:
    """Export listings that were first seen since the given timestamp."""
    q = """
    SELECT *
    FROM listings
    WHERE first_seen >= ?
    ORDER BY first_seen DESC
    """
    df = pd.read_sql_query(q, conn, params=(run_started_iso,))
    return df


def export_price_history(conn: sqlite3.Connection, item_id: Optional[str] = None) -> pd.DataFrame:
    """Export price history for all items or specific item."""
    if item_id:
        q = "SELECT * FROM price_history WHERE item_id=? ORDER BY ts ASC"
        return pd.read_sql_query(q, conn, params=(item_id,))
    else:
        q = "SELECT * FROM price_history ORDER BY item_id, ts ASC"
        return pd.read_sql_query(q, conn)


def save_output_rows(listings: List[Listing], out_path: str, logger=None):
    """Save listings to CSV or Excel file."""
    rows = []
    for x in listings:
        rows.append({
            "item_id": x.item_id,
            "title": x.title,
            "brand": x.brand,
            "model": x.model,
            "year": x.year,
            "mileage_km": x.mileage_km,
            "fuel": x.fuel,
            "transmission": x.transmission,
            "body_type": x.body_type,
            "price_text": x.price_text,
            "price_value": x.price_value,
            "price_currency": x.price_currency,
            "location_text": x.location_text,
            "posted_text": x.posted_text,
            "seller_text": x.seller_text,
            "thumbnail_url": x.thumbnail_url,
            "img_urls": "|".join(x.img_urls) if x.img_urls else "",
            "latitude": x.latitude,
            "longitude": x.longitude,
            "description": x.description,
            "attributes_json": json.dumps(x.attributes_kv, ensure_ascii=False),
            "item_url": x.item_url,
            "category_hint": x.category_hint,
            "source_url": x.source_url
        })
    
    df = pd.DataFrame(rows)
    if out_path.lower().endswith(".xlsx"):
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)
    
    if logger:
        logger.info(f">>> Saved {len(df)} rows to {out_path}")
    else:
        print(f">>> Saved {len(df)} rows to {out_path}")