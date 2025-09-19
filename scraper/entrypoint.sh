#!/usr/bin/env bash
set -euo pipefail

LAT="${LAT:?LAT is required}"
LON="${LON:?LON is required}"
RADIUS_KM="${RADIUS_KM:-50}"
CATEGORY="${CATEGORY:-all}"
QUERY="${QUERY:-}"
MAX_ITEMS="${MAX_ITEMS:-300}"
DETAILS="${DETAILS:-true}"
HEADLESS="${HEADLESS:-1}"
DB_PATH="${DB_PATH:-/data/db/fb_marketplace.db}"
STORAGE_STATE_FILE="${STORAGE_STATE_FILE:-/data/auth/storage_state.json}"
EXPORT_NEW="${EXPORT_NEW:-false}"
EXPORT_PRICES="${EXPORT_PRICES:-false}"
EXPORT_PRICES_ITEM="${EXPORT_PRICES_ITEM:-}"
OUT_PATH="${OUT_PATH:-/data/export.csv}"

ARGS=(
  --lat "$LAT"
  --lon "$LON"
  --radius-km "$RADIUS_KM"
  --category "$CATEGORY"
  --max-items "$MAX_ITEMS"
  --db "$DB_PATH"
  --storage-state "$STORAGE_STATE_FILE"
  --out "$OUT_PATH"
)

if [[ -n "$QUERY" ]]; then
  ARGS+=( --query "$QUERY" )
fi

if [[ "$DETAILS" == "true" || "$DETAILS" == "1" ]]; then
  ARGS+=( --details )
fi

if [[ "$HEADLESS" == "1" || "$HEADLESS" == "true" ]]; then
  ARGS+=( --headless )
fi

if [[ "$EXPORT_NEW" == "true" || "$EXPORT_NEW" == "1" ]]; then
  ARGS+=( --export-new )
fi

if [[ "$EXPORT_PRICES" == "true" || "$EXPORT_PRICES" == "1" ]]; then
  ARGS+=( --export-prices )
  if [[ -n "$EXPORT_PRICES_ITEM" ]]; then
    ARGS+=( --export-prices-item "$EXPORT_PRICES_ITEM" )
  fi
fi

echo ">> Running scraper with args: ${ARGS[@]}"
python /app/fb_marketplace_scraper.py "${ARGS[@]}"
