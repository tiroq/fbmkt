"""
Web UI route handlers for human-friendly interfaces.
"""
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse

from ..database import (
    get_listings_count, get_listings, get_listing_by_id,
    get_statistics, build_where_clause, get_order_clause
)
from ..config import config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ui"])

# HTML template for the main page
INDEX_HTML = '''<!doctype html>
<html lang="en" class="h-full">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FB Marketplace Viewer</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>.truncate-2{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}</style>
</head>
<body class="h-full bg-slate-50 text-slate-900">
<div class="max-w-7xl mx-auto px-4 py-6">
  <h1 class="text-2xl font-semibold mb-4">FB Marketplace — Listings</h1>
  <form id="filters" class="grid grid-cols-1 md:grid-cols-6 gap-3 mb-4"
        hx-get="/ui/table" hx-target="#table" hx-trigger="change, keyup delay:350ms from:input">
    <input class="border rounded px-3 py-2" type="text" name="q" placeholder="Search text (brand, model, title)"/>
    <select class="border rounded px-3 py-2" name="category_hint">
      <option value="">All categories</option>
      <option value="vehicles">vehicles</option>
      <option value="motorcycles">motorcycles</option>
      <option value="all">all</option>
    </select>
    <input class="border rounded px-3 py-2" type="number" name="min_price" placeholder="Min price"/>
    <input class="border rounded px-3 py-2" type="number" name="max_price" placeholder="Max price"/>
    <input class="border rounded px-3 py-2" type="number" name="year" placeholder="Year"/>
    <select class="border rounded px-3 py-2" name="sort">
      <option value="last_seen_desc">Last seen ↓</option>
      <option value="price_asc">Price ↑</option>
      <option value="price_desc">Price ↓</option>
      <option value="year_desc">Year ↓</option>
      <option value="year_asc">Year ↑</option>
    </select>
    <div class="md:col-span-6 flex items-center gap-2">
      <button class="px-3 py-2 rounded bg-slate-800 text-white" type="submit">Apply</button>
      <a class="px-3 py-2 rounded border" href="/api/export/csv" target="_blank">Export CSV (current filters)</a>
    </div>
  </form>
  <div id="stats" hx-get="/ui/stats" hx-trigger="load" class="mb-4"></div>
  <div id="table" hx-get="/ui/table" hx-trigger="load"></div>
</div>
<div id="modal" class="fixed inset-0 bg-black/40 hidden items-center justify-center p-4">
  <div class="bg-white rounded-xl shadow-xl w-full max-w-2xl p-4">
    <div class="flex justify-between items-center mb-2">
      <h2 class="text-lg font-semibold">Price history</h2>
      <button onclick="document.getElementById('modal').classList.add('hidden')" class="text-slate-500">✕</button>
    </div>
    <canvas id="priceChart"></canvas>
  </div>
</div>
<script>
async function openPriceHistory(item_id) {
  const res = await fetch(`/api/listings/${encodeURIComponent(item_id)}/price-history`);
  const data = await res.json();
  const labels = data.map(p => new Date(p.ts).toLocaleString());
  const values = data.map(p => p.price_value);
  const modal = document.getElementById('modal');
  modal.classList.remove('hidden');
  const ctx = document.getElementById('priceChart').getContext('2d');
  if (window.__chart) { window.__chart.destroy(); }
  window.__chart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'Price', data: values }]},
    options: { responsive: true, maintainAspectRatio: false }
  });
}
</script>
</body></html>'''

def get_ui_filters(
    q: Optional[str] = None,
    category_hint: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    year: Optional[int] = None
) -> dict:
    """Extract UI filters from query parameters."""
    return {
        'q': q,
        'category_hint': category_hint,
        'min_price': min_price,
        'max_price': max_price,
        'year': year
    }

@router.get('/', response_class=HTMLResponse)
async def index():
    """Main page with interactive table."""
    return HTMLResponse(INDEX_HTML)

