# Facebook Marketplace Scraper - Modular Architecture

This directory contains the refactored Facebook Marketplace scraper with a clean, modular architecture for better maintainability.

## Module Structure

### `models.py`
- **Purpose**: Data models and structures
- **Key Classes**: `Listing` dataclass with all marketplace item fields
- **Focus**: Vehicle-specific attributes (year, mileage, fuel, transmission, etc.)

### `utils.py` 
- **Purpose**: Utility functions for text processing and parsing
- **Key Functions**:
  - `parse_price()` - Multi-currency price extraction (THB, USD, EUR, GBP)
  - `clean_text()` - Text normalization and whitespace handling
  - `extract_first_number_km()` - Mileage extraction with various formats
  - `init_logger()` - Centralized logging setup
  - `build_urls()` - Facebook Marketplace URL construction

### `database.py`
- **Purpose**: SQLite database operations and schema management
- **Key Functions**:
  - `db_connect()`, `db_init()` - Database setup with WAL mode
  - `upsert_with_price_history()` - Incremental loading with price tracking
  - Schema definitions for `listings` and `price_history` tables

### `scraper.py`
- **Purpose**: Core Playwright-based scraping logic
- **Key Functions**:
  - `extract_cards_on_page()` - DOM scraping with fallback strategies
  - `scroll_and_collect()` - Infinite scroll handling with no-growth detection
  - `extract_details_from_item()` - Second-pass detailed data extraction
  - `_extract_vehicle_attributes()` - Vehicle-specific attribute parsing

### `core.py`
- **Purpose**: High-level scraping orchestration and browser management
- **Key Functions**:
  - `run_scrape()` - Main entry point with browser lifecycle management
  - Authentication handling with storage state persistence
  - Mobile fallback when desktop view fails

### `export.py`
- **Purpose**: Data export utilities
- **Key Functions**:
  - `export_new_since_run()` - Export incremental data
  - `export_price_history()` - Export price tracking data
  - `save_output_rows()` - CSV/Excel export functionality

### `fb_marketplace_scraper.py`
- **Purpose**: CLI interface and main orchestration
- **Responsibilities**: Argument parsing, logging setup, database operations, export coordination

## Usage

The refactored scraper maintains the same CLI interface:

```bash
python scraper/fb_marketplace_scraper.py --lat 13.7563 --lon 100.5018 --radius-km 50 --category all --max-items 200 --details --db data/db/fb_marketplace.db --out data/export.xlsx
```

## Architecture Benefits

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Testability**: Individual components can be tested in isolation
3. **Reusability**: Modules can be imported and used independently
4. **Maintainability**: Changes to scraping logic don't affect database operations
5. **Extensibility**: Easy to add new data sources or export formats

## Key Design Patterns

- **Dataclass Models**: Type-safe data structures with clear field definitions
- **Context Managers**: Proper resource management for database connections
- **Async/Await**: Playwright integration with proper error handling
- **Configurable Logging**: Separate console and file logging levels
- **Incremental Loading**: Efficient database updates with change detection

## Testing

Run the module tests to verify the structure:

```bash
python scraper/test_modules.py
```

This validates imports and basic functionality across all modules.