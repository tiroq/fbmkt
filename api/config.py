"""
API configuration and settings management.
"""
import os
from typing import Optional

class Config:
    """Application configuration."""
    
    # Database
    DB_PATH: str = os.getenv("FB_DB", "./data/db/fb_marketplace.db")
    
    # API settings
    API_TITLE: str = "FB Marketplace API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "REST API for Facebook Marketplace scraped data"
    
    # CORS settings
    CORS_ORIGINS: list = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["*"]
    CORS_ALLOW_HEADERS: list = ["*"]
    
    # Pagination defaults
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 500
    DEFAULT_API_LIMIT: int = 50
    MAX_API_LIMIT: int = 500
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> None:
        """Validate configuration on startup."""
        if not os.path.exists(cls.DB_PATH):
            raise FileNotFoundError(f"Database file not found: {cls.DB_PATH}")

# Global config instance
config = Config()