@router.get('/ui/table', response_class=HTMLResponse)
async def ui_table(
    filters: dict = Depends(get_ui_filters),
    sort: str = 'last_seen_desc',
    page: int = 1,
    page_size: int = 20
):
    """Generate HTML table with listings."""
    try:
        offset = (max(1, page) - 1) * max(1, page_size)
        
        total = get_listings_count(filters)
        listings = get_listings(filters, sort, page_size, offset)
        
        # Build HTML table
        html_parts = ['<div class="bg-white rounded-xl shadow border">']
        html_parts.append('<table class="min-w-full divide-y divide-slate-200">')
        html_parts.append('<thead class="bg-slate-50"><tr>')
        
        headers = ["Photo", "Title", "Year", "Price", "Location", "Last seen", "Actions"]
        for header in headers:
            html_parts.append(f'<th class="px-3 py-2 text-left text-xs font-semibold">{header}</th>')
        
        html_parts.append('</tr></thead><tbody class="divide-y divide-slate-100">')
        
        for listing in listings:
            item_id = listing.get('item_id', '')
            title_parts = [x for x in [listing.get('brand', ''), listing.get('model', ''), listing.get('title', '')] if x]
            title_full = ' '.join(title_parts) or '-'
            
            html_parts.append('<tr>')
            
            # Photo with enhanced thumbnail and count
            thumb = listing.get('thumbnail_url', '')
            img_urls = listing.get('img_urls', '')
            images = [url.strip() for url in img_urls.split('|') if url.strip()] if img_urls else []
            image_count = len(images)
            
            if thumb:  # Show thumbnail if it exists, regardless of additional images
                detail_url = f'/detail/{item_id}'
                html_parts.append(f'''<td class="px-3 py-2">
<div class="relative group">
<img src="{thumb}" 
     class="w-20 h-14 object-cover rounded shadow-sm cursor-pointer transition-transform group-hover:scale-105" 
     loading="lazy"
     onerror="this.style.display='none'; this.nextElementSibling.style.display='block'"
     onclick="window.open('{detail_url}', '_blank')"
     alt="Thumbnail"/>
<div class="w-20 h-14 bg-slate-100 rounded shadow-sm hidden items-center justify-center text-slate-400 text-xs">No image</div>''')
                
                # Add image count badge if more than 1 image
                if image_count > 1:
                    html_parts.append(f'<span class="absolute top-1 right-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">{image_count}</span>')
                
                html_parts.append('''<div class="absolute inset-0 bg-black/0 group-hover:bg-black/20 rounded transition-colors flex items-center justify-center">
<svg class="w-4 h-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" fill="currentColor" viewBox="0 0 20 20">
<path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd"></path>
</svg>
</div>
</div>
</td>''')
            else:
                detail_url = f'/detail/{item_id}'
                html_parts.append(f'''<td class="px-3 py-2">
<div class="w-20 h-14 bg-slate-100 rounded shadow-sm flex items-center justify-center text-slate-400 text-xs cursor-pointer" 
     onclick="window.open('{detail_url}', '_blank')">No photo</div>
</td>''')
            
            # Title
            html_parts.append(f'<td class="px-3 py-2">')
            html_parts.append(f'<div class="font-medium truncate-2 max-w-sm">{title_full}</div>')
            html_parts.append(f'<div class="text-xs text-slate-500">{item_id}</div>')
            html_parts.append('</td>')
            
            # Year
            year = listing.get('year') or ''
            html_parts.append(f'<td class="px-3 py-2">{year}</td>')
            
            # Price
            price_value = listing.get('price_value')
            price_currency = listing.get('price_currency', '')
            price_text = f'{price_value:.0f} {price_currency}' if price_value else '-'
            html_parts.append(f'<td class="px-3 py-2">{price_text}</td>')
            
            # Location
            location = listing.get('location_text', '')
            html_parts.append(f'<td class="px-3 py-2">{location}</td>')
            
            # Last seen
            last_seen = listing.get('last_seen', '')
            html_parts.append(f'<td class="px-3 py-2 text-xs text-slate-500">{last_seen}</td>')
            
            # Actions
            actions = (
                f"<a class='text-blue-600 underline mr-2' href='/detail/{item_id}' target='_blank'>View</a>"
                f"<button class='text-emerald-700 underline' onclick=\"openPriceHistory('{item_id}')\">Price history</button>"
            )
            html_parts.append(f'<td class="px-3 py-2">{actions}</td>')
            html_parts.append('</tr>')
        
        html_parts.append('</tbody></table>')
        
        # Pagination
        pages = max(1, (total + page_size - 1) // page_size)
        html_parts.append('<div class="flex items-center justify-between p-3 text-sm text-slate-600">')
        html_parts.append(f'<div>Total: {total}</div>')
        
        prev_page = max(1, page - 1)
        next_page = min(pages, page + 1)
        
        # Build query string for pagination
        query_params = []
        for key, value in filters.items():
            if value is not None and value != '':
                query_params.append(f'{key}={value}')
        query_params.extend([f'sort={sort}', f'page_size={page_size}'])
        query_string = '&'.join(query_params)
        
        html_parts.append('<div class="space-x-2">')
        html_parts.append(f'<a class="px-2 py-1 border rounded" hx-get="/ui/table?page={prev_page}&{query_string}" hx-target="#table">Prev</a>')
        html_parts.append(f'<span>Page {page}/{pages}</span>')
        html_parts.append(f'<a class="px-2 py-1 border rounded" hx-get="/ui/table?page={next_page}&{query_string}" hx-target="#table">Next</a>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        return HTMLResponse(''.join(html_parts))
        
    except Exception as e:
        logger.error(f"Error generating UI table: {e}")
        return HTMLResponse('<div class="text-red-600">Error loading listings</div>')

@router.get('/ui/stats', response_class=HTMLResponse)
async def ui_stats():
    """Generate HTML stats display."""
    try:
        stats = get_statistics()
        
        def stat_pill(label: str, value: str) -> str:
            return (f'<div class="px-3 py-2 bg-white rounded-lg shadow text-sm">'
                   f'<div class="text-slate-500">{label}</div>'
                   f'<div class="text-lg font-semibold">{value}</div></div>')
        
        html_parts = ['<div class="grid grid-cols-2 md:grid-cols-5 gap-3">']
        html_parts.append(stat_pill('Total listings', str(stats['total_listings'])))
        html_parts.append(stat_pill('Active last 7d', str(stats['active_last_days'])))
        
        min_price = f"{stats['min_price']:.0f}" if stats['min_price'] else '—'
        max_price = f"{stats['max_price']:.0f}" if stats['max_price'] else '—'
        avg_price = f"{stats['avg_price']:.0f}" if stats['avg_price'] else '—'
        
        html_parts.append(stat_pill('Min price', min_price))
        html_parts.append(stat_pill('Max price', max_price))
        html_parts.append(stat_pill('Avg price', avg_price))
        html_parts.append('</div>')
        
        # Brand and year breakdowns
        html_parts.append('<div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">')
        
        # Top brands
        html_parts.append('<div class="bg-white rounded-lg shadow p-3">')
        html_parts.append('<h3 class="font-medium mb-2">Top brands</h3>')
        html_parts.append('<ul class="space-y-1">')
        for brand, count in list(stats['by_brand'].items())[:10]:
            html_parts.append(f'<li class="flex justify-between"><span>{brand}</span><span class="text-slate-500">{count}</span></li>')
        html_parts.append('</ul></div>')
        
        # By year
        html_parts.append('<div class="bg-white rounded-lg shadow p-3">')
        html_parts.append('<h3 class="font-medium mb-2">By year</h3>')
        html_parts.append('<ul class="space-y-1">')
        for year, count in list(stats['by_year'].items())[:10]:
            html_parts.append(f'<li class="flex justify-between"><span>{year}</span><span class="text-slate-500">{count}</span></li>')
        html_parts.append('</ul></div>')
        html_parts.append('</div>')
        
        return HTMLResponse(''.join(html_parts))
        
    except Exception as e:
        logger.error(f"Error generating UI stats: {e}")
        return HTMLResponse('<div class="text-red-600">Error loading statistics</div>')

@router.get('/detail/{item_id}', response_class=HTMLResponse)
async def detail_page(item_id: str):
    """Detail page for a specific listing."""
    try:
        listing = get_listing_by_id(item_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Parse attributes
        try:
            attributes = json.loads(listing.get('attributes_json', '{}'))
            attrs_list = list(attributes.items())
        except (json.JSONDecodeError, TypeError):
            attrs_list = []
        
        # Parse images
        img_urls = listing.get('img_urls', '')
        images = [url.strip() for url in img_urls.split('|') if url.strip()] if img_urls else []
        
        # Build detail page HTML
        brand = listing.get('brand', '')
        model = listing.get('model', '')
        title = listing.get('title', '')
        full_title = f"{brand} {model} — {title}".strip(' —')
        
        price_value = listing.get('price_value')
        price_currency = listing.get('price_currency', '')
        price_text = f"{price_value} {price_currency}".strip() if price_value else listing.get('price_text', '')
        
        html = f'''<!doctype html>
<html><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{full_title} - FB Marketplace</title>
<script src='https://cdn.tailwindcss.com'></script>
<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
</head>
<body class='bg-slate-50 text-slate-900'>
<div class="max-w-5xl mx-auto px-4 py-6">
<a href="/" class="text-blue-600 underline">← Back</a>
<h1 class='text-2xl font-semibold mt-2'>{full_title}</h1>
<div class='text-lg mt-1'>Price: <b>{price_text or '—'}</b></div>
<div class='text-slate-600 text-sm'>Last seen: {listing.get('last_seen', '')}</div>'''
        
        # Images with enhanced gallery
        thumbnail_url = listing.get('thumbnail_url', '')
        display_images = images.copy() if images else []
        
        # If we have a thumbnail but no additional images, use the thumbnail
        if thumbnail_url and not display_images:
            display_images = [thumbnail_url]
        
        if display_images:
            html += '''<div class="my-6">
<h3 class="text-lg font-medium mb-3">Photos</h3>
<div class="grid grid-cols-2 md:grid-cols-4 gap-3">'''
            for i, img_url in enumerate(display_images[:16]):
                html += f'''<div class="relative group cursor-pointer" onclick="openImageModal({i})">
<img class="rounded-lg shadow-md w-full h-32 md:h-40 object-cover transition-transform group-hover:scale-105" 
     src="{img_url}" 
     loading="lazy"
     onerror="this.parentElement.style.display='none'"
     alt="Vehicle photo {i+1}"/>
<div class="absolute inset-0 bg-black/0 group-hover:bg-black/20 rounded-lg transition-colors flex items-center justify-center">
<svg class="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" fill="currentColor" viewBox="0 0 20 20">
<path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 011 1v12a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm5 3a1 1 0 00-1 1v1a1 1 0 002 0V9h1a1 1 0 000-2H8zm4 0a1 1 0 00-1 1v1a1 1 0 002 0V9h1a1 1 0 000-2h-1z" clip-rule="evenodd"></path>
</svg>
</div>
</div>'''
            if len(display_images) > 16:
                html += f'<div class="flex items-center justify-center text-slate-500 bg-slate-100 rounded-lg h-32 md:h-40">+{len(display_images)-16} more</div>'
            html += '</div></div>'
        
        # Specs and description
        html += '<div class="grid grid-cols-1 md:grid-cols-3 gap-4">'
        html += '<div class="bg-white rounded-lg shadow p-3">'
        html += '<h3 class="font-medium mb-2">Specs</h3><ul class="space-y-1">'
        
        specs = [
            ("Year", listing.get('year')),
            ("Mileage (km)", listing.get('mileage_km')),
            ("Fuel", listing.get('fuel')),
            ("Transmission", listing.get('transmission')),
            ("Body", listing.get('body_type')),
            ("Location", listing.get('location_text'))
        ]
        
        for label, value in specs:
            display_value = value if value not in (None, "") else "—"
            html += f'<li class="flex justify-between"><span>{label}</span><span class="text-slate-700">{display_value}</span></li>'
        
        html += '</ul></div>'
        html += '<div class="bg-white rounded-lg shadow p-3 md:col-span-2">'
        html += '<h3 class="font-medium mb-2">Description</h3>'
        html += f'<div class="whitespace-pre-wrap">{listing.get("description", "—")}</div>'
        html += '</div></div>'
        
        # Attributes
        if attrs_list:
            html += '<div class="bg-white rounded-lg shadow p-3 mt-4">'
            html += '<h3 class="font-medium mb-2">Attributes</h3>'
            html += '<div class="grid grid-cols-1 md:grid-cols-2 gap-2">'
            for key, value in attrs_list[:40]:
                html += f'<div class="flex justify-between"><span class="text-slate-500">{key}</span><span class="text-slate-800">{value}</span></div>'
            html += '</div></div>'
        
        # Footer links
        item_url = listing.get('item_url') or listing.get('source_url') or '#'
        html += f'''<div class="mt-4 flex items-center gap-3">
<a class="px-3 py-2 bg-slate-900 text-white rounded" href="{item_url}" target="_blank">Open on Facebook</a>
<button onclick="openPriceHistory('{item_id}')" class="px-3 py-2 border rounded">Show price history</button>
</div>'''
        
        # Modal and JavaScript with Image Gallery
        html += f'''
<!-- Price History Modal -->
<div id='priceModal' class='fixed inset-0 bg-black/40 hidden items-center justify-center p-4 z-50'>
<div class='bg-white rounded-xl shadow-xl w-full max-w-2xl p-4'>
<div class='flex justify-between items-center mb-2'>
<h2 class='text-lg font-semibold'>Price history</h2>
<button onclick="document.getElementById('priceModal').classList.add('hidden')" class='text-slate-500 hover:text-slate-700'>✕</button>
</div>
<canvas id='priceChart'></canvas>
</div></div>

<!-- Image Gallery Modal -->
<div id='imageModal' class='fixed inset-0 bg-black/90 hidden items-center justify-center p-4 z-50'>
<div class='relative w-full h-full flex items-center justify-center'>
<button onclick="document.getElementById('imageModal').classList.add('hidden')" 
        class='absolute top-4 right-4 text-white text-2xl hover:text-gray-300 z-10'>✕</button>
<button onclick="prevImage()" class='absolute left-4 text-white text-3xl hover:text-gray-300 z-10'>‹</button>
<button onclick="nextImage()" class='absolute right-4 text-white text-3xl hover:text-gray-300 z-10'>›</button>
<img id='modalImage' class='max-w-full max-h-full object-contain rounded-lg' src='' alt=''>
<div class='absolute bottom-4 left-1/2 transform -translate-x-1/2 text-white text-sm bg-black/50 px-3 py-1 rounded'>
<span id='imageCounter'>1 / 1</span>
</div>
</div></div>

<script>
const images = {json.dumps(display_images)};
let currentImageIndex = 0;

function openImageModal(index) {{
    currentImageIndex = index;
    const modal = document.getElementById('imageModal');
    const modalImage = document.getElementById('modalImage');
    const counter = document.getElementById('imageCounter');
    
    modalImage.src = images[currentImageIndex];
    counter.textContent = `${{currentImageIndex + 1}} / ${{images.length}}`;
    modal.classList.remove('hidden');
}}

function nextImage() {{
    currentImageIndex = (currentImageIndex + 1) % images.length;
    document.getElementById('modalImage').src = images[currentImageIndex];
    document.getElementById('imageCounter').textContent = `${{currentImageIndex + 1}} / ${{images.length}}`;
}}

function prevImage() {{
    currentImageIndex = (currentImageIndex - 1 + images.length) % images.length;
    document.getElementById('modalImage').src = images[currentImageIndex];
    document.getElementById('imageCounter').textContent = `${{currentImageIndex + 1}} / ${{images.length}}`;
}}

// Keyboard navigation
document.addEventListener('keydown', function(e) {{
    const imageModal = document.getElementById('imageModal');
    if (!imageModal.classList.contains('hidden')) {{
        if (e.key === 'ArrowLeft') prevImage();
        if (e.key === 'ArrowRight') nextImage();
        if (e.key === 'Escape') imageModal.classList.add('hidden');
    }}
}});

async function openPriceHistory(id){{
  try {{
    const r=await fetch(`/api/listings/${{encodeURIComponent(id)}}/price-history`);
    const d=await r.json();
    const labels=d.map(p=>new Date(p.ts).toLocaleString());
    const values=d.map(p=>p.price_value);
    const m=document.getElementById('priceModal');
    m.classList.remove('hidden');
    const ctx=document.getElementById('priceChart').getContext('2d');
    if(window.__chart)window.__chart.destroy();
    window.__chart=new Chart(ctx,{{
      type:'line',
      data:{{
        labels,
        datasets:[{{
          label:'Price',
          data:values,
          borderColor:'rgb(75, 192, 192)',
          tension:0.1
        }}]
      }},
      options:{{
        responsive:true,
        scales:{{
          y:{{beginAtZero:false}}
        }}
      }}
    }});
  }} catch(e) {{
    alert('Failed to load price history');
  }}
}}
</script>
</div>
</body></html>'''
        
        return HTMLResponse(html)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating detail page for {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")