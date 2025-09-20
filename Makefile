SHELL := /bin/bash

.PHONY: build up down logs scrape api

build:
	docker compose build

up: ## start API (and keep volumes mounted)
	docker compose up -d api

down:
	docker compose down

logs:
	docker compose logs -f

scrape: ## run one-off scraper (env from .env)
	docker compose run --rm scraper

api: ## run API in foreground
	docker compose up api

clean:
	@rm -rf data/fbmkt.log data/export.xlsx || true
	@echo "Removed log and export files"
	@echo "Are you sure you want to delete the database files? This cannot be undone! (y/N)"
	@read -r confirm; if [[ $$confirm == [yY] ]]; then rm -rf data/db/*.db data/fbmkt.log || true; fi
