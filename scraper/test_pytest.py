#!/usr/bin/env python3
"""
Test runner using pytest for more advanced testing capabilities.
"""
import pytest
import sys
import os

# Add scraper directory to Python path for testing
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all modules can be imported successfully."""
    # Import individual modules
    import models
    import utils
    import database
    import export
    import core
    
    # Test specific imports
    from models import Listing
    from utils import init_logger, now_iso, parse_price
    from database import db_connect, db_init
    from export import export_new_since_run
    from core import run_scrape

def test_price_parsing():
    """Test price parsing functionality."""
    from utils import parse_price
    
    # Test Thai Baht
    price, currency = parse_price("฿150,000")
    assert price == 150000.0
    assert currency == "THB"
    
    # Test USD
    price, currency = parse_price("$15,000")
    assert price == 15000.0
    assert currency == "USD"
    
    # Test edge cases
    price, currency = parse_price("")
    assert price is None
    assert currency is None

def test_text_cleaning():
    """Test text cleaning functionality."""
    from utils import clean_text
    
    assert clean_text("  Hello   World  \n") == "Hello World"
    assert clean_text(None) == ""
    assert clean_text("") == ""

def test_mileage_extraction():
    """Test mileage extraction functionality."""
    from utils import extract_first_number_km
    
    assert extract_first_number_km("Car with 50,000 km") == 50000
    assert extract_first_number_km("50 000 км") == 50000
    assert extract_first_number_km("No mileage info") is None

def test_listing_model():
    """Test Listing model creation."""
    from models import Listing
    
    listing = Listing(
        source_url="https://example.com",
        item_url="https://facebook.com/marketplace/item/123",
        item_id="123",
        title="Test Car",
        price_text="฿100,000",
        location_text="Bangkok",
        thumbnail_url="",
        seller_text="John Doe",
        posted_text="1 hour ago",
        category_hint="vehicles"
    )
    assert listing.item_id == "123"
    assert listing.title == "Test Car"
    assert listing.category_hint == "vehicles"

def test_main_scraper_import():
    """Test that the main scraper module can be imported."""
    import fb_marketplace_scraper
    
    # Check that key functions exist
    assert hasattr(fb_marketplace_scraper, 'main')
    assert hasattr(fb_marketplace_scraper, 'parse_args')

if __name__ == "__main__":
    # Run pytest programmatically
    pytest.main([__file__, "-v"])