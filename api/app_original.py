import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Any, Dict, Tuple

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

DB_PATH = os.getenv("FB_DB", "./data/db/fb_marketplace.db")

app = FastAPI(title="FB Marketplace API", version="1.0.0", docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@contextmanager
def get_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"DB file not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

class ListingOut(BaseModel):
    item_id: str
    title: str = ""
    brand: str = ""
    model: str = ""
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: str = ""
    transmission: str = ""
    body_type: str = ""
    price_text: str = ""
    price_value: Optional[float] = None
    price_currency: Optional[str] = None
    location_text: str = ""
    posted_text: str = ""
    seller_text: str = ""
    thumbnail_url: str = ""
    img_urls: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: str = ""
    attributes_json: str = ""
    category_hint: str = ""
    source_url: str = ""
    item_url: str = ""
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

class ListingsResponse(BaseModel):
    total: int
    items: List[ListingOut]

class PricePoint(BaseModel):
    ts: str
    price_value: Optional[float]
    price_currency: Optional[str]

class StatsOut(BaseModel):
    total_listings: int
    active_last_days: int
    min_price: Optional[float]
    max_price: Optional[float]
    avg_price: Optional[float]
    by_brand: Dict[str, int]
    by_year: Dict[str, int]

INDEX_HTML = '<!doctype html>\n<html lang="en" class="h-full">\n<head>\n  <meta charset="utf-8"/>\n  <meta name="viewport" content="width=device-width, initial-scale=1"/>\n  <title>FB Marketplace Viewer</title>\n  <script src="https://unpkg.com/htmx.org@1.9.12"></script>\n  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n  <script src="https://cdn.tailwindcss.com"></script>\n  <style>.truncate-2{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}</style>\n</head>\n<body class="h-full bg-slate-50 text-slate-900">\n<div class="max-w-7xl mx-auto px-4 py-6">\n  <h1 class="text-2xl font-semibold mb-4">FB Marketplace — Listings</h1>\n  <form id="filters" class="grid grid-cols-1 md:grid-cols-6 gap-3 mb-4"\n        hx-get="/ui/table" hx-target="#table" hx-trigger="change, keyup delay:350ms from:input">\n    <input class="border rounded px-3 py-2" type="text" name="q" placeholder="Search text (brand, model, title)"/>\n    <select class="border rounded px-3 py-2" name="category_hint">\n      <option value="">All categories</option>\n      <option value="vehicles">vehicles</option>\n      <option value="motorcycles">motorcycles</option>\n      <option value="all">all</option>\n    </select>\n    <input class="border rounded px-3 py-2" type="number" name="min_price" placeholder="Min price"/>\n    <input class="border rounded px-3 py-2" type="number" name="max_price" placeholder="Max price"/>\n    <input class="border rounded px-3 py-2" type="number" name="year" placeholder="Year"/>\n    <select class="border rounded px-3 py-2" name="sort">\n      <option value="last_seen_desc">Last seen ↓</option>\n      <option value="price_asc">Price ↑</option>\n      <option value="price_desc">Price ↓</option>\n      <option value="year_desc">Year ↓</option>\n      <option value="year_asc">Year ↑</option>\n    </select>\n    <div class="md:col-span-6 flex items-center gap-2">\n      <button class="px-3 py-2 rounded bg-slate-800 text-white" type="submit">Apply</button>\n      <a class="px-3 py-2 rounded border" href="/export/csv" target="_blank">Export CSV (current filters)</a>\n    </div>\n  </form>\n  <div id="stats" hx-get="/ui/stats" hx-trigger="load" class="mb-4"></div>\n  <div id="table" hx-get="/ui/table" hx-trigger="load"></div>\n</div>\n<div id="modal" class="fixed inset-0 bg-black/40 hidden items-center justify-center p-4">\n  <div class="bg-white rounded-xl shadow-xl w-full max-w-2xl p-4">\n    <div class="flex justify-between items-center mb-2">\n      <h2 class="text-lg font-semibold">Price history</h2>\n      <button onclick="document.getElementById(\'modal\').classList.add(\'hidden\')" class="text-slate-500">✕</button>\n    </div>\n    <canvas id="priceChart"></canvas>\n  </div>\n</div>\n<script>\nasync function openPriceHistory(item_id) {\n  const res = await fetch(`/api/listings/${encodeURIComponent(item_id)}/price-history`);\n  const data = await res.json();\n  const labels = data.map(p => new Date(p.ts).toLocaleString());\n  const values = data.map(p => p.price_value);\n  const modal = document.getElementById(\'modal\');\n  modal.classList.remove(\'hidden\');\n  const ctx = document.getElementById(\'priceChart\').getContext(\'2d\');\n  if (window.__chart) { window.__chart.destroy(); }\n  window.__chart = new Chart(ctx, {\n    type: \'line\',\n    data: { labels, datasets: [{ label: \'Price\', data: values }]},\n    options: { responsive: true, maintainAspectRatio: false }\n  });\n}\n</script>\n</body></html>\n'
def _build_where(args: Dict[str, Any]) -> Tuple[str, list]:
    where = []
    binds = []
    q = args.get('q')
    if q:
        where.append('(lower(title) LIKE ? OR lower(brand) LIKE ? OR lower(model) LIKE ?)')
        s = f'%{q.lower()}%'
        binds += [s, s, s]
    cat = args.get('category_hint')
    if cat:
        where.append('category_hint = ?')
        binds.append(cat)
    mn = args.get('min_price')
    if mn is not None:
        where.append('(price_value IS NOT NULL AND price_value >= ?)')
        binds.append(mn)
    mx = args.get('max_price')
    if mx is not None:
        where.append('(price_value IS NOT NULL AND price_value <= ?)')
        binds.append(mx)
    yr = args.get('year')
    if yr is not None:
        where.append('year = ?')
        binds.append(yr)
    min_lat = args.get('min_lat'); max_lat = args.get('max_lat')
    if min_lat is not None and max_lat is not None:
        where.append('(latitude BETWEEN ? AND ?)')
        binds += [min_lat, max_lat]
    min_lon = args.get('min_lon'); max_lon = args.get('max_lon')
    if min_lon is not None and max_lon is not None:
        where.append('(longitude BETWEEN ? AND ?)')
        binds += [min_lon, max_lon]
    return (' WHERE ' + ' AND '.join(where)) if where else '', binds

def _order_by(sort: str) -> str:
    if sort == "price_asc": return " ORDER BY price_value ASC"
    if sort == "price_desc": return " ORDER BY price_value DESC"
    if sort == "year_desc": return " ORDER BY year DESC"
    if sort == "year_asc": return " ORDER BY year ASC"
    return " ORDER BY datetime(last_seen) DESC"

@app.get('/', response_class=HTMLResponse)
def index():
    return INDEX_HTML

@app.get('/ui/table', response_class=HTMLResponse)
def ui_table(q: Optional[str] = None, category_hint: Optional[str] = None,
             min_price: Optional[float] = None, max_price: Optional[float] = None,
             year: Optional[int] = None, sort: str = 'last_seen_desc',
             page: int = 1, page_size: int = 20):
    args = dict(q=q, category_hint=category_hint, min_price=min_price, max_price=max_price, year=year)
    offset = (max(1, page) - 1) * max(1, page_size)
    with get_conn() as conn:
        where, binds = _build_where(args)
        total = conn.execute(f'SELECT COUNT(*) FROM listings {where}', binds).fetchone()[0]
        sql = f"""        SELECT item_id, title, brand, model, year, price_value, price_currency, location_text, last_seen, thumbnail_url
        FROM listings
        {where}
        {_order_by(sort)}
        LIMIT ? OFFSET ?"""
        rows = conn.execute(sql, [*binds, page_size, offset]).fetchall()

    s = []
    s.append('<div class="bg-white rounded-xl shadow border">')
    s.append('<table class="min-w-full divide-y divide-slate-200">')
    s.append('<thead class="bg-slate-50"><tr>')
    for h in ["Photo","Title","Year","Price","Location","Last seen","Actions"]:
        s.append(f'<th class="px-3 py-2 text-left text-xs font-semibold">{h}</th>')
    s.append('</tr></thead><tbody class="divide-y divide-slate-100">')
    for r in rows:
        (item_id, title, brand, model, year_, price_value, price_currency, location_text, last_seen, thumb) = r
        title_full = ' '.join([x for x in [brand, model, title] if x])
        s.append('<tr>')
        s.append(f'<td class="px-3 py-2"><img src="{thumb or ""}" class="w-20 h-14 object-cover rounded"/></td>')
        s.append(f'<td class="px-3 py-2"><div class="font-medium truncate-2 max-w-sm">{title_full or "-"}</div><div class="text-xs text-slate-500">{item_id}</div></td>')
        s.append(f'<td class="px-3 py-2">{year_ or ""}</td>')
        price_txt = f'{price_value:.0f} {price_currency}' if price_value is not None else '-'
        s.append(f'<td class="px-3 py-2">{price_txt}</td>')
        s.append(f'<td class="px-3 py-2">{location_text or ""}</td>')
        s.append(f'<td class="px-3 py-2 text-xs text-slate-500">{last_seen or ""}</td>')
        actions = (
            f"<a class='text-blue-600 underline mr-2' href='/detail/{item_id}' target='_blank'>View</a>"
            + f"<button class='text-emerald-700 underline' onclick=\"openPriceHistory('{item_id}')\">Price history</button>"
        )
        s.append(f'<td class="px-3 py-2">{actions}</td>')
        s.append('</tr>')
    s.append('</tbody></table>')
    pages = max(1, (total + page_size - 1) // page_size)
    s.append('<div class="flex items-center justify-between p-3 text-sm text-slate-600">')
    s.append(f'<div>Total: {total}</div>')
    prev_p = max(1, page - 1); next_p = min(pages, page + 1)
    s.append('<div class="space-x-2">')
    s.append(f'<a class="px-2 py-1 border rounded" hx-get="/ui/table?page={prev_p}&page_size={page_size}&q={q or ""}&category_hint={category_hint or ""}&min_price={min_price or ""}&max_price={max_price or ""}&year={year or ""}&sort={sort}" hx-target="#table">Prev</a>')
    s.append(f'<span>Page {page}/{pages}</span>')
    s.append(f'<a class="px-2 py-1 border rounded" hx-get="/ui/table?page={next_p}&page_size={page_size}&q={q or ""}&category_hint={category_hint or ""}&min_price={min_price or ""}&max_price={max_price or ""}&year={year or ""}&sort={sort}" hx-target="#table">Next</a>')
    s.append('</div></div></div>')
    return HTMLResponse(''.join(s))

@app.get('/ui/stats', response_class=HTMLResponse)
def ui_stats():
    with get_conn() as conn:
        total = conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
        active_7d = conn.execute("SELECT COUNT(*) FROM listings WHERE datetime(last_seen) >= datetime('now','-7 day')").fetchone()[0]
        mn, mx, avg = conn.execute('SELECT MIN(price_value), MAX(price_value), AVG(price_value) FROM listings WHERE price_value IS NOT NULL').fetchone()
        by_brand = conn.execute("SELECT brand, COUNT(*) FROM listings WHERE brand!='' GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 10").fetchall()
        by_year = conn.execute('SELECT year, COUNT(*) FROM listings WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC LIMIT 10').fetchall()
    def pill(label, value):
        return f'<div class="px-3 py-2 bg-white rounded-lg shadow text-sm"><div class="text-slate-500">{label}</div><div class="text-lg font-semibold">{value}</div></div>'
    html = ['<div class="grid grid-cols-2 md:grid-cols-5 gap-3">']
    html.append(pill('Total listings', total))
    html.append(pill('Active last 7d', active_7d))
    html.append(pill('Min price', f"{mn:.0f}" if mn is not None else '—'))
    html.append(pill('Max price', f"{mx:.0f}" if mx is not None else '—'))
    html.append(pill('Avg price', f"{avg:.0f}" if avg is not None else '—'))
    html.append('</div>')
    html.append('<div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">')
    html.append('<div class="bg-white rounded-lg shadow p-3"><h3 class="font-medium mb-2">Top brands</h3><ul class="space-y-1">')
    for b,c in by_brand:
        html.append(f'<li class="flex justify-between"><span>{b}</span><span class="text-slate-500">{c}</span></li>')
    html.append('</ul></div>')
    html.append('<div class="bg-white rounded-lg shadow p-3"><h3 class="font-medium mb-2">By year</h3><ul class="space-y-1">')
    for y,c in by_year:
        html.append(f'<li class="flex justify-between"><span>{y}</span><span class="text-slate-500">{c}</span></li>')
    html.append('</ul></div></div>')
    return HTMLResponse(''.join(html))

@app.get('/detail/{item_id}', response_class=HTMLResponse)
def detail_page(item_id: str):
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM listings WHERE item_id=?', (item_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, 'Not found')
        cols = [d[0] for d in cur.description]
        rec = {cols[i]: row[i] for i in range(len(cols))}
    try:
        attrs = list(json.loads(rec.get('attributes_json') or '{}').items())
    except Exception:
        attrs = []
    imgs = (rec.get('img_urls') or '').split('|') if rec.get('img_urls') else []
    s = []
    s.append('<div class="max-w-5xl mx-auto px-4 py-6">')
    s.append('<a href="/" class="text-blue-600 underline">← Back</a>')
    s.append(f"<h1 class='text-2xl font-semibold mt-2'>{rec.get('brand') or ''} {rec.get('model') or ''} — {rec.get('title') or ''}</h1>")
    price_txt = ((f"{rec.get('price_value') or ''} {rec.get('price_currency') or ''}").strip() or rec.get('price_text',''))
    s.append(f"<div class='text-lg mt-1'>Price: <b>{price_txt or '—'}</b></div>")
    s.append(f"<div class='text-slate-600 text-sm'>Last seen: {rec.get('last_seen') or ''}</div>")
    if imgs:
        s.append('<div class="grid grid-cols-2 md:grid-cols-4 gap-2 my-4">')
        for u in imgs[:12]:
            s.append(f'<img class="rounded-lg shadow w-full h-40 object-cover" src="{u}"/>')
        s.append('</div>')
    s.append('<div class="grid grid-cols-1 md:grid-cols-3 gap-4">')
    s.append('<div class="bg-white rounded-lg shadow p-3">')
    s.append('<h3 class="font-medium mb-2">Specs</h3>')
    specs = [("Year", rec.get('year')), ("Mileage (km)", rec.get('mileage_km')), ("Fuel", rec.get('fuel')),
             ("Transmission", rec.get('transmission')), ("Body", rec.get('body_type')), ("Location", rec.get('location_text'))]
    s.append('<ul class="space-y-1">')
    for k,v in specs:
        s.append(f'<li class="flex justify-between"><span>{k}</span><span class="text-slate-700">{v if v not in (None,"") else "—"}</span></li>')
    s.append('</ul></div>')
    s.append('<div class="bg-white rounded-lg shadow p-3 md:col-span-2">')
    s.append('<h3 class="font-medium mb-2">Description</h3>')
    s.append(f'<div class="whitespace-pre-wrap">{rec.get("description") or "—"}</div>')
    s.append('</div></div>')
    if attrs:
        s.append('<div class="bg-white rounded-lg shadow p-3 mt-4">')
        s.append('<h3 class="font-medium mb-2">Attributes</h3>')
        s.append('<div class="grid grid-cols-1 md:grid-cols-2 gap-2">')
        for k,v in attrs[:40]:
            s.append(f'<div class="flex justify-between"><span class="text-slate-500">{k}</span><span class="text-slate-800">{v}</span></div>')
        s.append('</div></div>')
    item_url = rec.get('item_url') or rec.get('source_url') or '#'
    s.append(f'<div class="mt-4 flex items-center gap-3"><a class="px-3 py-2 bg-slate-900 text-white rounded" href="{item_url}" target="_blank">Open on Facebook</a>')
    s.append(f'<button onclick="openPriceHistory(\'%s\')" class="px-3 py-2 border rounded">Show price history</button>' % (item_id,))
    s.append('</div>')
    html = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
    <script src='https://cdn.tailwindcss.com'></script><script src='https://cdn.jsdelivr.net/npm/chart.js'></script></head>
    <body class='bg-slate-50 text-slate-900'>""" + ''.join(s) + """
    <div id='modal' class='fixed inset-0 bg-black/40 hidden items-center justify-center p-4'><div class='bg-white rounded-xl shadow-xl w-full max-w-2xl p-4'>
    <div class='flex justify-between items-center mb-2'><h2 class='text-lg font-semibold'>Price history</h2>
    <button onclick="document.getElementById('modal').classList.add('hidden')" class='text-slate-500'>✕</button></div>
    <canvas id='priceChart'></canvas></div></div>
    <script>async function openPriceHistory(id){const r=await fetch(`/api/listings/${encodeURIComponent(id)}/price-history`);
    const d=await r.json();const labels=d.map(p=>new Date(p.ts).toLocaleString());const values=d.map(p=>p.price_value);
    const m=document.getElementById('modal');m.classList.remove('hidden');const ctx=document.getElementById('priceChart').getContext('2d');
    if(window.__chart)window.__chart.destroy();window.__chart=new Chart(ctx,{type:'line',data:{labels,datasets:[{label:'Price',data:values}]}});}
    </script></body></html>"""
    return HTMLResponse(html)

@app.get('/api/listings', response_model=ListingsResponse)
def api_listings(q: Optional[str] = None,
                 category_hint: Optional[str] = None,
                 min_price: Optional[float] = None,
                 max_price: Optional[float] = None,
                 year: Optional[int] = None,
                 min_lat: Optional[float] = None, max_lat: Optional[float] = None,
                 min_lon: Optional[float] = None, max_lon: Optional[float] = None,
                 sort: str = 'last_seen_desc',
                 limit: int = Query(50, ge=1, le=500),
                 offset: int = Query(0, ge=0)):
    args = dict(q=q, category_hint=category_hint, min_price=min_price, max_price=max_price, year=year,
                min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon)
    with get_conn() as conn:
        where, binds = _build_where(args)
        total = conn.execute(f'SELECT COUNT(*) FROM listings {where}', binds).fetchone()[0]
        sql = f'SELECT * FROM listings {where} {_order_by(sort)} LIMIT ? OFFSET ?'
        cur = conn.execute(sql, [*binds, limit, offset])
        cols = [d[0] for d in cur.description]
        items = [ListingOut(**{cols[i]: row[i] for i in range(len(cols))}) for row in cur.fetchall()]
    return ListingsResponse(total=total, items=items)

@app.get('/api/listings/{item_id}', response_model=ListingOut)
def api_listing(item_id: str):
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM listings WHERE item_id=?', (item_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, 'Not found')
        cols = [d[0] for d in cur.description]
        return ListingOut(**{cols[i]: row[i] for i in range(len(cols))})

@app.get('/api/listings/{item_id}/price-history', response_model=List[PricePoint])
def api_price_history(item_id: str):
    with get_conn() as conn:
        cur = conn.execute('SELECT ts, price_value, price_currency FROM price_history WHERE item_id=? ORDER BY ts ASC', (item_id,))
        return [{'ts': r[0], 'price_value': r[1], 'price_currency': r[2]} for r in cur.fetchall()]

@app.get('/api/stats', response_model=StatsOut)
def api_stats():
    with get_conn() as conn:
        total = conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
        active_7d = conn.execute("SELECT COUNT(*) FROM listings WHERE datetime(last_seen) >= datetime('now','-7 day')").fetchone()[0]
        mn, mx, avg = conn.execute('SELECT MIN(price_value), MAX(price_value), AVG(price_value) FROM listings WHERE price_value IS NOT NULL').fetchone()
        by_brand_rows = conn.execute("SELECT brand, COUNT(*) FROM listings WHERE brand!='' GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 20").fetchall()
        by_year_rows = conn.execute('SELECT year, COUNT(*) FROM listings WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC LIMIT 20').fetchall()
    return StatsOut(
        total_listings=total,
        active_last_days=active_7d,
        min_price=mn, max_price=mx, avg_price=avg,
        by_brand={r[0]: r[1] for r in by_brand_rows},
        by_year={str(r[0]): r[1] for r in by_year_rows},
    )

@app.get('/export/csv')
def export_csv(q: Optional[str] = None,
               category_hint: Optional[str] = None,
               min_price: Optional[float] = None,
               max_price: Optional[float] = None,
               year: Optional[int] = None,
               sort: str = 'last_seen_desc'):
    args = dict(q=q, category_hint=category_hint, min_price=min_price, max_price=max_price, year=year)
    with get_conn() as conn:
        where, binds = _build_where(args)
        sql = f'SELECT * FROM listings {where} {_order_by(sort)}'
        df = pd.read_sql_query(sql, conn, params=binds)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    return StreamingResponse(iter([csv_bytes]), media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename="listings.csv"'})
