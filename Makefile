ifeq ($(wildcard .env),.env)
include .env
export
endif

VIRTUAL_ENV  := $(CURDIR)/.venv
PROJECT_NAME := $(shell grep '^name = ' pyproject.toml | sed -E 's/name = "(.*)"/\1/')

PYTHON_VERSION ?= 3.13
VENV_PYTHON  := $(VIRTUAL_ENV)/bin/python
VENV_RUFF    := $(VIRTUAL_ENV)/bin/ruff
VENV_PYRIGHT := $(VIRTUAL_ENV)/bin/pyright
VENV_PLXT    := RUST_LOG=warn "$(VIRTUAL_ENV)/bin/plxt"

UV_MIN_VERSION = $(shell grep -m1 'required-version' pyproject.toml | sed -E 's/.*"[<>=~^]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/')

# --- Defaults for eval targets (override: `make run-experiment METHOD=foo`) --------------------
METHOD     ?= answer_from_documents
N          ?= 5
FAIL_BELOW ?= 0.80
# Optional overrides — empty means "use method's default"
DATASET    ?=
GATE_METRIC ?=
EXPERIMENT ?=
RESUME     ?=
FORCE      ?=
CONCURRENCY ?= 1

define PRINT_TITLE
    $(eval PROJECT_PART := [$(PROJECT_NAME)])
    $(eval TARGET_PART := ($@))
    $(eval MESSAGE_PART := $(1))
    $(if $(MESSAGE_PART),\
        $(eval FULL_TITLE := === $(PROJECT_PART) ===== $(TARGET_PART) ====== $(MESSAGE_PART) ),\
        $(eval FULL_TITLE := === $(PROJECT_PART) ===== $(TARGET_PART) ====== )\
    )
    $(eval TITLE_LENGTH := $(shell echo -n "$(FULL_TITLE)" | wc -c | tr -d ' '))
    $(eval PADDING_LENGTH := $(shell echo $$((126 - $(TITLE_LENGTH)))))
    $(eval PADDING := $(shell printf '%*s' $(PADDING_LENGTH) '' | tr ' ' '='))
    $(eval PADDED_TITLE := $(FULL_TITLE)$(PADDING))
    @echo ""
    @echo "$(PADDED_TITLE)"
endef

define HELP
Manage $(PROJECT_NAME) located in $(CURDIR).
Usage:

# --- setup ---
make env                      - Create python virtual env
make install                  - Create local venv & install all deps (eval + dev)
make lock                     - Refresh uv.lock without updating
make update                   - Upgrade deps via uv
make reinstall                - cleanenv + cleanlock + install
make ri                       - Shorthand -> reinstall
make cleanenv                 - Remove virtual env and lock files
make cleanderived             - Remove caches, __pycache__, .ruff_cache, etc.
make cleanall                 - cleanenv + cleanderived

# --- bundle validation ---
make validate-bundles         - Validate every .mthds bundle in methods/
make plxt-format              - Format .mthds / TOML files with plxt
make plxt-lint                - Lint .mthds / TOML files with plxt

# --- python (eval/) ---
make ruff-format              - Format with ruff
make ruff-lint                - Lint with ruff (fix)
make pyright                  - Typecheck with pyright
make format                   - ruff-format + plxt-format
make lint                     - ruff-lint + plxt-lint

# --- merge-checks (no file modification) ---
make merge-check-ruff-format  - ruff format --check
make merge-check-ruff-lint    - ruff check
make merge-check-plxt-format  - plxt fmt --check
make merge-check-plxt-lint    - plxt lint
make merge-check-pyright      - pyright

# --- eval ---
make push-dataset             - Seed Langfuse dataset (METHOD, N, DATASET overridable)
make push-dataset-all         - Seed the FULL benchmark (METHOD, DATASET overridable)
make run-experiment           - Run the experiment for METHOD. Experiment name defaults to
                                '<package_name>@<package_version>' from METHODS.toml.
                                Re-runs at the same version are REJECTED — bump the version
                                in METHODS.toml first. Override with EXPERIMENT=<name>,
                                or pass RESUME=1 (append after crash) / FORCE=1 (overwrite).
make eval                     - push-dataset + run-experiment

