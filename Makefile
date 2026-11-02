.PHONY: test test-docker up up-full down lint dev

# Backend tests (pytest). Uses uv when available (or `python -m uv`); otherwise runs the suite in Docker.
UV ?= $(shell command -v uv 2>/dev/null || (python -m uv --version >/dev/null 2>&1 && echo "python -m uv"))

test:
ifeq ($(strip $(UV)),)
	docker compose --profile test run --rm --build tests
else
	cd backend && $(UV) run pytest
endif

test-docker:
	docker compose --profile test run --rm --build tests

up:
	docker compose up --build

up-full:
	OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006 docker compose --profile full up --build

down:
	docker compose --profile full down

lint:
	cd backend && $(UV) run ruff check app tests

dev:
	cd backend && $(UV) run uvicorn app.main:app --reload --port 8000
