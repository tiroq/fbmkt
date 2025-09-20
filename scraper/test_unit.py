#!/usr/bin/env python3
"""
Simple test runner for the modular fbmkt scraper.
This uses Python's built-in unittest framework.
"""
import unittest
import sys
import os

# Add scraper directory to Python path for testing
sys.path.insert(0, os.path.dirname(__file__))

class TestModularStructure(unittest.TestCase):
    """Test the modular structure works correctly."""
    
    def test_imports(self):
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
        
        # All imports successful if we reach here
        self.assertTrue(True)
    
    def test_price_parsing(self):
        """Test price parsing functionality."""
        from utils import parse_price
        
        # Test Thai Baht
        price, currency = parse_price("฿150,000")
        self.assertEqual(price, 150000.0)
        self.assertEqual(currency, "THB")
        
        # Test USD
        price, currency = parse_price("$15,000")
        self.assertEqual(price, 15000.0)
        self.assertEqual(currency, "USD")
    
    def test_text_cleaning(self):
        """Test text cleaning functionality."""
        from utils import clean_text
        
        cleaned = clean_text("  Hello   World  \n")
        self.assertEqual(cleaned, "Hello World")
        
        cleaned = clean_text(None)
        self.assertEqual(cleaned, "")
    
    def test_mileage_extraction(self):
        """Test mileage extraction functionality."""
        from utils import extract_first_number_km
        
        mileage = extract_first_number_km("Car with 50,000 km")
        self.assertEqual(mileage, 50000)
        
        mileage = extract_first_number_km("50 000 км")
        self.assertEqual(mileage, 50000)
    
    def test_listing_model(self):
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
        self.assertEqual(listing.item_id, "123")
        self.assertEqual(listing.title, "Test Car")
        self.assertEqual(listing.category_hint, "vehicles")

class TestMainScraper(unittest.TestCase):
    """Test the main scraper module."""
    
    def test_main_module_import(self):
        """Test that the main scraper module can be imported."""
        import fb_marketplace_scraper
        
        # Check that key functions exist
        self.assertTrue(hasattr(fb_marketplace_scraper, 'main'))
        self.assertTrue(hasattr(fb_marketplace_scraper, 'parse_args'))

if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)