# --- shortcuts ---
make check                    - format + lint + pyright + validate-bundles
make c                        - Shorthand -> check
make cc                       - cleanderived + check
make agent-check              - format + lint + pyright + validate-bundles (silent on success)
make help                     - Show this help

Override any of these:
  BUNDLE=methods/answer_from_documents
  DATASET=mmlongbench-sample-v1
  EXPERIMENT=v0.1.0-baseline
  N=5
  FAIL_BELOW=0.80
endef
export HELP

.PHONY: \
	all help env env-verbose check-uv check-uv-verbose lock install update reinstall ri \
	cleanderived cleanenv cleanlock cleanall \
	validate-bundles plxt-format plxt-lint \
	ruff-format ruff-lint pyright format lint \
	merge-check-ruff-format merge-check-ruff-lint merge-check-plxt-format merge-check-plxt-lint merge-check-pyright \
	push-dataset run-experiment eval \
	check c cc agent-check

all help:
	@echo "$$HELP"

##########################################################################################
### SETUP
##########################################################################################

check-uv:
	@command -v uv >/dev/null 2>&1 || { \
		echo ""; \
		echo "=== [$(PROJECT_NAME)] ===== (check-uv) ====== Installing uv ≥ $(UV_MIN_VERSION) =========="; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@uv self update >/dev/null 2>&1 || true

check-uv-verbose:
	$(call PRINT_TITLE,"Ensuring uv ≥ $(UV_MIN_VERSION)")
	@command -v uv >/dev/null 2>&1 || { \
		echo "uv not found – installing latest …"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@uv self update >/dev/null 2>&1 || true

env: check-uv
	@if [ ! -d $(VIRTUAL_ENV) ]; then \
		echo ""; \
		echo "=== [$(PROJECT_NAME)] ===== (env) ====== Creating virtual environment ================="; \
		uv venv $(VIRTUAL_ENV) --python $(PYTHON_VERSION); \
	fi

env-verbose: check-uv-verbose
	$(call PRINT_TITLE,"Creating virtual environment")
	@if [ ! -d $(VIRTUAL_ENV) ]; then \
		uv venv $(VIRTUAL_ENV) --python $(PYTHON_VERSION); \
	else \
		echo "Virtual env already exists: $(VIRTUAL_ENV)"; \
	fi

install: env-verbose
	$(call PRINT_TITLE,"Installing dependencies")
	@. $(VIRTUAL_ENV)/bin/activate && uv sync --all-extras

lock: env-verbose
	$(call PRINT_TITLE,"Resolving dependencies without update")
	@uv lock

update: env-verbose
	$(call PRINT_TITLE,"Upgrading all dependencies")
	@uv lock --upgrade

reinstall: cleanenv cleanlock install
	@echo "> done: reinstall"

ri: reinstall
	@echo "> done: ri = reinstall"

##########################################################################################
### CLEAN
##########################################################################################

cleanderived:
	$(call PRINT_TITLE,"Erasing derived files")
	@find . -name '.coverage' -delete && \
	find . -wholename '**/*.pyc' -delete && \
	find . -type d -wholename '__pycache__' -exec rm -rf {} + && \
	find . -type d -wholename './.cache' -exec rm -rf {} + && \
	find . -type d -wholename './.mypy_cache' -exec rm -rf {} + && \
	find . -type d -wholename './.ruff_cache' -exec rm -rf {} + && \
	find . -type d -wholename '.pytest_cache' -exec rm -rf {} + && \
	echo "Cleaned derived files"

cleanenv:
	$(call PRINT_TITLE,"Erasing virtual environment")
	@find . -type d -wholename './.venv' -exec rm -rf {} +
	@echo "Cleaned virtual env"

cleanlock:
	$(call PRINT_TITLE,"Erasing uv lock file")
	@rm -f uv.lock && echo "Cleaned uv.lock"

cleanall: cleanenv cleanderived cleanlock
	@echo "> done: cleanall"

##########################################################################################
### BUNDLE VALIDATION
##########################################################################################

validate-bundles:
	$(call PRINT_TITLE,"Validating every bundle in methods/")
	@set -e; \
	found=0; \
	for b in methods/*/bundle.mthds; do \
		[ -f "$$b" ] || continue; \
		found=1; \
		echo "  - $$b"; \
		mthds-agent validate bundle "$$b" >/dev/null; \
		mthds-agent package validate -C "$$(dirname $$b)" >/dev/null; \
	done; \
	if [ "$$found" = "0" ]; then echo "  (no bundles found in methods/)"; fi; \
	echo "All bundles and manifests valid."

plxt-format: env
	$(call PRINT_TITLE,"Formatting MTHDS/TOML with plxt")
	$(VENV_PLXT) fmt

plxt-lint: env
	$(call PRINT_TITLE,"Linting MTHDS/TOML with plxt")
	$(VENV_PLXT) lint

##########################################################################################
### PYTHON
##########################################################################################

ruff-format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	@$(VENV_RUFF) format eval

ruff-lint: env
	$(call PRINT_TITLE,"Linting with ruff and fixing")
	@$(VENV_RUFF) check eval --fix

pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	@$(VENV_PYRIGHT) --pythonpath $(VENV_PYTHON) --project pyproject.toml

format: ruff-format plxt-format
	@echo "> done: format"

lint: ruff-lint plxt-lint
	@echo "> done: lint"

##########################################################################################
### MERGE CHECKS (read-only)
##########################################################################################

merge-check-ruff-format: env
	$(call PRINT_TITLE,"ruff format --check")
	@$(VENV_RUFF) format --check eval

merge-check-ruff-lint: env
	$(call PRINT_TITLE,"ruff check without fixing")
	@$(VENV_RUFF) check eval

merge-check-plxt-format: env
	$(call PRINT_TITLE,"plxt fmt --check")
	$(VENV_PLXT) fmt --check

merge-check-plxt-lint: env
	$(call PRINT_TITLE,"plxt lint")
	$(VENV_PLXT) lint

merge-check-pyright: env
	$(call PRINT_TITLE,"pyright")
	@$(VENV_PYRIGHT) --pythonpath $(VENV_PYTHON) --project pyproject.toml

##########################################################################################
### EVAL
##########################################################################################

push-dataset: env
	$(call PRINT_TITLE,"Seeding dataset for method $(METHOD) with $(N) items")
	@$(VENV_PYTHON) eval/cli.py push \
		--method $(METHOD) \
		$(if $(strip $(DATASET)),--dataset $(DATASET),) \
		--n $(N)

push-dataset-all: env
	$(call PRINT_TITLE,"Seeding FULL benchmark for method $(METHOD)")
	@$(VENV_PYTHON) eval/cli.py push \
		--method $(METHOD) \
		$(if $(strip $(DATASET)),--dataset $(DATASET),) \
		--all

run-experiment: env
	$(call PRINT_TITLE,"Experiment on method $(METHOD)")
	@$(VENV_PYTHON) eval/cli.py run \
		--method $(METHOD) \
		$(if $(strip $(EXPERIMENT)),--experiment $(EXPERIMENT),) \
		$(if $(strip $(DATASET)),--dataset $(DATASET),) \
		$(if $(strip $(GATE_METRIC)),--gate-metric $(GATE_METRIC),) \
		$(if $(strip $(RESUME)),--resume,) \
		$(if $(strip $(FORCE)),--force,) \
		--concurrency $(CONCURRENCY) \
		--fail-below $(FAIL_BELOW)

eval: push-dataset run-experiment
	@echo "> done: eval"

##########################################################################################
### SHORTCUTS
##########################################################################################

check: format lint pyright validate-bundles
	@echo "> done: check"

c: check
	@echo "> done: c = check"

cc: cleanderived check
	@echo "> done: cc = cleanderived + check"

agent-check: env
	@echo "• Running format + lint + pyright + validate-bundles (silent on success)..."
	@tmpfile=$$(mktemp); \
	{ $(VENV_RUFF) format eval && \
	  $(VENV_RUFF) check eval --fix && \
	  $(VENV_PLXT) fmt && \
	  $(VENV_PLXT) lint && \
	  $(VENV_PYRIGHT) --pythonpath $(VENV_PYTHON) --project pyproject.toml && \
	  $(MAKE) -s validate-bundles; } > "$$tmpfile" 2>&1; \
	exit_code=$$?; \
	if [ $$exit_code -ne 0 ]; then cat "$$tmpfile"; fi; \
	rm -f "$$tmpfile"; \
	if [ $$exit_code -eq 0 ]; then echo "• All checks passed."; fi; \
	exit $$exit_code
