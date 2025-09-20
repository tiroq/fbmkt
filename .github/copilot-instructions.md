# AI Coding Instructions for FBMkt

## Project Overview
FBMkt is a Facebook Marketplace scraper with API endpoints. The system consists of two main components:
- **Scraper**: Playwright-based web scraper that collects marketplace listings into SQLite
- **API**: FastAPI server that serves the scraped data via REST endpoints and web UI

## Architecture & Data Flow

### Core Components
- `scraper/fb_marketplace_scraper.py`: Main scraper using Playwright, stores data in SQLite with incremental loading
- `api/app.py`: FastAPI server with REST endpoints and HTML table views
- `data/db/fb_marketplace.db`: SQLite database with `listings` and `price_history` tables
- `data/auth/storage_state.json`: Facebook authentication state for headless scraping

### Data Model
The `Listing` dataclass (line 110+ in scraper) defines the core schema:
- Vehicle-specific fields: `year`, `mileage_km`, `fuel`, `transmission`, `body_type`, `brand`, `model`
- Price parsing with `parse_price()` function extracts numeric values and currency symbols (฿/$)
- Location data includes lat/lon coordinates and text descriptions

## Development Workflows

### Local Development
```bash
# Scraper setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r scraper/requirements.txt
playwright install

# First run requires Facebook login (headful mode)
python scraper/fb_marketplace_scraper.py --lat 13.7563 --lon 100.5018 --radius-km 50 --category all --max-items 200 --details --db data/db/fb_marketplace.db --out data/export.xlsx

# API server
cd api && uvicorn app:app --reload --port 8000
```

### Docker Workflow (Current State)
- `make build`: Builds Docker images
- `make scrape`: Runs scraper container with `.env` file
- `make up/down`: Manages API container
- **Note**: docker-compose.yml doesn't exist yet (mentioned as "Step 4" in README)

## Project-Specific Patterns

### Environment Configuration
The scraper uses environment variables primarily through `entrypoint.sh`:
- Required: `LAT`, `LON` for geographic targeting
- Optional: `RADIUS_KM`, `CATEGORY`, `QUERY`, `MAX_ITEMS`, `HEADLESS`
- Paths: `DB_PATH`, `STORAGE_STATE_FILE`, `OUT_PATH`

### Error Handling & Logging
- Custom logger in `init_logger()` with both console and file output
- Price parsing gracefully handles multiple currencies and formats
- Text cleaning with `clean_text()` normalizes whitespace

### Database Integration
- SQLite database with context manager pattern in `get_conn()` (api/app.py:26)
- API endpoints support filtering by price range, category, and text search
- Price history tracking for items over time

### Testing & Quality
- No formal test suite currently exists
- Manual testing via `make scrape` and API endpoints at `/docs`

## Critical Integration Points

### Facebook Authentication
- First run requires interactive login (headful mode)
- Subsequent runs use stored `storage_state.json` for headless operation
- Session state persists between scraper runs

### API Endpoints Structure
- `/`: HTML table view with filtering
- `/api/listings`: JSON listings with query params
- `/api/listings/{item_id}`: Individual item details
- `/api/price-history/{item_id}`: Price changes over time
- `/export.csv`: CSV export with same filtering as listings

## Development Notes
- Project appears to be in early stages ("Step 2" mentioned in README)
- Future plans include docker-compose setup and login tools (`tools/login_once.py`)
- Makefile contains Russian comments indicating international development
- Vehicle-focused but designed for extensibility to other categories