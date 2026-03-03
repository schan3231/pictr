# Pictr Storyboard Agent — developer targets
# Requires Python 3.11+ and a virtual environment at .venv/
# Run `make setup` first if you have not already.

VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
RUFF    := $(VENV)/bin/ruff
BLACK   := $(VENV)/bin/black
UVICORN := $(VENV)/bin/uvicorn

.PHONY: setup dev test lint format check all clean

## Create virtualenv and install all dependencies (including dev extras).
setup:
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -e ".[dev]" -q
	@echo "✓ setup complete — activate with: source $(VENV)/bin/activate"

## Run the FastAPI dev server with hot-reload.
dev:
	$(UVICORN) backend.app.main:app --reload --host 0.0.0.0 --port 8000

## Run the full test suite with verbose output.
test:
	$(PYTEST) backend/tests/ -v

## Run ruff linter.
lint:
	$(RUFF) check backend/

## Auto-fix ruff violations and format with black.
format:
	$(RUFF) check --fix backend/
	$(BLACK) backend/

## Run lint + format-check (no writes) — suitable for CI.
check:
	$(RUFF) check backend/
	$(BLACK) --check backend/

## Run setup + check + test (full CI pipeline locally).
all: setup check test

## Remove generated artefacts.
clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache __pycache__ build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
