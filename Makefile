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
	rm -rf data/db/*.db data/fbmkt.log || true
