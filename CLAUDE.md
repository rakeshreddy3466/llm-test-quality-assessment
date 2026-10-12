# CLAUDE.md
Research project: quality assessment of LLM-generated unit tests (Home Assistant `threshold`).
- Start every session by reading `PROGRESS.md`, then `docs/PLAN.md` and `docs/DECISIONS.md`.
- Tool: `src/testquality` (uv, Python 3.12+). Run its tests: `uv run pytest`; lint: `uv run ruff check .`
- HA tests ONLY via `~/code/ha-core/.venv/bin/python -m pytest` run from `~/code/ha-core` (HA_PYTHON in .env).
- Never edit HA files except `tests/components/threshold/_llm_generated/<run_id>/` (delete after each run).
- Never print/commit `.env` or the API key. Never send temperature/top_p/top_k. Never show developer tests to the LLM.
- Every number in README/report must come from `results/*.csv`. Never fill manual ratings. Never invent citations.
- Log decisions in `docs/DECISIONS.md`; commit "Phase N: <name>" and push to origin main.
