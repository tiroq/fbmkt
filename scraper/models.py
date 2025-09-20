"""
Data models for Facebook Marketplace scraper.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Listing:
    """Represents a Facebook Marketplace listing with all extracted data."""
    
    # Basic listing info
    source_url: str
    item_url: str
    item_id: str
    title: str
    price_text: str
    location_text: str
    thumbnail_url: str
    seller_text: str
    posted_text: str
    category_hint: str
    
    # Detailed info (populated in second pass)
    description: str = ""
    attributes_kv: Dict[str, str] = field(default_factory=dict)
    
    # Vehicle-specific fields
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: str = ""
    transmission: str = ""
    body_type: str = ""
    brand: str = ""
    model: str = ""
    
    # Media and location
    img_urls: List[str] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Parsed price data
    price_value: Optional[float] = None
    price_currency: Optional[str] = None