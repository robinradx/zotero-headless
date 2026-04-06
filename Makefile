.PHONY: test build version release-check tag push-tag release

PYTHON ?= python3
BUILD_PYTHON := $(shell if [ -x .venv-build/bin/python ]; then printf '%s' .venv-build/bin/python; else printf '%s' $(PYTHON); fi)
VERSION ?=
TAG := v$(VERSION)

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

tag:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make tag VERSION=0.3.1"; exit 1; fi
	-git tag -d $(TAG)
	git tag $(TAG)

push-tag:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make push-tag VERSION=0.3.1"; exit 1; fi
	-git push origin :refs/tags/$(TAG)
	git push origin $(TAG)

release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release VERSION=0.3.1"; exit 1; fi
	$(MAKE) version VERSION=$(VERSION)
	$(MAKE) release-check
	git push origin main
	$(MAKE) tag VERSION=$(VERSION)
	$(MAKE) push-tag VERSION=$(VERSION)
