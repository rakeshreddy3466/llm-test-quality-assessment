# PROGRESS
Read `docs/PLAN.md` first. Update this file at the end of every phase.

| Phase | Name | Status |
|---|---|---|
| 1 | Skeleton | done |
| 2 | Generation pipeline | code done + tested (fake client); REAL RUN BLOCKED: API key needs ANTHROPIC_WORKSPACE_ID in .env |
| 3 | Executability | todo |
| 4 | Coverage | todo |
| 5 | Mutation testing | todo |
| 6 | Traceability | todo |
| 7 | Test smells | todo |
| 8 | Relevance & completeness | todo |
| 9 | Manual review sample (STOP for user) | todo |
| 10 | Metamorphic experiment | todo |
| 11 | Results/report.py/make all | todo |
| 12 | CI | todo |
| 13 | Report | todo |

## Notes for next session
- `.env` has HA_PYTHON set to the `.venv` interpreter. Do not print `.env`.
- Phase 2: `uv run testquality generate --dry-run` shows plan (15 calls, est. ~$1.56 for sonnet k=5). First real call returned 400 (key not scoped to a workspace). Add `ANTHROPIC_WORKSPACE_ID=...` to .env (or use a workspace-scoped key), then: `uv run testquality generate` (main) and `--cheap` (haiku).
