"""
Playwright-based scraping logic for Facebook Marketplace.
"""
import asyncio
import json
import os
import random
import re
from typing import List, Dict, Set, Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from .models import Listing
from .utils import clean_text, parse_price, to_float, extract_first_number_km


# Constants
STORAGE_STATE_FILE_DEFAULT = "storage_state.json"
NO_GROWTH_SCROLLS_LIMIT = 4
DETAIL_WAIT_SEL = "[data-pagelet='MarketplacePDP']"


async def ensure_marketplace_ready(page, timeout_ms: int = 15000) -> bool:
    """Ensure marketplace page is ready and handle cookie/consent banners."""
    # Try to close cookie/consent banners in different locales
    selectors = [
        "button:has-text('Allow all cookies')",
        "button:has-text('Accept all')",
        "button:has-text('Разрешить все')",
        "button:has-text('Принять все')",
        "div[role='dialog'] button:has-text('OK')",
    ]
    for sel in selectors:
        try:
            if await page.locator(sel).first.is_visible():
                await page.locator(sel).first.click(timeout=2000)
                break
        except Exception:
            pass

    # Wait for marketplace items to load
    try:
        await page.wait_for_selector("a[href*='/marketplace/item/']", timeout=timeout_ms, state="visible")
        return True
    except Exception:
        return False


async def extract_cards_on_page(page) -> List[Dict]:
    """Extract listing cards from current marketplace page."""
    item_loc = page.locator("[data-testid='marketplace_feed_item']")
    count = await item_loc.count()
    raw = []
    
    if count == 0:
        # Fallback: direct anchor collection - FB DOM changes frequently
        anchors = page.locator("a[href*='/marketplace/item/']").filter(has_text=re.compile(r".+"))
        ac = await anchors.count()
        print(f">>> Fallback: found {ac} anchors with /marketplace/item/")
        
        for i in range(min(ac, 200)):
            a = anchors.nth(i)
            href = await a.get_attribute("href") or ""
            # Try to extract text for title
            title_guess = clean_text((await a.get_attribute("aria-label")) or (await a.inner_text()) or "")
            # Look for nearest image as thumbnail
            thumb = ""
            try:
                img = a.locator("img")
                if await img.count() > 0:
                    src = await img.first.get_attribute("src")
                    if src and src.startswith("http"):
                        thumb = src
            except Exception:
                pass
            
            if href:
                raw.append({
                    "href": href,
                    "title_guess": title_guess[:220],
                    "price_text": "",          # price will be clarified in details
                    "location_text": "",
                    "posted_text": "",
                    "seller_text": "",
                    "thumb": thumb
                })
        print(f">>> Fallback produced {len(raw)} raw items")
        return raw
    
    print(f">>> Found {count} item cards on the page")
    for i in range(count):
        it = item_loc.nth(i)
        href = ""
        links = it.locator("a[href*='/marketplace/item/']")
        if await links.count() > 0:
            href = await links.nth(0).get_attribute("href") or ""
        else:
            hrefs = await it.get_by_role("link").all()
            for l in hrefs:
                h = await l.get_attribute("href")
                if h and "/marketplace/item/" in h:
                    href = h
                    break

        full_text = clean_text(await it.inner_text())
        price_text = ""
        m = re.search(r"([฿$€£]\s?\d[\d,\.]*)", full_text)
        if m:
            price_text = m.group(1)

        lines = [clean_text(x) for x in re.split(r"[\\n\\r]+", full_text) if clean_text(x)]
        location_text = ""
        posted_text = ""
        seller_text = ""
        title_guess = ""
        
        for line in lines:
            if not posted_text and re.search(r"(minutes?|hours?|days?) ago|только что|час(а|ов) назад", line, re.I):
                posted_text = line
                continue
            if not location_text and re.search(r"(Bangkok|Hua Hin|Pattaya|Phuket|Thailand|Бангкок|Хуахин|Паттайя|Пхукет)", line, re.I):
                location_text = line
                continue
            if not seller_text and re.search(r"(Seller|Продавец|by\s)", line, re.I):
                seller_text = line
                continue
        
        candidates = [l for l in lines if l not in (price_text, location_text, posted_text, seller_text) and len(l) > 0]
        if candidates:
            title_guess = max(candidates, key=len)[:220]
        
        thumb = ""
        imgs = it.locator("img")
        if await imgs.count() > 0:
            for k in range(min(5, await imgs.count())):
                src = await imgs.nth(k).get_attribute("src")
                if src and src.startswith("http"):
                    thumb = src
                    break
        
        raw.append({
            "href": href,
            "title_guess": title_guess,
            "price_text": price_text,
            "location_text": location_text,
            "posted_text": posted_text,
            "seller_text": seller_text,
            "thumb": thumb
        })
    
    return raw


