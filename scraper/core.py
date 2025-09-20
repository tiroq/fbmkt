"""
Core scraping orchestration and browser management.
"""
import asyncio
import os
import random
from typing import List, Optional, Dict

from playwright.async_api import async_playwright

from models import Listing
from scraper import (
    ensure_marketplace_ready, 
    scroll_and_collect, 
    extract_details_from_item,
    STORAGE_STATE_FILE_DEFAULT
)
from utils import build_urls


async def run_scrape(
    lat: float, 
    lon: float, 
    radius_km: int, 
    query: Optional[str],
    category: str, 
    max_items: int, 
    headless: bool,
    details: bool, 
    details_concurrency: int,
    storage_state_path: Optional[str],
    logger=None
) -> List[Listing]:
    """
    Main scraping orchestration function.
    
    Manages browser lifecycle, handles authentication, and coordinates
    the scraping of marketplace listings across multiple URLs.
    """
    urls = build_urls(lat, lon, radius_km, query, category)
    all_results: Dict[str, Listing] = {}
    is_headless = bool(headless) or os.getenv("HEADLESS", "").strip().lower() in ("1", "true")
    
    launch_args = ["--disable-blink-features=AutomationControlled"]
    if is_headless:
        launch_args += ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"]

    async with async_playwright() as p:
        # Configure browser launch
        if not is_headless:
            browser = await p.chromium.launch(
                headless=False,
                channel="chrome",          # Opens Chrome.app specifically
                args=launch_args,
                slow_mo=150,               # Slight slowdown for visibility
            )
            if logger:
                logger.info(">>> Headless mode disabled")
        else:
            browser = await p.chromium.launch(
                headless=True,
                args=launch_args,
            )
            if logger:
                logger.info(">>> Headless mode enabled")
        
        # Setup browser context
        ctx_kwargs = {}
        if storage_state_path and os.path.exists(storage_state_path):
            ctx_kwargs["storage_state"] = storage_state_path
            if logger:
                logger.info(f">>> Using existing storage state: {storage_state_path}")
        
        context = await browser.new_context(
            **ctx_kwargs,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        context.set_default_timeout(30_000)
        context.set_default_navigation_timeout(45_000)

        page = await context.new_page()
        if logger:
            logger.info(f">>> Opening page: {page.url}")
        
        try:
            await page.bring_to_front()   # Bring window to foreground
        except Exception:
            pass
        
        if logger:
            logger.info(f">>> Headless mode: {is_headless}")

        # Handle first-time authentication
        if not storage_state_path or not os.path.exists(storage_state_path):
            if logger:
                logger.info(">>> First run: Please log in to Facebook and return to the console, then press Enter.")
            else:
                print(">>> First run: Please log in to Facebook and return to the console, then press Enter.")
            
            await page.goto("https://www.facebook.com/login", timeout=120_000)
            try:
                input()
            except EOFError:
                pass
            
            if storage_state_path:
                await context.storage_state(path=storage_state_path)

        # Scrape each URL
        for u in urls:
            if logger:
                logger.info(f">>> Opening catalog: {u}")
            
            try:
                await page.goto(u, timeout=120_000, wait_until="domcontentloaded")
            except Exception:
                # Recreate page if crashed
                if page.is_closed():
                    page = await context.new_page()
                await page.goto(u, timeout=120_000, wait_until="domcontentloaded")
            
            ready = await ensure_marketplace_ready(page, timeout_ms=15_000)
            if not ready:
                # If desktop version gave no cards - try mobile m.facebook.com
                try:
                    u_mobile = u.replace("://www.facebook.com", "://m.facebook.com")
                    if logger:
                        logger.info(f">>> Desktop view empty; retry mobile: {u_mobile}")
                    else:
                        print(f">>> Desktop view empty; retry mobile: {u_mobile}")
                    
                    await page.goto(u_mobile, timeout=120_000, wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(1.2, 2.2))
                    ready = await ensure_marketplace_ready(page, timeout_ms=10_000)
                except Exception:
                    if logger:
                        logger.exception("Failed to open mobile Marketplace")

            await asyncio.sleep(random.uniform(1.0, 2.0))

            batch: List[Listing] = []

            # Soft retry in case of crash during scrolling
            for attempt in range(2):
                try:
                    batch = await scroll_and_collect(
                        page, target_count=max_items, category_hint=category, source_url=u
                    )
                    if logger:
                        logger.info(f">>> Collected {len(batch)} items from this URL")
                    else:
                        print(f">>> Collected {len(batch)} items from this URL")
                    break
                except Exception:
                    if page.is_closed():
                        page = await context.new_page()
                        await page.goto(u, timeout=120_000, wait_until="domcontentloaded")
                    if attempt == 1:
                        raise
            
            for b in batch:
                all_results[b.item_id] = b
            
            if len(all_results) >= max_items:
                break

        listings = list(all_results.values())[:max_items]

        # Second pass for detailed information
        if details and listings:
            if logger:
                logger.info(f">>> Second pass over {len(listings)} listings...")
            else:
                print(f">>> Second pass over {len(listings)} listings...")
            
            for i, lst in enumerate(listings, 1):
                try:
                    listings[i-1] = await extract_details_from_item(page, lst)
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.8, 1.2))

        await context.close()
        await browser.close()

    return listings