
import argparse
import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Set, Optional, Tuple

import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

MARKETPLACE_BASE = "https://www.facebook.com/marketplace"
STORAGE_STATE_FILE_DEFAULT = "storage_state.json"
NO_GROWTH_SCROLLS_LIMIT = 4
DETAIL_WAIT_SEL = "[data-pagelet='MarketplacePDP']"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def parse_price(price_text: str) -> Tuple[Optional[float], Optional[str]]:
    if not price_text:
        return (None, None)
    s = price_text.replace(",", "").replace("\xa0", " ")
    m = re.search(r"(฿|\$|€|£)?\s?(\d+(?:\.\d+)?)", s)
    cur = None
    val = None
    if m:
        cur = m.group(1)
        try:
            val = float(m.group(2))
        except ValueError:
            val = None
    if not cur:
        m2 = re.search(r"\b(THB|USD|EUR|GBP)\b", s, re.I)
        if m2:
            cur = m2.group(1).upper()
    symbol_map = {"฿": "THB", "$": "USD", "€": "EUR", "£": "GBP"}
    if cur in symbol_map:
        cur = symbol_map[cur]
    return (val, cur)

def to_float(text: str) -> Optional[float]:
    if not text:
        return None
    try:
        return float(text)
    except:
        return None

def extract_first_number_km(text: str) -> Optional[int]:
    if not text:
        return None
    t = text.replace(",", " ")
    m = re.search(r"(\d[\d\s]{1,12})\s?(км|km)\b", t, re.I)
    if m:
        num = re.sub(r"\s+", "", m.group(1))
        try:
            return int(num)
        except:
            return None
    m2 = re.search(r"\b(\d{4,7})\b", t)
    if m2:
        try:
            return int(m2.group(1))
        except:
            return None
    return None

@dataclass
class Listing:
    source_url: str
    item_url: str
    item_id: str
    title: str
    price_text: str
    location_text: str
    thumbnail_url: str
    seller_text: str
    posted_text: str
    category_hint: str
    # details
    description: str = ""
    attributes_kv: Dict[str, str] = field(default_factory=dict)
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: str = ""
    transmission: str = ""
    body_type: str = ""
    brand: str = ""
    model: str = ""
    img_urls: List[str] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    price_value: Optional[float] = None
    price_currency: Optional[str] = None

