# quorum-gatherer — developer task runner
# Backend uses uv + ruff + pytest; frontend uses npm + vite.

BACKEND  := backend
FRONTEND := frontend
UV       := uv

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup --------
.PHONY: install
install: install-backend install-frontend ## Install all dependencies

.PHONY: install-backend
install-backend: ## Create venv + install backend (uv, includes dev group)
	cd $(BACKEND) && $(UV) sync

.PHONY: install-frontend
install-frontend: ## Install frontend deps (npm)
	cd $(FRONTEND) && npm install

# ----------------------------------------------------------------- lint --------
.PHONY: lint
lint: ## Ruff lint (backend)
	cd $(BACKEND) && $(UV) run ruff check .

.PHONY: format
format: ## Ruff format + autofix (backend)
	cd $(BACKEND) && $(UV) run ruff format . && $(UV) run ruff check --fix .

.PHONY: format-check
format-check: ## Verify formatting without writing (CI)
	cd $(BACKEND) && $(UV) run ruff format --check . && $(UV) run ruff check .

# ----------------------------------------------------------------- test --------
.PHONY: test
test: ## Run backend test suite (pytest)
	cd $(BACKEND) && $(UV) run python -m pytest

# ------------------------------------------------------------------ run ---------
.PHONY: dev-backend
dev-backend: ## Run FastAPI with reload (http://localhost:8000)
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --reload --port 8000

.PHONY: dev-frontend
dev-frontend: ## Run Vite dev server (http://localhost:5173)
	cd $(FRONTEND) && npm run dev

.PHONY: migrate
migrate: ## Apply Alembic migrations
	cd $(BACKEND) && $(UV) run alembic upgrade head

.PHONY: revision
revision: ## Create an Alembic autogenerate revision (m="message")
	cd $(BACKEND) && $(UV) run alembic revision --autogenerate -m "$(m)"

# ------------------------------------------------------------------ ci ----------
.PHONY: check
check: format-check test ## Lint + format check + tests (what CI runs)
