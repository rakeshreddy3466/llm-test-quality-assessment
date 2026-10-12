.PHONY: test lint all
test:
	uv run pytest
lint:
	uv run ruff check .
all: lint test
