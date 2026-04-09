.PHONY: test build version release-check tag push-tag release changelog github-release test-venv

PYTHON ?= python3
BUILD_PYTHON := $(shell if [ -x .venv-build/bin/python ]; then printf '%s' .venv-build/bin/python; else printf '%s' $(PYTHON); fi)
VENV_TEST := .venv-test
VENV_TEST_PY := $(VENV_TEST)/bin/python
VERSION ?=
TAG := v$(VERSION)

# Create an isolated test venv with runtime dependencies so that tests which
# import the Typer-based CLI work without polluting the system Python.
$(VENV_TEST_PY):
	$(PYTHON) -m venv $(VENV_TEST)
	$(VENV_TEST_PY) -m pip install --quiet --upgrade pip
	$(VENV_TEST_PY) -m pip install --quiet 'typer>=0.24.0' 'rich>=14.0.0' 'questionary>=2.1.0'

test-venv: $(VENV_TEST_PY)

test: test-venv
	PYTHONPATH=src $(VENV_TEST_PY) -m unittest discover -s tests

build:
	rm -rf build dist *.egg-info
	$(BUILD_PYTHON) -m build --no-isolation

version:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make version VERSION=0.3.1"; exit 1; fi
	$(PYTHON) scripts/bump_version.py $(VERSION)

release-check: test-venv
	$(PYTHON) -m compileall src/zotero_headless tests scripts
	PYTHONPATH=src $(VENV_TEST_PY) -m unittest discover -s tests
	$(BUILD_PYTHON) -m build --no-isolation

tag:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make tag VERSION=0.3.1"; exit 1; fi
	-git tag -d $(TAG)
	git tag $(TAG)

push-tag:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make push-tag VERSION=0.3.1"; exit 1; fi
	-git push origin :refs/tags/$(TAG)
	git push origin $(TAG)

# Print a changelog of commits since the previous tag. Pass RANGE=... to override.
# Example: make changelog VERSION=0.5.0
changelog:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make changelog VERSION=0.5.0"; exit 1; fi
	@PREV_TAG=$$(git tag --list 'v*' --sort=-v:refname | grep -v '^$(TAG)$$' | head -n1); \
	if [ -z "$$PREV_TAG" ]; then RANGE=HEAD; else RANGE="$$PREV_TAG..HEAD"; fi; \
	echo "## $(TAG)"; \
	echo; \
	git log --no-merges --pretty=format:"- %s" $$RANGE; \
	echo

# Create a GitHub release for $(TAG) with auto-generated notes from commit messages.
github-release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make github-release VERSION=0.5.0"; exit 1; fi
	@command -v gh >/dev/null 2>&1 || { echo "gh CLI not found; skipping GitHub release"; exit 0; }
	@PREV_TAG=$$(git tag --list 'v*' --sort=-v:refname | grep -v '^$(TAG)$$' | head -n1); \
	if [ -z "$$PREV_TAG" ]; then RANGE=$(TAG); else RANGE="$$PREV_TAG..$(TAG)"; fi; \
	NOTES=$$(git log --no-merges --pretty=format:"- %s" $$RANGE); \
	if [ -z "$$NOTES" ]; then NOTES="Release $(TAG)"; fi; \
	if gh release view $(TAG) >/dev/null 2>&1; then \
	  echo "Updating existing GitHub release $(TAG)"; \
	  printf '%s\n' "$$NOTES" | gh release edit $(TAG) --title "$(TAG)" --notes-file -; \
	else \
	  echo "Creating GitHub release $(TAG)"; \
	  printf '%s\n' "$$NOTES" | gh release create $(TAG) --title "$(TAG)" --notes-file -; \
	fi

release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release VERSION=0.3.1"; exit 1; fi
	$(MAKE) version VERSION=$(VERSION)
	$(MAKE) release-check
	@if ! git diff --quiet -- pyproject.toml src/zotero_headless/__init__.py; then \
	  git add pyproject.toml src/zotero_headless/__init__.py; \
	  git commit -m "Bump version to $(VERSION)"; \
	fi
	git push origin main
	$(MAKE) tag VERSION=$(VERSION)
	$(MAKE) push-tag VERSION=$(VERSION)
	$(MAKE) github-release VERSION=$(VERSION)
