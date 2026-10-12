# Automated Quality Assessment of LLM Generated Unit Tests: A Home Assistant Case Study

[![CI](https://github.com/rakeshreddy3466/llm-test-quality-assessment/actions/workflows/ci.yml/badge.svg)](https://github.com/rakeshreddy3466/llm-test-quality-assessment/actions/workflows/ci.yml)

Status: **work in progress** (see `PROGRESS.md`).

## Research questions
- **RQ1** How do LLM generated tests compare with developers' tests on executability, coverage,
  mutation score, traceability, maintainability (test smells), relevance and completeness?
- **RQ2** How well do automatic scores agree with a blinded manual review (Spearman rho, weighted kappa)?
- **RQ3** How sensitive are generated tests to metamorphic changes, compared with the noise between
  repeated samples?

## Results
_Pending: results are generated from `results/*.csv` (phase 11). RQ2: pending manual review._

## Setup
```bash
cp .env.example .env     # fill ANTHROPIC_API_KEY, HA_CORE_DIR, HA_PYTHON
uv sync
uv run testquality --help
uv run pytest
```
Requires Home Assistant core checked out at tag 2026.10.1 with its own `.venv`.

## Reproduce
_Filled in phase 13._

## License
MIT
