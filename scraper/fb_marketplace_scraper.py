
"""
Facebook Marketplace Scraper - Main CLI interface.

Refactored for better maintainability and clear architecture.
"""
import argparse
import asyncio
import os

from core import run_scrape
from database import db_connect, db_init, upsert_with_price_history
from export import export_new_since_run, export_price_history, save_output_rows
from utils import init_logger, now_iso

STORAGE_STATE_FILE_DEFAULT = "storage_state.json"

def parse_args():
    """Parse command line arguments."""
    ap = argparse.ArgumentParser(description="Facebook Marketplace scraper (vehicles/motorcycles) with SQLite & price history")
    ap.add_argument("--lat", type=float, required=True, help="Latitude")
    ap.add_argument("--lon", type=float, required=True, help="Longitude")
    ap.add_argument("--radius-km", type=int, default=50, help="Radius in km")
    ap.add_argument("--query", type=str, default="", help="Query, e.g. 'Honda'")
    ap.add_argument("--category", choices=["vehicles","motorcycles","all"], default="all", help="Search category")
    ap.add_argument("--max-items", type=int, default=300, help="Maximum items to collect")
    ap.add_argument("--headless", action="store_true", help="Run without UI")
    ap.add_argument("--details", action="store_true", help="Collect details from the listing page")
    ap.add_argument("--details-concurrency", type=int, default=1, help="Pseudo-concurrency for details (leave as 1)")
    ap.add_argument("--db", type=str, default="fb_marketplace.db", help="Path to SQLite DB")
    ap.add_argument("--export-new", action="store_true", help="Export only new items since the current run")
    ap.add_argument("--out", type=str, default="fb_marketplace_export.xlsx", help="CSV/XLSX to export (used with --export-new or --export-prices)")
    ap.add_argument("--export-prices", action="store_true", help="Export price_history to CSV/XLSX (uses --out)")
    ap.add_argument("--export-prices-item", type=str, default="", help="Filter price_history by item_id")
    ap.add_argument("--storage-state", type=str, default=STORAGE_STATE_FILE_DEFAULT, help="Path to storage_state.json")
    # Logging
    lvl_choices = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    ap.add_argument("--log-level", choices=lvl_choices, default=None,
                    help="Global log level for both console and file (overrides --log-console/--log-file).")
    ap.add_argument("--log-console", choices=lvl_choices, default=os.getenv("LOG_CONSOLE", "INFO"),
                    help="Console log level (default from env LOG_CONSOLE or INFO).")
    ap.add_argument("--log-file", choices=lvl_choices, default=os.getenv("LOG_FILE", "DEBUG"),
                    help="File log level (default from env LOG_FILE or DEBUG).")
    ap.add_argument("--log-file-path", default=os.getenv("LOG_FILE_PATH", "fbmkt.log"),
                    help="Path to log file (default from env LOG_FILE_PATH or fbmkt.log).")
    ap.add_argument("--no-file-log", action="store_true",
                help="Disable file logging (only console output).")

    return ap.parse_args()


def main():
    """Main CLI entry point."""
    args = parse_args()
    eff_console = args.log_level or args.log_console
    eff_file = args.log_level or args.log_file
    
    global logger
    logger = init_logger(
        console_level=eff_console,
        file_level=eff_file,
        log_file=None if args.no_file_log else args.log_file_path
    )
    logger.info(
        f"Logger initialized: console={eff_console}, "
        f"file={'DISABLED' if args.no_file_log else eff_file}, "
        f"path={'N/A' if args.no_file_log else args.log_file_path}"
    )
    
    run_started_iso = now_iso()
    logger.info(f">>> Run started at {run_started_iso}")

    # Run the scraping
    listings = asyncio.run(run_scrape(
        lat=args.lat, 
        lon=args.lon, 
        radius_km=args.radius_km,
        query=args.query if args.query.strip() else None,
        category=args.category, 
        max_items=args.max_items,
        headless=args.headless, 
        details=args.details, 
        details_concurrency=args.details_concurrency,
        storage_state_path=args.storage_state,
        logger=logger
    ))

    # Database operations
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    conn = db_connect(args.db)
    db_init(conn)

    new_items = 0
    price_changed_count = 0
    for lst in listings:
        is_new, price_changed = upsert_with_price_history(conn, lst)
        if is_new:
            new_items += 1
        if price_changed:
            price_changed_count += 1
    logger.info(f">>> In DB: new items added: {new_items}, price changes: {price_changed_count}")

    # Export operations
    if args.export_prices:
        dfp = export_price_history(conn, item_id=args.export_prices_item or None)
        if args.out.lower().endswith(".xlsx"):
            dfp.to_excel(args.out, index=False)
        else:
            dfp.to_csv(args.out, index=False)
        logger.info(f">>> Export price_history: {len(dfp)} rows -> {args.out}")
    else:
        if args.export_new:
            dfn = export_new_since_run(conn, run_started_iso)
            if args.out.lower().endswith(".xlsx"):
                dfn.to_excel(args.out, index=False)
            else:
                dfn.to_csv(args.out, index=False)
            logger.info(f">>> Export only new items: {len(dfn)} rows -> {args.out}")
        else:
            save_output_rows(listings, args.out, logger)

    conn.close()


if __name__ == "__main__":
    main()
