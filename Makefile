# Common Streamhub tasks. Run `make help` for the list. Windows (cmd/PowerShell): use make.bat.
# Override any variable on the command line, for example: make start CONFIG=/etc/streamhub PYTHON=python3.12

PYTHON ?= python
CONFIG ?= config
ARGS ?=
VERSION := $(shell $(PYTHON) -c "import streamhub; print(streamhub.__version__)")
IMAGE_NAME ?= kavehbc/streamhub
IMAGE ?= $(IMAGE_NAME):$(VERSION)
LATEST ?= $(IMAGE_NAME):latest

.DEFAULT_GOAL := help
.PHONY: help install install-ldap install-build test check demo start passwd dist exe docker-build docker-up docker-down docker-logs k8s-image docs clean

help: ## List the targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install Streamhub for development (tools, examples, tests)
	$(PYTHON) -m pip install -e ".[tools,examples,dev]"

install-ldap: ## Also install LDAP login support
	$(PYTHON) -m pip install -e ".[tools,examples,dev,ldap]"

install-build: ## Also install the build tools (wheel, PyInstaller)
	$(PYTHON) -m pip install -e ".[tools,examples,dev,build]"

test: ## Run the test suite (unit, handlers, integration, doc links)
	$(PYTHON) -m pytest -q

demo: ## Run the bundled demo in the foreground (streamhub demo; admin password: admin)
	$(PYTHON) -m streamhub demo --debug $(ARGS)

start: ## Run the hub on $(CONFIG) (default: config), appending its output to logs/streamhub.log
	@mkdir -p logs
	$(PYTHON) -m streamhub run $(ARGS) $(CONFIG) >> logs/streamhub.log 2>&1

check: ## Validate $(CONFIG) without starting the hub
	$(PYTHON) -m streamhub check $(CONFIG)

passwd: ## Print a password hash for the users file (prompts, or ARGS=<password>)
	$(PYTHON) -m streamhub passwd $(ARGS)

dist: ## Build the wheel and sdist into dist/ (needs the build extra)
	$(PYTHON) -m build

exe: ## Build the single-file executable dist/streamhub with PyInstaller (needs the build extra)
	$(PYTHON) -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller deploy/pyinstaller/streamhub.spec

docker-build: ## Build the Docker image, tagged $(IMAGE) and $(LATEST)
	docker build -t $(IMAGE) -t $(LATEST) .

docker-up: ## Start with Docker Compose on ./config (the first start prints a setup link: make docker-logs)
	docker compose up -d --build

docker-down: ## Stop the Compose stack
	docker compose down

docker-logs: ## Follow the Compose logs
	docker compose logs -f

k8s-image: docker-build ## Build the hub image with kubectl, for "runtime": "kubernetes"
	docker build --build-arg BASE=$(IMAGE) -t streamhub-kubectl:$(VERSION) deploy/kubernetes

docs: ## Build the documentation site into readthedocs/_build/html (pip install -r readthedocs/requirements.txt)
	$(PYTHON) -m sphinx -b html -W --keep-going readthedocs readthedocs/_build/html

clean: ## Remove caches and build output
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for pattern in ('**/__pycache__', '.pytest_cache', '*.egg-info', 'build', 'dist', 'readthedocs/_build') for p in pathlib.Path('.').glob(pattern)]"
