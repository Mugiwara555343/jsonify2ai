.PHONY: up down rebuild-worker smoke api worker web logs ps validate smoke-golden

up:
	docker compose up -d qdrant worker api

down:
	docker compose down

rebuild-worker:
	docker compose build worker && docker compose up -d worker

api:
	docker compose up -d api && docker compose logs -f api

worker:
	docker compose up -d worker && docker compose logs -f worker

web:
	npm --prefix web install && npm --prefix web run dev

smoke:
	API_URL=http://localhost:8082 WORKER_URL=http://localhost:8090 \
	python scripts/smoke_e2e.py

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

.PHONY: indexes
indexes:
	python scripts/qdrant_indexes.py
