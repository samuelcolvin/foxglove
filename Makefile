.DEFAULT_GOAL := all
isort = isort -rc foxglove tests
black = black -S -l 120 --target-version py37 foxglove tests

.PHONY: install
install:
	pip install -U setuptools pip
	pip install -U -r requirements.txt
	pip install -U -e .

.PHONY: format
format:
	$(isort)
	$(black)

.PHONY: lint
lint:
	flake8 foxglove/ tests/
	$(isort) --check-only
	$(black) --check

.PHONY: test
test:
	pytest --cov=foxglove

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
	python setup.py clean
