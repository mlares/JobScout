.DEFAULT_GOAL := help

.PHONY: help setup test lint build check-public check demo run run-demo

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install locked Python and frontend dependencies
	uv sync --locked --all-packages --all-groups
	npm ci --prefix apps/career-app

test: ## Run deterministic tests that need no services or LaTeX compiler
	uv run --all-packages pytest apps/career-app/tests packages/cover-letter-engine/tests packages/cv-engine/tests integrations/job-scout/tests -m "not integration and not compile"

lint: ## Run Python static checks
	uv run --all-packages ruff check apps packages integrations scripts

build: ## Build the React frontend
	npm run build --prefix apps/career-app

check-public: ## Reject tracked private data and common secret/path leaks
	uv run python scripts/check_public_tree.py

check: lint test build check-public ## Run the local release-quality gate

demo: ## Print a synthetic cover-letter prompt without a model call
	uv run cover-letter generate --profile examples/fictional-profile.json --job examples/fictional-job-description.txt --company "Northstar Transit Labs" --role "Applied AI Engineer" --dry-run

run: ## Launch the local Career App on http://127.0.0.1:8765
	bash apps/career-app/run.sh

run-demo: ## Launch with fictional inputs and isolated demo runtime data
	CAREER_DEMO=1 bash apps/career-app/run.sh
