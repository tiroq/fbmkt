"""
Database operations and connection management.
"""
import sqlite3
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from .config import config

logger = logging.getLogger(__name__)

@contextmanager
def get_db_connection():
    """Get a database connection with proper error handling."""
    conn = None
    try:
        if not config.DB_PATH:
            raise ValueError("Database path not configured")
        
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected database error: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def build_where_clause(filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """Build WHERE clause and parameters from filters."""
    where_conditions = []
    parameters = []
    
    # Text search
    q = filters.get('q')
    if q:
        where_conditions.append('(lower(title) LIKE ? OR lower(brand) LIKE ? OR lower(model) LIKE ?)')
        search_term = f'%{q.lower()}%'
        parameters.extend([search_term, search_term, search_term])
    
    # Category filter
    category = filters.get('category_hint')
    if category:
        where_conditions.append('category_hint = ?')
        parameters.append(category)
    
    # Price range
    min_price = filters.get('min_price')
    if min_price is not None:
        where_conditions.append('(price_value IS NOT NULL AND price_value >= ?)')
        parameters.append(min_price)
    
    max_price = filters.get('max_price')
    if max_price is not None:
        where_conditions.append('(price_value IS NOT NULL AND price_value <= ?)')
        parameters.append(max_price)
    
    # Year filter
    year = filters.get('year')
    if year is not None:
        where_conditions.append('year = ?')
        parameters.append(year)
    
    # Location bounds
    min_lat, max_lat = filters.get('min_lat'), filters.get('max_lat')
    if min_lat is not None and max_lat is not None:
        where_conditions.append('(latitude BETWEEN ? AND ?)')
        parameters.extend([min_lat, max_lat])
    
    min_lon, max_lon = filters.get('min_lon'), filters.get('max_lon')
    if min_lon is not None and max_lon is not None:
        where_conditions.append('(longitude BETWEEN ? AND ?)')
        parameters.extend([min_lon, max_lon])
    
    where_clause = ' WHERE ' + ' AND '.join(where_conditions) if where_conditions else ''
    return where_clause, parameters

def get_order_clause(sort: str) -> str:
    """Generate ORDER BY clause based on sort parameter."""
    sort_options = {
        "price_asc": "ORDER BY price_value ASC",
        "price_desc": "ORDER BY price_value DESC", 
        "year_desc": "ORDER BY year DESC",
        "year_asc": "ORDER BY year ASC",
        "last_seen_desc": "ORDER BY datetime(last_seen) DESC"
    }
    return sort_options.get(sort, sort_options["last_seen_desc"])

def get_listings_count(filters: Dict[str, Any]) -> int:
    """Get total count of listings matching filters."""
    with get_db_connection() as conn:
        where_clause, parameters = build_where_clause(filters)
        sql = f'SELECT COUNT(*) FROM listings {where_clause}'
        result = conn.execute(sql, parameters).fetchone()
        return result[0] if result else 0

def get_listings(filters: Dict[str, Any], sort: str = 'last_seen_desc', 
                limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get listings with filters, sorting, and pagination."""
    with get_db_connection() as conn:
        where_clause, parameters = build_where_clause(filters)
        order_clause = get_order_clause(sort)
        
        sql = f'SELECT * FROM listings {where_clause} {order_clause} LIMIT ? OFFSET ?'
        parameters.extend([limit, offset])
        
        cursor = conn.execute(sql, parameters)
        columns = [description[0] for description in cursor.description]
        
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_listing_by_id(item_id: str) -> Optional[Dict]:
    """Get a single listing by ID."""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT * FROM listings WHERE item_id = ?', (item_id,))
        row = cursor.fetchone()
        
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None

def get_price_history(item_id: str) -> List[Dict]:
    """Get price history for a specific item."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT ts, price_value, price_currency FROM price_history WHERE item_id = ? ORDER BY ts ASC',
            (item_id,)
        )
        return [{'ts': row[0], 'price_value': row[1], 'price_currency': row[2]} 
                for row in cursor.fetchall()]

def get_statistics() -> Dict[str, Any]:
    """Get various statistics about the listings."""
    with get_db_connection() as conn:
        # Basic counts
        total_listings = conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
        active_7d = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE datetime(last_seen) >= datetime('now','-7 day')"
        ).fetchone()[0]
        
        # Price statistics
        price_stats = conn.execute(
            'SELECT MIN(price_value), MAX(price_value), AVG(price_value) FROM listings WHERE price_value IS NOT NULL'
        ).fetchone()
        min_price, max_price, avg_price = price_stats if price_stats else (None, None, None)
        
        # Brand statistics
        brand_stats = conn.execute(
            "SELECT brand, COUNT(*) FROM listings WHERE brand != '' GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall()
        
        # Year statistics
        year_stats = conn.execute(
            'SELECT year, COUNT(*) FROM listings WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC LIMIT 20'
        ).fetchall()
        
        return {
            'total_listings': total_listings,
            'active_last_days': active_7d,
            'min_price': min_price,
            'max_price': max_price,
            'avg_price': avg_price,
            'by_brand': {brand: count for brand, count in brand_stats},
            'by_year': {str(year): count for year, count in year_stats}
        }