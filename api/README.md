# 🚀 FB Marketplace API - Quick Start Guide

## Running the API with Virtual Environment

### Prerequisites
```bash
# Make sure you're in the project root
cd /Users/mysterx/Documents/GitHub/fbmkt

# Virtual environment should be activated (or use full path)
source .venv/bin/activate
```

### Start the API Server
```bash
# Navigate to API directory
cd api

# Option 1: Using full path to venv python (recommended)
/Users/mysterx/Documents/GitHub/fbmkt/.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Option 2: With activated venv
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Option 3: Using uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 🌐 Access Points

| URL | Description |
|-----|-------------|
| http://localhost:8000 | Main API homepage |
| http://localhost:8000/docs | Interactive API documentation (Swagger) |
| http://localhost:8000/redoc | Alternative API documentation |
| http://localhost:8000/ui/table | HTML table view of listings |
| http://localhost:8000/ui/stats | Statistics dashboard |

## 📋 API Endpoints

### Data Endpoints
- `GET /api/listings` - Get all listings with filtering
- `GET /api/listings/{item_id}` - Get specific listing
- `GET /api/price-history/{item_id}` - Get price history for item
- `GET /api/stats` - Get database statistics

### UI Endpoints  
- `GET /` - Homepage with navigation
- `GET /ui/table` - HTML table view with filtering
- `GET /ui/stats` - Statistics dashboard

### Export
- `GET /export.csv` - Export listings as CSV

## 🔧 Configuration

The API uses these environment variables:
- `FB_DB` - Database path (default: `../data/db/fb_marketplace.db`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## 🧪 Testing the API

### Quick Test
```bash
# Test basic endpoint
curl http://localhost:8000/api/stats

# Test with browser
open http://localhost:8000/docs
```

### Stop the Server
Press `Ctrl+C` in the terminal where uvicorn is running.

## ✅ Success Indicators

When running correctly, you should see:
```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```