.DEFAULT_GOAL := help
PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip
ALEMBIC := cd backend && .venv/bin/alembic

.PHONY: help install install-backend install-frontend migrate migration migrations-sql \
        seed verify dev dev-backend dev-frontend test test-backend test-frontend \
        lint format backup import-cp31 import-striver sync clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install backend and frontend dependencies

install-backend: ## Create the venv and install Python dependencies
	python3 -m venv backend/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@test -f .env || (cp .env.example .env && echo "Created .env — fill in your credentials")

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

migrate: ## Apply all database migrations
	$(ALEMBIC) upgrade head

migration: ## Create a migration from model changes (make migration m="add x")
	$(ALEMBIC) revision --autogenerate -m "$(m)"
	$(PY) scripts/generate_supabase_migrations.py

migrations-sql: ## Regenerate supabase/migrations/*.sql from the Alembic chain
	$(PY) scripts/generate_supabase_migrations.py

seed: ## Seed taxonomy, achievements and the bundled sheets
	$(PY) scripts/seed_database.py

verify: ## Verify schema, constraints, RLS and seed data
	$(PY) scripts/verify_database.py

import-cp31: ## Import the CP-31 sheet
	$(PY) scripts/import_cp31.py

import-striver: ## Import Striver's A2Z sheet
	$(PY) scripts/import_striver.py

sync: ## Sync connected platform accounts now
	$(PY) scripts/sync_accounts.py

dev: ## Run backend and frontend together
	@echo "Backend  http://localhost:8000/docs"
	@echo "Frontend http://localhost:5173"
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Run the FastAPI dev server
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run the Vite dev server
	cd frontend && npm run dev

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	cd backend && .venv/bin/pytest -q

test-frontend: ## Run frontend tests
	cd frontend && npm test

lint: ## Lint backend and type-check frontend
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint

format: ## Auto-format the backend
	cd backend && .venv/bin/ruff format app tests
	cd backend && .venv/bin/ruff check --fix app tests

backup: ## Back up the database into data/backups/
	$(PY) scripts/backup_database.py

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	rm -rf frontend/dist backend/.ruff_cache
