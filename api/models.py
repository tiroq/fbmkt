"""
Pydantic models for API request/response serialization.
"""
from typing import Optional, List, Dict
from pydantic import BaseModel

class ListingOut(BaseModel):
    """Output model for listing data."""
    item_id: str
    title: str = ""
    brand: str = ""
    model: str = ""
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: str = ""
    transmission: str = ""
    body_type: str = ""
    price_text: str = ""
    price_value: Optional[float] = None
    price_currency: Optional[str] = None
    location_text: str = ""
    posted_text: str = ""
    seller_text: str = ""
    thumbnail_url: str = ""
    img_urls: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: str = ""
    attributes_json: str = ""
    category_hint: str = ""
    source_url: str = ""
    item_url: str = ""
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

class ListingsResponse(BaseModel):
    """Response model for paginated listings."""
    total: int
    items: List[ListingOut]

class PricePoint(BaseModel):
    """Model for price history data point."""
    ts: str
    price_value: Optional[float]
    price_currency: Optional[str]

class StatsOut(BaseModel):
    """Model for statistics data."""
    total_listings: int
    active_last_days: int
    min_price: Optional[float]
    max_price: Optional[float]
    avg_price: Optional[float]
    by_brand: Dict[str, int]
    by_year: Dict[str, int]

class ListingFilters(BaseModel):
    """Model for listing filter parameters."""
    q: Optional[str] = None
    category_hint: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    year: Optional[int] = None
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None