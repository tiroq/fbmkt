"""
API route handlers for listings endpoints.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import StreamingResponse
import pandas as pd

from ..models import ListingOut, ListingsResponse, PricePoint, ListingFilters
from ..database import (
    get_listings_count, get_listings, get_listing_by_id, 
    get_price_history, get_db_connection
)
from ..config import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["listings"])

def get_listing_filters(
    q: Optional[str] = None,
    category_hint: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    year: Optional[int] = None,
    min_lat: Optional[float] = None,
    max_lat: Optional[float] = None,
    min_lon: Optional[float] = None,
    max_lon: Optional[float] = None,
) -> dict:
    """Dependency to extract and validate listing filters."""
    return {
        'q': q,
        'category_hint': category_hint,
        'min_price': min_price,
        'max_price': max_price,
        'year': year,
        'min_lat': min_lat,
        'max_lat': max_lat,
        'min_lon': min_lon,
        'max_lon': max_lon
    }

@router.get("/listings", response_model=ListingsResponse)
async def get_api_listings(
    filters: dict = Depends(get_listing_filters),
    sort: str = 'last_seen_desc',
    limit: int = Query(config.DEFAULT_API_LIMIT, ge=1, le=config.MAX_API_LIMIT),
    offset: int = Query(0, ge=0)
):
    """Get listings with filtering, sorting and pagination."""
    try:
        total = get_listings_count(filters)
        items_data = get_listings(filters, sort, limit, offset)
        items = [ListingOut(**item) for item in items_data]
        
        return ListingsResponse(total=total, items=items)
        
    except Exception as e:
        logger.error(f"Error fetching listings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/listings/{item_id}", response_model=ListingOut)
async def get_api_listing(item_id: str):
    """Get a specific listing by ID."""
    try:
        listing_data = get_listing_by_id(item_id)
        if not listing_data:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        return ListingOut(**listing_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching listing {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/listings/{item_id}/price-history", response_model=List[PricePoint])
async def get_api_price_history(item_id: str):
    """Get price history for a specific listing."""
    try:
        # First check if listing exists
        listing = get_listing_by_id(item_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        history_data = get_price_history(item_id)
        return [PricePoint(**point) for point in history_data]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching price history for {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/export/csv")
async def export_listings_csv(
    filters: dict = Depends(get_listing_filters),
    sort: str = 'last_seen_desc'
):
    """Export filtered listings as CSV."""
    try:
        # Get all matching listings (no pagination for export)
        listings_data = get_listings(filters, sort, limit=10000, offset=0)
        
        if not listings_data:
            # Return empty CSV with headers
            df = pd.DataFrame(columns=['item_id', 'title', 'brand', 'model', 'price_value'])
        else:
            df = pd.DataFrame(listings_data)
        
        csv_content = df.to_csv(index=False).encode('utf-8')
        
        return StreamingResponse(
            iter([csv_content]),
            media_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="fbmkt_listings.csv"'}
        )
        
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=500, detail="Error generating CSV export")