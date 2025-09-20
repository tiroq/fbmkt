"""
Database operations for Facebook Marketplace scraper.
"""
import json
import os
import sqlite3
from typing import Optional, Dict, Tuple

from models import Listing
from utils import now_iso


# Schema definitions
DDL_LISTINGS = """
CREATE TABLE IF NOT EXISTS listings (
  item_id TEXT PRIMARY KEY,
  item_url TEXT,
  title TEXT,
  brand TEXT,
  model TEXT,
  year INTEGER,
  mileage_km INTEGER,
  fuel TEXT,
  transmission TEXT,
  body_type TEXT,
  price_text TEXT,
  price_value REAL,
  price_currency TEXT,
  location_text TEXT,
  posted_text TEXT,
  seller_text TEXT,
  thumbnail_url TEXT,
  img_urls TEXT,
  latitude REAL,
  longitude REAL,
  description TEXT,
  attributes_json TEXT,
  category_hint TEXT,
  source_url TEXT,
  first_seen TEXT,
  last_seen TEXT
);
"""

DDL_PRICE_HISTORY = """
CREATE TABLE IF NOT EXISTS price_history (
  item_id TEXT,
  ts TEXT DEFAULT (datetime('now')),
  price_value REAL,
  price_currency TEXT,
  PRIMARY KEY (item_id, ts)
);
"""

DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);",
    "CREATE INDEX IF NOT EXISTS idx_price_history_item ON price_history(item_id);"
]


def db_connect(path: str) -> sqlite3.Connection:
    """Create database connection with optimized settings."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def db_init(conn: sqlite3.Connection):
    """Initialize database schema with tables and indexes."""
    conn.execute(DDL_LISTINGS)
    conn.execute(DDL_PRICE_HISTORY)
    for ddl in DDL_INDEXES:
        conn.execute(ddl)
    conn.commit()


def row_to_dict(cur, row):
    """Convert sqlite3.Row to dictionary."""
    return {desc[0]: row[i] for i, desc in enumerate(cur.description)}


def db_get_listing(conn: sqlite3.Connection, item_id: str) -> Optional[Dict]:
    """Retrieve existing listing by item_id."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM listings WHERE item_id = ?", (item_id,))
    r = cur.fetchone()
    if not r:
        return None
    return row_to_dict(cur, r)


def db_insert_listing(conn: sqlite3.Connection, lst: Listing):
    """Insert new listing into database."""
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO listings (
      item_id,item_url,title,brand,model,year,mileage_km,fuel,transmission,body_type,
      price_text,price_value,price_currency,location_text,posted_text,seller_text,
      thumbnail_url,img_urls,latitude,longitude,description,attributes_json,
      category_hint,source_url,first_seen,last_seen
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lst.item_id, lst.item_url, lst.title, lst.brand, lst.model, lst.year, lst.mileage_km,
        lst.fuel, lst.transmission, lst.body_type,
        lst.price_text, lst.price_value, lst.price_currency, lst.location_text, lst.posted_text,
        lst.seller_text, lst.thumbnail_url, "|".join(lst.img_urls) if lst.img_urls else "",
        lst.latitude, lst.longitude, lst.description, json.dumps(lst.attributes_kv, ensure_ascii=False),
        lst.category_hint, lst.source_url, now_iso(), now_iso()
    ))
    conn.commit()


def db_update_listing(conn: sqlite3.Connection, lst: Listing):
    """Update existing listing in database."""
    cur = conn.cursor()
    cur.execute("""
    UPDATE listings SET
      item_url=?, title=?, brand=?, model=?, year=?, mileage_km=?, fuel=?, transmission=?, body_type=?,
      price_text=?, price_value=?, price_currency=?, location_text=?, posted_text=?, seller_text=?,
      thumbnail_url=?, img_urls=?, latitude=?, longitude=?, description=?, attributes_json=?,
      category_hint=?, source_url=?, last_seen=?
    WHERE item_id=?
    """, (
        lst.item_url, lst.title, lst.brand, lst.model, lst.year, lst.mileage_km, lst.fuel, lst.transmission, lst.body_type,
        lst.price_text, lst.price_value, lst.price_currency, lst.location_text, lst.posted_text, lst.seller_text,
        lst.thumbnail_url, "|".join(lst.img_urls) if lst.img_urls else "", lst.latitude, lst.longitude,
        lst.description, json.dumps(lst.attributes_kv, ensure_ascii=False),
        lst.category_hint, lst.source_url, now_iso(), lst.item_id
    ))
    conn.commit()


def db_insert_price_event(conn: sqlite3.Connection, item_id: str, price_value: Optional[float], price_currency: Optional[str]):
    """Insert price change event into price history."""
    if price_value is None:
        return
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO price_history (item_id, ts, price_value, price_currency)
    VALUES (?, datetime('now'), ?, ?)
    """, (item_id, price_value, price_currency))
    conn.commit()


def upsert_with_price_history(conn: sqlite3.Connection, lst: Listing) -> Tuple[bool, bool]:
    """
    Insert or update listing and track price changes.
    
    Returns:
        Tuple of (is_new_item, price_changed)
    """
    existing = db_get_listing(conn, lst.item_id)
    if existing is None:
        db_insert_listing(conn, lst)
        if lst.price_value is not None:
            db_insert_price_event(conn, lst.item_id, lst.price_value, lst.price_currency)
        return True, bool(lst.price_value is not None)
    else:
        old_price = existing.get("price_value")
        old_cur = existing.get("price_currency")
        price_changed = (
            lst.price_value is not None and 
            (old_price is None or 
             float(old_price) != float(lst.price_value) or 
             (lst.price_currency or "") != (old_cur or ""))
        )
        db_update_listing(conn, lst)
        if price_changed:
            db_insert_price_event(conn, lst.item_id, lst.price_value, lst.price_currency)
        return False, price_changed