.DEFAULT_GOAL := help
.PHONY: help install install-dev test lint type health check run clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package (runtime only)
	pip install -e .

install-dev:  ## Install package + dev/CI tooling
	pip install -e ".[async,config,dev]"
	pip install -r requirements-dev.txt

test:  ## Run the offline test suite
	pytest

lint:  ## Lint with ruff
	ruff check .

type:  ## Type-check with mypy
	mypy

health:  ## Re-parse samples/ to detect config drift
	python -m nestfetch.healthcheck

check: lint type health test  ## Run every quality gate (what CI runs)

run:  ## Launch the interactive scraper
	python -m nestfetch

clean:  ## Remove caches and build artifacts
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
