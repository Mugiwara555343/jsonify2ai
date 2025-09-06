.PHONY: up down logs ps validate smoke-golden

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

PYTHON ?= python

# validate the exported JSON/JSONL, not the README-only documents tree
validate:
	$(PYTHON) scripts/validate_json.py data/exports --strict

smoke-golden:
	$(PYTHON) scripts/smoke_golden.py
