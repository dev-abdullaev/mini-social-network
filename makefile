.DEFAULT_GOAL := help
.PHONY: help install services up down restart build logs logs-worker logs-beat ps \
	migrate makemigrations superuser shell dbshell cleanup-users \
	test test-file lint format precommit clean

COMPOSE = docker compose
MANAGE  = $(COMPOSE) exec web python manage.py
VENV    = .venv/bin

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- Setup ----------

.env:
	cp .env.example .env

install: ## Create venv and install dev dependencies (for local tests/lint)
	python3 -m venv .venv
	$(VENV)/pip install -r requirements/local.txt

precommit: install ## Install pre-commit hooks
	$(VENV)/pip install pre-commit
	$(VENV)/pre-commit install

# ---------- Docker stack ----------

up: .env ## Build and start the full stack (web, db, redis, celery worker + beat)
	$(COMPOSE) up --build

down: ## Stop the stack (data volume is kept)
	$(COMPOSE) down

restart: down up ## Restart the full stack

build: ## Rebuild the app image
	$(COMPOSE) build

services: .env ## Start only db + redis (for local development / tests)
	$(COMPOSE) up -d db redis

logs: ## Tail web logs
	$(COMPOSE) logs -f web

logs-worker: ## Tail celery worker logs
	$(COMPOSE) logs -f celery_worker

logs-beat: ## Tail celery beat logs
	$(COMPOSE) logs -f celery_beat

ps: ## Show container status
	$(COMPOSE) ps

clean: ## Stop the stack AND delete the database volume (destructive!)
	$(COMPOSE) down -v

# ---------- Django management (inside docker) ----------

migrate: ## Apply database migrations
	$(MANAGE) migrate

makemigrations: ## Generate new migrations
	$(MANAGE) makemigrations

superuser: ## Create a Django superuser
	$(MANAGE) createsuperuser

shell: ## Open a Django shell
	$(MANAGE) shell

dbshell: ## Open a psql shell into the database
	$(COMPOSE) exec db psql -U social social

cleanup-users: ## Manually delete stale unverified users
	$(MANAGE) cleanup_unverified_users

# ---------- Quality (local venv; db+redis must be up: make services) ----------

test: ## Run the test suite
	$(VENV)/pytest

test-file: ## Run one test file: make test-file f=tests/test_likes.py
	$(VENV)/pytest $(f) -v

lint: ## Run ruff lint + format check (same as CI)
	$(VENV)/ruff check .
	$(VENV)/ruff format --check .

format: ## Auto-fix lint issues and format code
	$(VENV)/ruff check --fix .
	$(VENV)/ruff format .
