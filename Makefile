# Market Briefing Agent — dev targets (techspec §9)
# Requires: uv (backend), npm (frontend), gitleaks (pre-commit)

.PHONY: setup dev dev-backend dev-frontend lint test lint-backend lint-frontend test-backend test-frontend

setup:
	cd backend && uv sync
	cd frontend && npm install
	git config core.hooksPath .githooks

dev:
	@echo "Run in two terminals:"
	@echo "  make dev-backend   (FastAPI on :8000)"
	@echo "  make dev-frontend  (Vite on :5173)"

dev-backend:
	cd backend && uv run uvicorn src.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-frontend:
	cd frontend && npm run lint && npm run format:check

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest -q

test-frontend:
	cd frontend && npm run test