def normalize_listing(source_url: str, row: Dict, category_hint: str) -> Optional[Listing]:
    """Convert raw extracted data to Listing object."""
    href = row.get("href") or ""
    if not href or "/marketplace/item/" not in href:
        return None
    
    if href.startswith("/"):
        item_url = "https://www.facebook.com" + href
    elif href.startswith("http"):
        item_url = href
    else:
        item_url = f"https://www.facebook.com{href}"
    
    m = re.search(r"/item/(\d+)", item_url)
    item_id = m.group(1) if m else item_url
    price_val, price_cur = parse_price(row.get("price_text", ""))
    
    return Listing(
        source_url=source_url,
        item_url=item_url,
        item_id=item_id,
        title=row.get("title_guess", ""),
        price_text=row.get("price_text", ""),
        location_text=row.get("location_text", ""),
        thumbnail_url=row.get("thumb", ""),
        seller_text=row.get("seller_text", ""),
        posted_text=row.get("posted_text", ""),
        category_hint=category_hint,
        price_value=price_val,
        price_currency=price_cur
    )


async def scroll_and_collect(page, target_count: int, category_hint: str, source_url: str) -> List[Listing]:
    """Scroll marketplace page and collect listings until target count reached."""
    seen_ids: Set[str] = set()
    results: List[Listing] = []
    no_growth = 0
    
    while len(results) < target_count:
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            # On heavy pages, networkidle may not occur - simplify waiting
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            await asyncio.sleep(random.uniform(1.2, 2.5))
        
        probe_cards = await page.locator("a[href*='/marketplace/item/']").count()
        if probe_cards == 0:
            for _ in range(3):
                try:
                    await page.evaluate("window.scrollBy(0, Math.min(1200, document.body.scrollHeight))")
                except Exception:
                    break
                await asyncio.sleep(random.uniform(0.6, 1.0))
        
        raw_cards = await extract_cards_on_page(page)
        added = 0
        
        for r in raw_cards:
            listing = normalize_listing(source_url, r, category_hint)
            if not listing:
                continue
            
            key = listing.item_id
            if key and key not in seen_ids:
                seen_ids.add(key)
                results.append(listing)
                added += 1
                print(f"Found item: {listing.item_id} | {listing.title} | {listing.price_text} | {listing.location_text} | {listing.posted_text} | {listing.seller_text} | {listing.item_url}")
        
        if added == 0:
            no_growth += 1
        else:
            no_growth = 0
        
        if no_growth >= NO_GROWTH_SCROLLS_LIMIT:
            break
        
        try:
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        except Exception:
            # If the page suddenly crashes, exit to let the outside retry work
            break
        
        await asyncio.sleep(random.uniform(1.0, 2.5))
    
    return results


async def extract_details_from_item(page, listing: Listing, timeout_ms: int = 25_000) -> Listing:
    """Extract detailed information from individual listing page."""
    try:
        await page.goto(listing.item_url, timeout=timeout_ms)
        await page.wait_for_selector(DETAIL_WAIT_SEL, timeout=timeout_ms)
        await asyncio.sleep(random.uniform(1.5, 3.0))
    except PlaywrightTimeout:
        return listing

    # Extract description
    description = ""
    try:
        desc_candidates = page.locator(f"{DETAIL_WAIT_SEL} div[role='article'], {DETAIL_WAIT_SEL} div[data-ad-preview='message']")
        if await desc_candidates.count() > 0:
            texts = []
            for i in range(await desc_candidates.count()):
                texts.append(clean_text(await desc_candidates.nth(i).inner_text()))
            description = max(texts, key=len) if texts else ""
    except:
        pass

    # Extract key-value attributes
    attributes_kv: Dict[str, str] = {}
    try:
        nodes = page.locator(f"{DETAIL_WAIT_SEL} li, {DETAIL_WAIT_SEL} div")
        cnt = min(await nodes.count(), 600)
        for i in range(cnt):
            tx = clean_text(await nodes.nth(i).inner_text())
            if not tx or len(tx) > 200:
                continue
            m = re.match(r"([A-Za-zА-Яа-яёЁ\/\-\s]+):?\s+(.+)$", tx)
            if m:
                k = clean_text(m.group(1))
                v = clean_text(m.group(2))
                if 2 <= len(k) <= 30 and 1 <= len(v) <= 120:
                    if k.lower() not in {"see details", "details", "more", "info", "about"}:
                        attributes_kv[k] = v
    except:
        pass

    # Extract image URLs
    img_urls: List[str] = []
    try:
        imgs = page.locator(f"{DETAIL_WAIT_SEL} img")
        n = await imgs.count()
        for i in range(min(n, 40)):
            src = await imgs.nth(i).get_attribute("src")
            if src and src.startswith("http") and "safe_image.php" not in src:
                if src not in img_urls:
                    img_urls.append(src)
    except:
        pass

    # Extract coordinates
    lat = lon = None
    try:
        html = await page.content()
        m1 = re.search(r'\"latitude\"\\s*:\\s*([\\-]?\\d{1,3}\\.\\d+).{0,80}\"longitude\"\\s*:\\s*([\\-]?\\d{1,3}\\.\\d+)', html)
        if m1:
            lat = to_float(m1.group(1))
            lon = to_float(m1.group(2))
        else:
            m2 = re.search(r"""[\"\\']lat[\"\\']\\s*[:=]\\s*([\\-]?\\d{1,3}\\.\\d+).{0,80}[\"\\'](lon|long|lng)[\"\\']\\s*[:=]\\s*([\\-]?\\d{1,3}\\.\\d+)""", html)
            if m2:
                lat = to_float(m2.group(1))
                lon = to_float(m2.group(3))
    except:
        pass

    # Process extracted data for vehicle attributes
    listing = _extract_vehicle_attributes(listing, description, attributes_kv)
    
    # Update listing with extracted details
    listing.description = description
    listing.attributes_kv = attributes_kv
    listing.img_urls = img_urls
    listing.latitude = lat
    listing.longitude = lon

    # Try to get better price from detail page
    try:
        price_node = page.locator(f"{DETAIL_WAIT_SEL} span, {DETAIL_WAIT_SEL} div")
        best = ""
        for i in range(min(await price_node.count(), 300)):
            t = clean_text(await price_node.nth(i).inner_text())
            if re.search(r"[฿$€£]\s?\d", t):
                best = t
                break
        if best:
            pv, pc = parse_price(best)
            if pv is not None:
                listing.price_value = pv
            if pc:
                listing.price_currency = pc
    except:
        pass

    return listing


