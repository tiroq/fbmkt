"""
FB Marketplace API - Refactored main application.

This is the main FastAPI application with clean modular architecture.
"""
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import config
from .routes import listings_router, stats_router, ui_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('api.log')
    ]
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    logger.info("Starting FB Marketplace API...")
    try:
        # Validate configuration
        config.validate()
        logger.info(f"Database path: {config.DB_PATH}")
        logger.info("API startup complete")
        yield
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down FB Marketplace API...")

# Create FastAPI application
app = FastAPI(
    title=config.API_TITLE,
    version=config.API_VERSION,
    description=config.API_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=config.CORS_ALLOW_METHODS,
    allow_headers=config.CORS_ALLOW_HEADERS,
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        from database import get_db_connection
        with get_db_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        
        return {
            "status": "healthy",
            "version": config.API_VERSION,
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

# Include routers
app.include_router(ui_router)
app.include_router(listings_router)
app.include_router(stats_router)

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Basic metrics endpoint."""
    try:
        from database import get_statistics
        stats = get_statistics()
        return {
            "total_listings": stats["total_listings"],
            "active_listings_7d": stats["active_last_days"],
            "api_version": config.API_VERSION
        }
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return {"error": "Unable to fetch metrics"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.LOG_LEVEL.lower()
    )