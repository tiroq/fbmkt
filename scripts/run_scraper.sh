#!/usr/bin/env bash
set -euo pipefail

# One-off run scraper via docker compose
# Uses variables from .env

docker compose run --rm scraper
