.PHONY: test build version release-check

PYTHON ?= python3
BUILD_PYTHON := $(shell if [ -x .venv-build/bin/python ]; then printf '%s' .venv-build/bin/python; else printf '%s' $(PYTHON); fi)
VERSION ?=

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

build:
	rm -rf build dist *.egg-info
	$(BUILD_PYTHON) -m build --no-isolation

version:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make version VERSION=0.3.1"; exit 1; fi
	$(PYTHON) scripts/bump_version.py $(VERSION)

release-check:
	$(PYTHON) -m compileall src/zotero_headless tests scripts
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests
	$(BUILD_PYTHON) -m build --no-isolation
