
SHELL := /bin/bash

.PHONY: build up down logs api scrape login-local

build:
	docker compose build || true

up:
	docker compose up -d api || true

down:
	docker compose down || true

logs:
	docker compose logs -f --tail=200 || true

api:
	@echo "Запустите вручную из каталога api/: uvicorn app:app --reload --port 8000"

scrape:
	docker compose run --rm --env-file .env scraper || true

login-local:
	@echo "Будет добавлено на шаге 5: tools/login_once.py"
