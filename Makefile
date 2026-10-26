.DEFAULT_GOAL := check
SAMPLE ?= data/jobs.json

.PHONY: setup test lint fmt check run verify clean

setup:            ## Create venv and install dev dependencies
	uv sync

test:             ## Run the test suite
	uv run pytest

lint:             ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

fmt:              ## Auto-format and fix lint findings
	uv run ruff format .
	uv run ruff check --fix .

type:             ## Type-check the package with mypy --strict
	uv run mypy

check: lint type test  ## All static checks plus tests

run:              ## Run the CLI on a JSON file: make run [SAMPLE=path/to/file.json]
	uv run python -m job_analytics $(SAMPLE)

verify:           ## Run all verification gates (types, tests, lint, oracles, repo hygiene)
	python3 scripts/verify.py tests
	python3 scripts/verify.py lint
	python3 scripts/verify.py types
	python3 scripts/verify.py cli
	python3 scripts/verify.py streaming
	python3 scripts/verify.py schema
	python3 scripts/verify.py jobview
	python3 scripts/verify.py git
	python3 scripts/verify.py readme
	python3 scripts/verify.py agentic

clean:            ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache dist build src/*.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
