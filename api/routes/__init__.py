"""
Route package initialization.
"""
from .listings import router as listings_router
from .stats import router as stats_router
from .ui import router as ui_router

__all__ = ["listings_router", "stats_router", "ui_router"]