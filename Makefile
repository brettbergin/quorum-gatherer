# quorum-gatherer — developer task runner
# uv workspace (quorum_core + desktop) at the repo root.

DESKTOP  := desktop
PYDIRS   := quorum_core desktop
UV       := uv

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup --------
.PHONY: install
install: ## Create the workspace venv + install all members (uv)
	$(UV) sync --all-packages

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
test: ## Run the test suite (quorum_core + desktop)
	$(UV) run python -m pytest

.PHONY: test-cov
test-cov: ## Run tests with coverage (term + htmlcov/, enforces the 70% gate)
	$(UV) run python -m pytest --cov --cov-report=term-missing --cov-report=html

# ------------------------------------------------------------------ run ---------
.PHONY: dev-desktop
dev-desktop: ## Run the native desktop app (dev)
	$(UV) run python -m quorum_desktop.app

.PHONY: migrate
migrate: ## Apply migrations to a local SQLite (./quorum.db)
	$(UV) run python -c "from quorum_core.migrate import upgrade_to_head; upgrade_to_head()"

.PHONY: revision
revision: ## Create an Alembic autogenerate revision (m="message")
	$(UV) run alembic -c quorum_core/alembic.ini revision --autogenerate -m "$(m)"

# ------------------------------------------------------------------ ci ----------
.PHONY: check
check: format-check test ## Lint + format check + tests (what CI runs)
