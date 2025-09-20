
# FBMkt — Facebook Marketplace Scraper + API

**Step 2 — Scraper (Playwright + SQLite + price history).**  
This step includes: scraper code, dependencies, Dockerfile, and entrypoint.

---

## Quick start (locally, without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scraper/requirements.txt
python -m playwright install

# First run may require login to Facebook (in headful mode).
# After logging in, return to the console and press Enter.

python scraper/fb_marketplace_scraper.py   --lat 13.7563 --lon 100.5018 --radius-km 50   --category all --max-items 200 --details   --db data/db/fb_marketplace.db --out data/export.xlsx
```

---

## Environment variables (used in Docker)

Copy `.env.example` → `.env` and set:

- `LAT`, `LON`, `RADIUS_KM`, `CATEGORY`, `QUERY`, `MAX_ITEMS`  
- `DETAILS`, `HEADLESS`  
- `DB_PATH=/data/db/fb_marketplace.db`  
- `STORAGE_STATE_FILE=/data/auth/storage_state.json`  
- (optional) `EXPORT_NEW`, `EXPORT_PRICES`, `EXPORT_PRICES_ITEM`, `OUT_PATH`  

---

## Features of the scraper

- Incremental loading into SQLite (`listings` + `price_history`)  
- Second pass through listing pages to extract detailed info  
- Export of new items and/or price history  

---

## Commands (after Step 4 we’ll add docker-compose)

- Local run: see example above.  
- With containers (after Step 4):  
  ```bash
  docker compose run --rm --env-file .env scraper
  ```  

---

## License

MIT — see LICENSE.  
