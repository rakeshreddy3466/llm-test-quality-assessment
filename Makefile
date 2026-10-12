.PHONY: all report pdf check test lint pipeline
# `make all` rebuilds every table and figure from results/*.csv (no Home Assistant, no API key).
all: report pdf

report:
	uv run --extra analysis testquality report

# report/report.pdf needs pandoc and typst (brew install pandoc typst); skipped if absent
pdf: report
	@if command -v pandoc >/dev/null && command -v typst >/dev/null; then \
		cd report && pandoc report.md --citeproc --pdf-engine=typst -o report.pdf; \
	else echo 'pandoc/typst not found: report.pdf not rebuilt'; fi

check: lint test

test:
	uv run --extra analysis pytest -q

lint:
	uv run ruff check .

# Full measurement pipeline (needs Home Assistant at tag 2026.10.1 and an API key; spends money
# only in the first step). Shown for documentation; see README "Reproduce".
pipeline:
	uv run testquality generate
	uv run testquality execute --suite developer
	uv run testquality coverage --suite developer
	uv run testquality mutate --suite developer
	uv run testquality traceability --suite developer
	uv run testquality smells --suite developer
	uv run testquality relevance --suite developer
