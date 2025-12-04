.PHONY: help build up down restart logs clean init-db

help: ## Show this help message
	@echo "🚀 MeshScout Docker Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build all Docker images
	docker compose build

up: ## Start all services
	docker compose up

up-d: ## Start all services in detached mode
	docker compose up -d

down: ## Stop all services
	docker compose down

restart: down up-d ## Restart all services

logs: ## View logs from all services
	docker compose logs -f

logs-api: ## View API logs
	docker compose logs -f api

logs-ingestion: ## View ingestion logs
	docker compose logs -f ingestion

logs-web: ## View web logs
	docker compose logs -f web

clean: ## Stop services and remove volumes (⚠️ deletes database)
	docker compose down -v
	docker system prune -f

init-db: ## Initialize database schema
	./scripts/init-db.sh

shell-api: ## Open shell in API container
	docker compose exec api sh

shell-db: ## Open PostgreSQL shell
	docker compose exec postgres psql -U meshscout -d meshscout

status: ## Show status of all services
	docker compose ps

rebuild: down build up-d init-db ## Full rebuild: stop, build, start, init database

dev: up-d init-db logs ## Start development environment