def build_urls(lat: float, lon: float, radius_km: int, query: Optional[str], category: str) -> List[str]:
    params_geo = f"exact=false&latitude={lat}&longitude={lon}&radius_km={radius_km}"
    urls = []
    if category in ("vehicles", "all"):
        urls.append(f"{MARKETPLACE_BASE}/category/vehicles?{params_geo}")
    if category in ("motorcycles", "all"):
        urls.append(f"{MARKETPLACE_BASE}/category/motorcycles?{params_geo}")
    if query:
        q = re.sub(r\"\\s+\", \"%20\", query.strip())
        urls.append(f\"{MARKETPLACE_BASE}/search/?query={q}&{params_geo}\")
    uniq, seen = [], set()
    for u in urls:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return uniq

async def extract_cards_on_page(page) -> List[Dict]:
    item_loc = page.locator(\"[data-testid='marketplace_feed_item']\")
    count = await item_loc.count()
    raw = []
    for i in range(count):
        it = item_loc.nth(i)
        href = \"\"
        links = it.locator(\"a[href*='/marketplace/item/']\")
        if await links.count() > 0:
            href = await links.nth(0).get_attribute(\"href\") or \"\"
        else:
            hrefs = await it.get_by_role(\"link\").all()
            for l in hrefs:
                h = await l.get_attribute(\"href\")
                if h and \"/marketplace/item/\" in h:
                    href = h; break

        full_text = clean_text(await it.inner_text())
        price_text = \"\"
        m = re.search(r\"([฿$€£]\\s?\\d[\\d,\\.]*)\", full_text)
        if m: price_text = m.group(1)

        lines = [clean_text(x) for x in re.split(r\"[\\n\\r]+\", full_text) if clean_text(x)]
        location_text = \"\"; posted_text = \"\"; seller_text = \"\"; title_guess = \"\"
        for line in lines:
            if not posted_text and re.search(r\"(minutes?|hours?|days?) ago|только что|час(а|ов) назад\", line, re.I):
                posted_text = line; continue
            if not location_text and re.search(r\"(Bangkok|Hua Hin|Pattaya|Phuket|Thailand|Бангкок|Хуахин|Паттайя|Пхукет)\", line, re.I):
                location_text = line; continue
            if not seller_text and re.search(r\"(Seller|Продавец|by\\s)\", line, re.I):
                seller_text = line; continue
        candidates = [l for l in lines if l not in (price_text, location_text, posted_text, seller_text) and len(l) > 0]
        if candidates:
            title_guess = max(candidates, key=len)[:220]
        thumb = \"\"
        imgs = it.locator(\"img\")
        if await imgs.count() > 0:
            for k in range(min(5, await imgs.count())):
                src = await imgs.nth(k).get_attribute(\"src\")
                if src and src.startswith(\"http\"):
                    thumb = src; break
        raw.append({
            \"href\": href,
            \"title_guess\": title_guess,
            \"price_text\": price_text,
            \"location_text\": location_text,
            \"posted_text\": posted_text,
            \"seller_text\": seller_text,
            \"thumb\": thumb
        })
    return raw

def normalize_listing(source_url: str, row: Dict, category_hint: str) -> Optional[Listing]:
    href = row.get(\"href\") or \"\"
    if not href or \"/marketplace/item/\" not in href:
        return None
    if href.startswith(\"/\"):
        item_url = \"https://www.facebook.com\" + href
    elif href.startswith(\"http\"):
        item_url = href
    else:
        item_url = f\"https://www.facebook.com{href}\"
    m = re.search(r\"/item/(\\d+)\", item_url)
    item_id = m.group(1) if m else item_url
    price_val, price_cur = parse_price(row.get(\"price_text\",\"\"))
    return Listing(
        source_url=source_url,
        item_url=item_url,
        item_id=item_id,
        title=row.get(\"title_guess\",\"\"),
        price_text=row.get(\"price_text\",\"\"),
        location_text=row.get(\"location_text\",\"\"),
        thumbnail_url=row.get(\"thumb\",\"\"),
        seller_text=row.get(\"seller_text\",\"\"),
        posted_text=row.get(\"posted_text\",\"\"),
        category_hint=category_hint,
        price_value=price_val,
        price_currency=price_cur
    )

async def scroll_and_collect(page, target_count: int, category_hint: str, source_url: str) -> List[Listing]:
    seen_ids: Set[str] = set()
    results: List[Listing] = []
    no_growth = 0
    while len(results) < target_count:
        await page.wait_for_load_state(\"networkidle\")
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
        if added == 0:
            no_growth += 1
        else:
            no_growth = 0
        if no_growth >= NO_GROWTH_SCROLLS_LIMIT:
            break
        await page.evaluate(\"window.scrollBy(0, document.body.scrollHeight)\")
        await asyncio.sleep(1.2)
    return results

async def extract_details_from_item(page, listing: Listing, timeout_ms: int = 25_000) -> Listing:
    try:
        await page.goto(listing.item_url, timeout=timeout_ms)
        await page.wait_for_selector(DETAIL_WAIT_SEL, timeout=timeout_ms)
        await asyncio.sleep(1.0)
    except PlaywrightTimeout:
        return listing

    description = \"\"
    try:
        desc_candidates = page.locator(f\"{DETAIL_WAIT_SEL} div[role='article'], {DETAIL_WAIT_SEL} div[data-ad-preview='message']\")
        if await desc_candidates.count() > 0:
            texts = []
            for i in range(await desc_candidates.count()):
                texts.append(clean_text(await desc_candidates.nth(i).inner_text()))
            description = max(texts, key=len) if texts else \"\"
    except:
        pass

    attributes_kv: Dict[str, str] = {}
    try:
        nodes = page.locator(f\"{DETAIL_WAIT_SEL} li, {DETAIL_WAIT_SEL} div\")
        cnt = min(await nodes.count(), 600)
        for i in range(cnt):
            tx = clean_text(await nodes.nth(i).inner_text())
            if not tx or len(tx) > 200:
                continue
            m = re.match(r\"([A-Za-zА-Яа-яёЁ\\/\\-\\s]+):?\\s+(.+)$\", tx)
            if m:
                k = clean_text(m.group(1))
                v = clean_text(m.group(2))
                if 2 <= len(k) <= 30 and 1 <= len(v) <= 120:
                    if k.lower() not in {\"see details\",\"details\",\"more\",\"info\",\"about\"}:
                        attributes_kv[k] = v
    except:
        pass

    img_urls: List[str] = []
    try:
        imgs = page.locator(f\"{DETAIL_WAIT_SEL} img\")
        n = await imgs.count()
        for i in range(min(n, 40)):
            src = await imgs.nth(i).get_attribute(\"src\")
            if src and src.startswith(\"http\") and \"safe_image.php\" not in src:
                if src not in img_urls:
                    img_urls.append(src)
    except:
        pass

    lat = lon = None
    try:
        html = await page.content()
        m1 = re.search(r'\"latitude\"\\s*:\\s*([\\-]?\\d{1,3}\\.\\d+).{0,80}\"longitude\"\\s*:\\s*([\\-]?\\d{1,3}\\.\\d+)', html)
        if m1:
            lat = to_float(m1.group(1)); lon = to_float(m1.group(2))
        else:
            m2 = re.search(r'[\"\\']lat[\"\\']\\s*[:=]\\s*([\\-]?\\d{1,3}\\.\\d+).{0,80}[\"\\'](lon|long|lng)[\"\\']\\s*[:=]\\s*([\\-]?\\d{1,3}\\.\\d+)', html)
            if m2:
                lat = to_float(m2.group(1)); lon = to_float(m2.group(3))
    except:
        pass

    title = listing.title or \"\"
    text_pool = \" \".join([title, description, \" \".join([f\"{k} {v}\" for k,v in attributes_kv.items()])])

    def pick_year(s: str) -> Optional[int]:
        cand = re.findall(r\"\\b(19[89]\\d|20[0-3]\\d)\\b\", s)
        for c in cand:
            y = int(c)
            if 1980 <= y <= 2035:
                return y
        return None

    def pick_transmission(s: str) -> str:
        if re.search(r\"\\b(auto(matic)?|AT|АКПП)\\b\", s, re.I): return \"Automatic\"
        if re.search(r\"\\b(manual|MT|МКПП)\\b\", s, re.I): return \"Manual\"
        return \"\"

    def pick_fuel(s: str) -> str:
        if re.search(r\"\\b(diesel|дизель)\\b\", s, re.I): return \"Diesel\"
        if re.search(r\"\\b(petrol|gasoline|бензин|gas)\\b\", s, re.I): return \"Petrol\"
        if re.search(r\"\\b(hybrid)\\b\", s, re.I): return \"Hybrid\"
        if re.search(r\"\\b(EV|electric|электро)\\b\", s, re.I): return \"Electric\"
        return \"\"

    def pick_body(s: str) -> str:
        for bt in [\"Sedan\",\"Hatchback\",\"SUV\",\"Pickup\",\"Wagon\",\"Coupe\",\"Convertible\",\"Van\",\"MPV\",\"Crossover\",\"Scooter\",\"Sportbike\",\"Cruiser\",\"Adventure\"]:
            if re.search(rf\"\\b{bt}\\b\", s, re.I):
                return bt
        return \"\"

    year = None
    for k, v in attributes_kv.items():
        if k.lower() in {\"year\",\"год\"}:
            y = re.findall(r\"\\b(19[89]\\d|20[0-3]\\d)\\b\", v)
            if y: year = int(y[0])
    if not year:
        year = pick_year(text_pool)

    mileage_km = extract_first_number_km(text_pool)

    transmission = \"\"
    for k,v in attributes_kv.items():
        if k.lower() in {\"transmission\",\"коробка\",\"трансмиссия\"}:
            transmission = clean_text(v); break
    if not transmission:
        transmission = pick_transmission(text_pool)

    fuel = \"\"
    for k,v in attributes_kv.items():
        if k.lower() in {\"fuel type\",\"топливо\"}:
            fuel = clean_text(v); break
    if not fuel:
        fuel = pick_fuel(text_pool)

    body_type = \"\"
    for k,v in attributes_kv.items():
        if k.lower() in {\"body\",\"body type\",\"тип кузова\"}:
            body_type = clean_text(v); break
    if not body_type:
        body_type = pick_body(text_pool)

    brand = \"\"
    known_brands = [
        \"Toyota\",\"Honda\",\"Nissan\",\"Mazda\",\"Mitsubishi\",\"Suzuki\",\"Isuzu\",\"Subaru\",\"Hyundai\",\"Kia\",
        \"Ford\",\"Chevrolet\",\"BMW\",\"Mercedes\",\"Audi\",\"Volkswagen\",\"Skoda\",\"Volvo\",\"Peugeot\",\"Renault\",
        \"Yamaha\",\"Kawasaki\",\"Ducati\",\"Harley\",\"Triumph\",\"Royal Enfield\",\"Benelli\",\"CFMoto\",\"KTM\",\"Vespa\",\"Piaggio\",\"SYM\",\"Kymco\",\"Husqvarna\"
    ]
    for b in known_brands:
        if re.search(rf\"\\b{re.escape(b)}\\b\", title, re.I):
            brand = b; break
    model = \"\"
    if brand:
        m = re.search(rf\"{re.escape(brand)}\\s+([A-Za-z0-9\\-]+)\", title, re.I)
        if m:
            model = m.group(1)

    listing.description = description
    listing.attributes_kv = attributes_kv
    listing.year = year
    listing.mileage_km = mileage_km
    listing.fuel = fuel
    listing.transmission = transmission
    listing.body_type = body_type
    listing.brand = brand
    listing.model = model
    listing.img_urls = img_urls
    listing.latitude = lat
    listing.longitude = lon

    try:
        price_node = page.locator(f\"{DETAIL_WAIT_SEL} span, {DETAIL_WAIT_SEL} div\")
        best = \"\"
        for i in range(min(await price_node.count(), 300)):
            t = clean_text(await price_node.nth(i).inner_text())
            if re.search(r\"[฿$€£]\\s?\\d\", t):
                best = t; break
        if best:
            pv, pc = parse_price(best)
            if pv is not None:
                listing.price_value = pv
            if pc:
                listing.price_currency = pc
    except:
        pass

    return listing

DDL_LISTINGS = \"\"\"
CREATE TABLE IF NOT EXISTS listings (
  item_id TEXT PRIMARY KEY,
  item_url TEXT,
  title TEXT,
  brand TEXT,
  model TEXT,
  year INTEGER,
  mileage_km INTEGER,
  fuel TEXT,
  transmission TEXT,
  body_type TEXT,
  price_text TEXT,
  price_value REAL,
  price_currency TEXT,
  location_text TEXT,
  posted_text TEXT,
  seller_text TEXT,
  thumbnail_url TEXT,
  img_urls TEXT,
  latitude REAL,
  longitude REAL,
  description TEXT,
  attributes_json TEXT,
  category_hint TEXT,
  source_url TEXT,
  first_seen TEXT,
  last_seen TEXT
);
\"\"\"

DDL_PRICE_HISTORY = \"\"\"
CREATE TABLE IF NOT EXISTS price_history (
  item_id TEXT,
  ts TEXT DEFAULT (datetime('now')),
  price_value REAL,
  price_currency TEXT,
  PRIMARY KEY (item_id, ts)
);
\"\"\"

DDL_INDEXES = [
    \"CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);\",
    \"CREATE INDEX IF NOT EXISTS idx_price_history_item ON price_history(item_id);\"
]

def db_connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(\"PRAGMA journal_mode=WAL;\")
    conn.execute(\"PRAGMA synchronous=NORMAL;\")
    return conn

def db_init(conn: sqlite3.Connection):
    conn.execute(DDL_LISTINGS)
    conn.execute(DDL_PRICE_HISTORY)
    for ddl in DDL_INDEXES:
        conn.execute(ddl)
    conn.commit()

def row_to_dict(cur, row):
    return {desc[0]: row[i] for i, desc in enumerate(cur.description)}

def db_get_listing(conn: sqlite3.Connection, item_id: str) -> Optional[Dict]:
    cur = conn.cursor()
    cur.execute(\"SELECT * FROM listings WHERE item_id = ?\", (item_id,))
    r = cur.fetchone()
    if not r:
        return None
    return row_to_dict(cur, r)

def db_insert_listing(conn: sqlite3.Connection, lst: Listing):
    cur = conn.cursor()
    cur.execute(\"\"\"
    INSERT INTO listings (
      item_id,item_url,title,brand,model,year,mileage_km,fuel,transmission,body_type,
      price_text,price_value,price_currency,location_text,posted_text,seller_text,
      thumbnail_url,img_urls,latitude,longitude,description,attributes_json,
      category_hint,source_url,first_seen,last_seen
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    \"\"\", (
        lst.item_id, lst.item_url, lst.title, lst.brand, lst.model, lst.year, lst.mileage_km,
        lst.fuel, lst.transmission, lst.body_type,
        lst.price_text, lst.price_value, lst.price_currency, lst.location_text, lst.posted_text,
        lst.seller_text, lst.thumbnail_url, \"|\".join(lst.img_urls) if lst.img_urls else \"\",
        lst.latitude, lst.longitude, lst.description, json.dumps(lst.attributes_kv, ensure_ascii=False),
        lst.category_hint, lst.source_url, now_iso(), now_iso()
    ))
    conn.commit()

def db_update_listing(conn: sqlite3.Connection, lst: Listing):
    cur = conn.cursor()
    cur.execute(\"\"\"
    UPDATE listings SET
      item_url=?, title=?, brand=?, model=?, year=?, mileage_km=?, fuel=?, transmission=?, body_type=?,
      price_text=?, price_value=?, price_currency=?, location_text=?, posted_text=?, seller_text=?,
      thumbnail_url=?, img_urls=?, latitude=?, longitude=?, description=?, attributes_json=?,
      category_hint=?, source_url=?, last_seen=?
    WHERE item_id=?
    \"\"\", (
        lst.item_url, lst.title, lst.brand, lst.model, lst.year, lst.mileage_km, lst.fuel, lst.transmission, lst.body_type,
        lst.price_text, lst.price_value, lst.price_currency, lst.location_text, lst.posted_text, lst.seller_text,
        lst.thumbnail_url, \"|\".join(lst.img_urls) if lst.img_urls else \"\", lst.latitude, lst.longitude,
        lst.description, json.dumps(lst.attributes_kv, ensure_ascii=False),
        lst.category_hint, lst.source_url, now_iso(), lst.item_id
    ))
    conn.commit()

def db_insert_price_event(conn: sqlite3.Connection, item_id: str, price_value: Optional[float], price_currency: Optional[str]):
    if price_value is None:
        return
    cur = conn.cursor()
    cur.execute(\"\"\"
    INSERT OR REPLACE INTO price_history (item_id, ts, price_value, price_currency)
    VALUES (?, datetime('now'), ?, ?)
    \"\"\", (item_id, price_value, price_currency))
    conn.commit()

def upsert_with_price_history(conn: sqlite3.Connection, lst: Listing) -> Tuple[bool, bool]:
    existing = db_get_listing(conn, lst.item_id)
    if existing is None:
        db_insert_listing(conn, lst)
        if lst.price_value is not None:
            db_insert_price_event(conn, lst.item_id, lst.price_value, lst.price_currency)
        return True, bool(lst.price_value is not None)
    else:
        old_price = existing.get(\"price_value\")
        old_cur = existing.get(\"price_currency\")
        price_changed = (lst.price_value is not None and (old_price is None or float(old_price) != float(lst.price_value) or (lst.price_currency or \"\") != (old_cur or \"\")))
        db_update_listing(conn, lst)
        if price_changed:
            db_insert_price_event(conn, lst.item_id, lst.price_value, lst.price_currency)
        return False, price_changed

async def run_scrape(lat: float, lon: float, radius_km: int, query: Optional[str],
                     category: str, max_items: int, headless: bool,
                     details: bool, details_concurrency: int,
                     storage_state_path: Optional[str]) -> List[Listing]:
    urls = build_urls(lat, lon, radius_km, query, category)
    all_results: Dict[str, Listing] = {}

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=[\"--disable-blink-features=AutomationControlled\"])
        ctx_kwargs = {}
        if storage_state_path and os.path.exists(storage_state_path):
            ctx_kwargs[\"storage_state\"] = storage_state_path
        context = await browser.new_context(**ctx_kwargs, viewport={\"width\": 1280, \"height\": 900})
        page = await context.new_page()

        if not storage_state_path or not os.path.exists(storage_state_path):
            print(\">>> Первый запуск: войдите в Facebook и вернитесь в консоль, затем нажмите Enter.\")
            await page.goto(\"https://www.facebook.com/login\", timeout=120_000)
            try:
                input()
            except EOFError:
                pass
            if storage_state_path:
                await context.storage_state(path=storage_state_path)

        for u in urls:
            print(f\">>> Открываем каталог: {u}\")
            await page.goto(u, timeout=120_000)
            await asyncio.sleep(2.0)
            batch = await scroll_and_collect(page, target_count=max_items, category_hint=category, source_url=u)
            for b in batch:
                all_results[b.item_id] = b
            if len(all_results) >= max_items:
                break

        listings = list(all_results.values())[:max_items]

        if details and listings:
            print(f\">>> Второй проход по {len(listings)} объявлениям...\")
            for i, lst in enumerate(listings, 1):
                try:
                    listings[i-1] = await extract_details_from_item(page, lst)
                except Exception:
                    pass
                await asyncio.sleep(0.8)

        await context.close()
        await browser.close()

    return listings

def export_new_since_run(conn: sqlite3.Connection, run_started_iso: str) -> pd.DataFrame:
    q = \"\"\"
    SELECT *
    FROM listings
    WHERE first_seen >= ?
    ORDER BY first_seen DESC
    \"\"\"
    df = pd.read_sql_query(q, conn, params=(run_started_iso,))
    return df

def export_price_history(conn: sqlite3.Connection, item_id: Optional[str] = None) -> pd.DataFrame:
    if item_id:
        q = \"SELECT * FROM price_history WHERE item_id=? ORDER BY ts ASC\"
        return pd.read_sql_query(q, conn, params=(item_id,))
    else:
        q = \"SELECT * FROM price_history ORDER BY item_id, ts ASC\"
        return pd.read_sql_query(q, conn)

def save_output_rows(listings: List[Listing], out_path: str):
    rows = []
    for x in listings:
        rows.append({
            \"item_id\": x.item_id,
            \"title\": x.title,
            \"brand\": x.brand,
            \"model\": x.model,
            \"year\": x.year,
            \"mileage_km\": x.mileage_km,
            \"fuel\": x.fuel,
            \"transmission\": x.transmission,
            \"body_type\": x.body_type,
            \"price_text\": x.price_text,
            \"price_value\": x.price_value,
            \"price_currency\": x.price_currency,
            \"location_text\": x.location_text,
            \"posted_text\": x.posted_text,
            \"seller_text\": x.seller_text,
            \"thumbnail_url\": x.thumbnail_url,
            \"img_urls\": \"|\".join(x.img_urls) if x.img_urls else \"\",
            \"latitude\": x.latitude,
            \"longitude\": x.longitude,
            \"description\": x.description,
            \"attributes_json\": json.dumps(x.attributes_kv, ensure_ascii=False),
            \"item_url\": x.item_url,
            \"category_hint\": x.category_hint,
            \"source_url\": x.source_url
        })
    df = pd.DataFrame(rows)
    if out_path.lower().endswith(\".xlsx\"):
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)
    print(f\">>> Сохранено {len(df)} строк в {out_path}\")

def parse_args():
    ap = argparse.ArgumentParser(description=\"Facebook Marketplace scraper (vehicles/motorcycles) with SQLite & price history\")
    ap.add_argument(\"--lat\", type=float, required=True, help=\"Широта\")
    ap.add_argument(\"--lon\", type=float, required=True, help=\"Долгота\")
    ap.add_argument(\"--radius-km\", type=int, default=50, help=\"Радиус в км\")
    ap.add_argument(\"--query\", type=str, default=\"\", help=\"Запрос, напр. 'Honda'\")
    ap.add_argument(\"--category\", choices=[\"vehicles\",\"motorcycles\",\"all\"], default=\"all\", help=\"Категория поиска\")
    ap.add_argument(\"--max-items\", type=int, default=300, help=\"Максимум карточек к сбору\")
    ap.add_argument(\"--headless\", action=\"store_true\", help=\"Запуск без UI\")
    ap.add_argument(\"--details\", action=\"store_true\", help=\"Собирать детали со страницы объявления\")
    ap.add_argument(\"--details-concurrency\", type=int, default=1, help=\"Псевдоконкурентность детализации (оставьте 1)\")
    ap.add_argument(\"--db\", type=str, default=\"fb_marketplace.db\", help=\"Путь к SQLite БД\")
    ap.add_argument(\"--export-new\", action=\"store_true\", help=\"Экспортировать только новые за текущий запуск\")
    ap.add_argument(\"--out\", type=str, default=\"fb_marketplace_export.xlsx\", help=\"CSV/XLSX для экспорта\")
    ap.add_argument(\"--export-prices\", action=\"store_true\", help=\"Отдельно выгрузить price_history в CSV/XLSX (использует --out)\")
    ap.add_argument(\"--export-prices-item\", type=str, default=\"\", help=\"Фильтр price_history по item_id\")
    ap.add_argument(\"--storage-state\", type=str, default=STORAGE_STATE_FILE_DEFAULT, help=\"Путь к storage_state.json\")
    return ap.parse_args()

def main():
    args = parse_args()
    run_started_iso = now_iso()

    listings = asyncio.run(run_scrape(
        lat=args.lat, lon=args.lon, radius_km=args.radius_km,
        query=args.query if args.query.strip() else None,
        category=args.category, max_items=args.max_items,
        headless=args.headless, details=args.details, details_concurrency=args.details_concurrency,
        storage_state_path=args.storage_state
    ))

    # DB
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
    print(f\">>> В БД: новых добавлено: {new_items}, изменений цен: {price_changed_count}\")

    # Export
    if args.export_prices:
        dfp = export_price_history(conn, item_id=args.export_prices_item or None)
        if args.out.lower().endswith(\".xlsx\"):
            dfp.to_excel(args.out, index=False)
        else:
            dfp.to_csv(args.out, index=False)
        print(f\">>> Экспорт price_history: {len(dfp)} строк -> {args.out}\")
    else:
        if args.export_new:
            dfn = export_new_since_run(conn, run_started_iso)
            if args.out.lower().endswith(\".xlsx\"):
                dfn.to_excel(args.out, index=False)
            else:
                dfn.to_csv(args.out, index=False)
            print(f\">>> Экспорт только новых: {len(dfn)} строк -> {args.out}\")
        else:
            save_output_rows(listings, args.out)

    conn.close()

if __name__ == \"__main__\":
    main()
