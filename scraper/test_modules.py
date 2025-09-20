#!/usr/bin/env python3
"""
Simple test script to verify the modular structure works correctly.
"""
import sys
import os

# Add scraper directory to Python path for testing
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all modules can be imported successfully."""
    try:
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
        
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality of key components."""
    try:
        from utils import parse_price, clean_text, extract_first_number_km
        from models import Listing
        
        # Test price parsing
        price, currency = parse_price("฿150,000")
        assert price == 150000.0
        assert currency == "THB"
        print("✅ Price parsing works")
        
        # Test text cleaning
        cleaned = clean_text("  Hello   World  \n")
        assert cleaned == "Hello World"
        print("✅ Text cleaning works")
        
        # Test mileage extraction
        mileage = extract_first_number_km("Car with 50,000 km")
        assert mileage == 50000
        print("✅ Mileage extraction works")
        
        # Test Listing creation
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
        print("✅ Listing model works")
        
        return True
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing modular scraper structure...")
    
    success = True
    success &= test_imports()
    success &= test_basic_functionality()
    
    if success:
        print("\n🎉 All tests passed! The modular structure is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the module structure.")
        sys.exit(1)