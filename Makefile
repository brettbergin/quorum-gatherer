# quorum-gatherer — developer task runner
# uv workspace (quorum_core + backend + desktop) at the repo root; frontend uses npm + vite.

BACKEND  := backend
FRONTEND := frontend
DESKTOP  := desktop
PYDIRS   := quorum_core backend desktop
UV       := uv

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup --------
.PHONY: install
install: install-py install-frontend ## Install all dependencies

.PHONY: install-py
install-py: ## Create the workspace venv + install all members (uv)
	$(UV) sync --all-packages

.PHONY: install-frontend
install-frontend: ## Install frontend deps (npm)
	cd $(FRONTEND) && npm install

# ----------------------------------------------------------------- lint --------
.PHONY: lint
lint: ## Ruff lint (all Python packages)
	$(UV) run ruff check $(PYDIRS)

.PHONY: format
format: ## Ruff format + autofix
	$(UV) run ruff format $(PYDIRS) && $(UV) run ruff check --fix $(PYDIRS)

.PHONY: format-check
format-check: ## Verify formatting without writing (CI)
	$(UV) run ruff format --check $(PYDIRS) && $(UV) run ruff check $(PYDIRS)

# ----------------------------------------------------------------- test --------
.PHONY: test
test: ## Run the test suite (quorum_core + backend)
	$(UV) run python -m pytest

# ------------------------------------------------------------------ run ---------
.PHONY: dev-backend
dev-backend: ## Run FastAPI with reload (http://localhost:8000)
	cd $(BACKEND) && $(UV) run python -m uvicorn app.main:app --reload --port 8000

.PHONY: dev-frontend
dev-frontend: ## Run Vite dev server (http://localhost:5173)
	cd $(FRONTEND) && npm run dev

.PHONY: dev-desktop
dev-desktop: ## Run the native desktop app (dev)
	$(UV) run python -m quorum_desktop.app

.PHONY: migrate
migrate: ## Apply migrations to the backend's local SQLite
	cd $(BACKEND) && $(UV) run python -c "from quorum_core.migrate import upgrade_to_head; upgrade_to_head()"

.PHONY: revision
revision: ## Create an Alembic autogenerate revision (m="message")
	cd $(BACKEND) && $(UV) run alembic -c ../quorum_core/alembic.ini revision --autogenerate -m "$(m)"

# ------------------------------------------------------------------ ci ----------
.PHONY: check
check: format-check test ## Lint + format check + tests (what CI runs)
