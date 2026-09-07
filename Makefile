IMAGE   ?= fabiocicerchia/co2-grid-meter
VERSION ?= $(shell cat version.txt)
VENV    ?= .venv

# Every verb this repository exposes lives here; `make` on its own prints them.
# FC-GEN-057: the same eight verbs in every repo, each either wired or a
# declared no-op that says why. None of them exit 0 quietly.

.DEFAULT_GOAL := help

.PHONY: help setup install build run test lint format analyze

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

# Everything a contributor needs: the venv start.sh expects, the runtime and
# dev dependencies in it, and the hook.
setup: ## Create the venv, install runtime + dev dependencies and the hook
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

install: ## Install the runtime dependencies into the active interpreter
	pip install -r requirements.txt

# The image is the dashboard only. The mock Pico is a dev aid and the firmware
# runs on-device under MicroPython — see docs/firmware.md for flashing.
build: ## Build the dashboard image
	docker build -t $(IMAGE):$(VERSION) .

run: ## Serve the dashboard and the mock Pico together
	./start.sh

test: ## Run tests
	pytest

lint: ## Run the whole gate — every hook, every file
	pre-commit run --all-files

format: ## Format what the gate checks — Python with ruff, the rest with biome
	ruff format .
	npx --yes @biomejs/biome@2.5.7 format --write .

analyze: ## Scan the tree the way CI does — vulnerabilities, misconfig, secrets
	@command -v trivy >/dev/null 2>&1 || { \
		echo "analyze needs trivy: https://trivy.dev/latest/getting-started/installation/" >&2; \
		exit 69; }
	trivy fs --scanners vuln,misconfig,secret --severity CRITICAL,HIGH .
