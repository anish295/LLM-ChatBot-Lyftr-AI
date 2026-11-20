# LLM Chatbot - developer shortcuts. Requires Docker (with the compose plugin).
COMPOSE ?= docker compose
PYTHON  ?= python
BACKEND_URL ?= http://localhost:8000

.DEFAULT_GOAL := help
.PHONY: help env up down restart logs ps build test test-docker lint smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if it does not exist
	@test -f .env || (cp .env.example .env && echo ">> Created .env from .env.example - put your real LLM_API_KEYS in it.")

up: env ## Build and start backend (:8000) + frontend (:3000) in the background
	$(COMPOSE) up --build -d
	@echo ""
	@echo "  Frontend: http://localhost:3000"
	@echo "  Backend:  http://localhost:8000  (docs: http://localhost:8000/docs)"

down: ## Stop the stack (data volume is kept)
	$(COMPOSE) down

restart: ## Restart containers (history survives: SQLite lives on the app-data volume)
	$(COMPOSE) restart

logs: ## Follow logs of all services
	$(COMPOSE) logs -f --tail=200

ps: ## Show container status
	$(COMPOSE) ps

build: ## Build images without starting
	$(COMPOSE) build

test: ## Run backend tests locally (needs Python 3.11+: pip install -r backend/requirements-dev.txt)
	cd backend && $(PYTHON) -m pytest -q

test-docker: ## Run backend tests in a throwaway Python container (no local Python needed)
	docker run --rm -v "$(CURDIR)/backend:/src" -w /src python:3.11-slim \
		sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q -p no:cacheprovider"

lint: ## Lint backend (ruff) and type-check frontend (tsc)
	cd backend && $(PYTHON) -m ruff check .
	cd frontend && npm run lint

smoke: ## Run the end-to-end smoke test against BACKEND_URL (default http://localhost:8000)
	bash scripts/smoke_test.sh $(BACKEND_URL)

clean: ## Stop the stack AND delete the data volume (wipes history + cache)
	$(COMPOSE) down -v --remove-orphans