def _extract_vehicle_attributes(listing: Listing, description: str, attributes_kv: Dict[str, str]) -> Listing:
    """Extract vehicle-specific attributes from text and structured data."""
    title = listing.title or ""
    text_pool = " ".join([title, description, " ".join([f"{k} {v}" for k, v in attributes_kv.items()])])

    def pick_year(s: str) -> Optional[int]:
        cand = re.findall(r"\b(19[89]\d|20[0-3]\d)\b", s)
        for c in cand:
            y = int(c)
            if 1980 <= y <= 2035:
                return y
        return None

    def pick_transmission(s: str) -> str:
        if re.search(r"\b(auto(matic)?|AT|АКПП)\b", s, re.I):
            return "Automatic"
        if re.search(r"\b(manual|MT|МКПП)\b", s, re.I):
            return "Manual"
        return ""

    def pick_fuel(s: str) -> str:
        if re.search(r"\b(diesel|дизель)\b", s, re.I):
            return "Diesel"
        if re.search(r"\b(petrol|gasoline|бензин|gas)\b", s, re.I):
            return "Petrol"
        if re.search(r"\b(hybrid)\b", s, re.I):
            return "Hybrid"
        if re.search(r"\b(EV|electric|электро)\b", s, re.I):
            return "Electric"
        return ""

    def pick_body(s: str) -> str:
        for bt in ["Sedan", "Hatchback", "SUV", "Pickup", "Wagon", "Coupe", "Convertible", "Van", "MPV", "Crossover", "Scooter", "Sportbike", "Cruiser", "Adventure"]:
            if re.search(rf"\b{bt}\b", s, re.I):
                return bt
        return ""

    # Extract year
    year = None
    for k, v in attributes_kv.items():
        if k.lower() in {"year", "год"}:
            y = re.findall(r"\b(19[89]\d|20[0-3]\d)\b", v)
            if y:
                year = int(y[0])
    if not year:
        year = pick_year(text_pool)

    # Extract mileage
    mileage_km = extract_first_number_km(text_pool)

    # Extract transmission
    transmission = ""
    for k, v in attributes_kv.items():
        if k.lower() in {"transmission", "коробка", "трансмиссия"}:
            transmission = clean_text(v)
            break
    if not transmission:
        transmission = pick_transmission(text_pool)

    # Extract fuel type
    fuel = ""
    for k, v in attributes_kv.items():
        if k.lower() in {"fuel type", "топливо"}:
            fuel = clean_text(v)
            break
    if not fuel:
        fuel = pick_fuel(text_pool)

    # Extract body type
    body_type = ""
    for k, v in attributes_kv.items():
        if k.lower() in {"body", "body type", "тип кузова"}:
            body_type = clean_text(v)
            break
    if not body_type:
        body_type = pick_body(text_pool)

    # Extract brand and model
    brand = ""
    known_brands = [
        "Toyota", "Honda", "Nissan", "Mazda", "Mitsubishi", "Suzuki", "Isuzu", "Subaru", "Hyundai", "Kia",
        "Ford", "Chevrolet", "BMW", "Mercedes", "Audi", "Volkswagen", "Skoda", "Volvo", "Peugeot", "Renault",
        "Yamaha", "Kawasaki", "Ducati", "Harley", "Triumph", "Royal Enfield", "Benelli", "CFMoto", "KTM", "Vespa", "Piaggio", "SYM", "Kymco", "Husqvarna"
    ]
    for b in known_brands:
        if re.search(rf"\b{re.escape(b)}\b", title, re.I):
            brand = b
            break
    
    model = ""
    if brand:
        m = re.search(rf"{re.escape(brand)}\s+([A-Za-z0-9\-]+)", title, re.I)
        if m:
            model = m.group(1)

    # Update listing attributes
    listing.year = year
    listing.mileage_km = mileage_km
    listing.fuel = fuel
    listing.transmission = transmission
    listing.body_type = body_type
    listing.brand = brand
    listing.model = model

    return listing