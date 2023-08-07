.DEFAULT_GOAL := all
paths = foxglove tests
isort = isort
black = black foxglove tests

.PHONY: install
install:
	pip install -U pip
	pip install -r requirements/all.txt
	pip install -U -e .[extra]

.PHONY: format
format:
	isort $(paths)
	black $(paths)

.PHONY: lint
lint:
	flake8 $(paths)
	isort $(paths) --check-only --df
	black $(paths) --check --diff

.PHONY: test
test:
	coverage run -m pytest

.PHONY: testcov
testcov:
	pytest --cov=foxglove
	@echo "building coverage html"
	@coverage html

.PHONY: all
all: lint testcov

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	rm -rf dist
	python setup.py clean

.PHONY: upgrade-requirements
upgrade-requirements:
	@echo "upgrading dependencies"
	@pip-compile --quiet --upgrade --output-file=requirements/pyproject.txt pyproject.toml
	@pip-compile --quiet --upgrade --output-file=requirements/linting.txt requirements/linting.in
	@pip-compile --quiet --upgrade --output-file=requirements/testing.txt requirements/testing.in
	@echo "dependencies has been upgraded"

.PHONY: rebuild-requirements
rebuild-requirements:
	rm requirements/pyproject.txt requirements/linting.txt requirements/testing.txt
	pip-compile --quiet --rebuild --output-file=requirements/pyproject.txt pyproject.toml
	pip-compile --quiet --rebuild --output-file=requirements/linting.txt requirements/linting.in
	pip-compile --quiet --rebuild --output-file=requirements/testing.txt requirements/testing.in
