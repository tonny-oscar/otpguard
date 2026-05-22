# OTPGuard — Docker management commands
# Usage: make <target>

.PHONY: help dev prod build stop clean logs ps migrate shell-backend shell-db

APP_ENV ?= dev

help:
	@echo ""
	@echo "  OTPGuard Docker Commands"
	@echo "  ─────────────────────────────────────────"
	@echo "  make dev          Start development stack"
	@echo "  make prod         Start production stack"
	@echo "  make build        Build all images"
	@echo "  make stop         Stop all containers"
	@echo "  make clean        Stop + remove volumes"
	@echo "  make logs         Tail all logs"
	@echo "  make ps           Show running containers"
	@echo "  make migrate      Run DB migrations"
	@echo "  make shell-backend  Open backend shell"
	@echo "  make shell-db       Open psql shell"
	@echo ""

# ── Development ───────────────────────────────────────────────────
dev:
	APP_ENV=dev docker compose up --build

dev-bg:
	APP_ENV=dev docker compose up --build -d

# ── Production ────────────────────────────────────────────────────
prod:
	APP_ENV=prod docker compose --profile production up --build -d

prod-down:
	docker compose --profile production down

# ── Build only ────────────────────────────────────────────────────
build:
	docker compose build --no-cache

# ── Stop ──────────────────────────────────────────────────────────
stop:
	docker compose down

# ── Clean (removes volumes — destroys DB data) ────────────────────
clean:
	docker compose down -v --remove-orphans
	docker image prune -f

# ── Logs ──────────────────────────────────────────────────────────
logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-nginx:
	docker compose logs -f nginx

# ── Status ────────────────────────────────────────────────────────
ps:
	docker compose ps

# ── Database migration ────────────────────────────────────────────
migrate:
	docker compose exec backend alembic upgrade head

# ── Shells ────────────────────────────────────────────────────────
shell-backend:
	docker compose exec backend sh

shell-db:
	docker compose exec postgres psql -U otpguard -d otpguard
