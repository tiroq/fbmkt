"""
Statistics API route handlers.
"""
import logging
from fastapi import APIRouter, HTTPException

from ..models import StatsOut
from ..database import get_statistics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["statistics"])

@router.get("/stats", response_model=StatsOut)
async def get_api_stats():
    """Get marketplace statistics."""
    try:
        stats_data = get_statistics()
        return StatsOut(**stats_data)
        
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")