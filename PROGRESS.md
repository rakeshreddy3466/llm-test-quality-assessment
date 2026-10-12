# PROGRESS
Read `docs/PLAN.md` first. Update this file at the end of every phase.

| Phase | Name | Status |
|---|---|---|
| 1 | Skeleton | done |
| 2 | Generation pipeline | done; run `main_sonnet55_v1` (sonnet-5-5, k=5, 15 samples, $1.05) |
| 3 | Executability | done (developer baseline measured; LLM suites pending generation) |
| 4 | Coverage | done (developer + main_sonnet55_v1) |
| 5 | Mutation testing | done (mutmut 3.8 works; developer + main_sonnet55_v1) |
| 6 | Traceability | done (docs/metrics.md written first) |
| 7 | Test smells | done |
| 8 | Relevance & completeness | done (behaviours.yaml is DRAFT) |
| 9 | Manual review sample (STOP for user) | sample built; WAITING for user ratings (manual_review/sample_rated.csv) |
| 10 | Metamorphic experiment | done (results/mr_*.csv) |
| 11 | Results/report.py/make all | done (`make all`) |
| 12 | CI | done (green on Python 3.12 + 3.14) |
| 13 | Report | done: report/report.md + report.pdf + refs.bib (15 refs verified via Crossref); RQ2 pending ratings |

## Notes for next session
- `.env` has HA_PYTHON set to the `.venv` interpreter. Do not print `.env`.
- Phase 2: `uv run testquality generate --dry-run` shows plan (15 calls, est. ~$1.56 for sonnet k=5). First real call returned 400 (key not scoped to a workspace). Add `ANTHROPIC_WORKSPACE_ID=...` to .env (or use a workspace-scoped key), then: `uv run testquality generate` (main) and `--cheap` (haiku).
- Phase 3: `uv run testquality execute --suite developer` (baseline: 115 tests, collect 1.0, pass 1.0, flaky 0, 3 repeats -> results/exec_*.csv). For LLM samples: `uv run testquality execute --suite <run_id>`. Staging dir `_llm_generated/` in HA tree is removed after every run.
- Next: once real generation works, run `generate` (sonnet, k=5) then `execute --suite <run_id>`; then Phase 4 (coverage).
- Phase 4: `uv run testquality coverage --suite developer|<run_id>` -> results/coverage_{units,suites,per_test}.csv + results/cache/coverage_<suite>.json (per-test lines/arcs, reused by phases 5-8). Developer: line 246/246, branch 54/58. LLM run main_sonnet55_v1: collect 15/15, 294 tests, pass 97.6% (7 failing: 6 RuntimeError in init migration tests, 1 AssertionError), union line 245/246, branch 56/58.
- Do NOT run `ruff --fix` on data/ (excluded now). Samples are verbatim extractions of calls.jsonl responses.
- Haiku run (cheap model) not yet generated; run `uv run testquality generate --cheap --run-id cheap_haiku55_v1` if wanted for extra comparison (~$0.1).
- Phase 5: `uv run testquality mutate --suite developer|<run_id>` (~5 min for 15 samples) -> results/mutation_{units,suites,mutants}.csv. mutmut workspace in work/ (gitignored, rebuilt per unit). 164 mutants. developer union 129/164 (0.787); LLM union 133/164 (0.811). score_global is the comparable metric; score_covered = brief's killed/(killed+survived).
- config_flow samples mostly only touch config_flow.py functions (~10 mutants), hence tiny global scores: real, not a bug.
- Phase 6: `uv run testquality traceability --suite developer|<run_id>` -> results/trace_tests.csv, trace_summary.csv. Plugin plugins/_tq_trace.py runs inside HA python. developer trace_name 0.378; LLM trace_name 0.301, trace_declared 0.533.
- Phase 7: `uv run testquality smells --suite developer|<run_id>` -> results/smells_{tests,summary}.csv. Parametrised cases weight each function by its case count (developer file is heavily parametrised: roulette/conditional logic from loops over `vals`).
- Phase 8: data/behaviours.yaml = 40 behaviours, DRAFT needs human check (ranges for tag 2026.10.1). `uv run testquality relevance --suite <s>` needs results/cache/coverage_<s>.json (run `coverage` first). 38 reachable behaviours (2 module-level excluded); developer completeness 1.0 by construction.
- NEXT: Phase 9 manual review sample, then STOP and tell the user.
- Phase 9: manual_review/rubric.md, sample_blinded.csv (60 items: 20 developer, 40 LLM; seed 20261012), key_do_not_open_until_rated.csv. Assistant must NEVER fill ratings. User saves ratings as manual_review/sample_rated.csv. RQ2 stays 'pending manual review' until then. Meanwhile phases 10-12 proceed.
- Phase 10: runs data/runs/mr_<variant>_binary_sensor (mr1a,b,c paraphrases; mr2 rename locals; mr3 reorder; mr4 strip comments). Evaluate: `uv run testquality metamorphic --evaluate --compare` (~45 min, uses HA tree + work/ workspace: do not run other HA commands concurrently). Compare only: `uv run testquality metamorphic --compare`.
- Phases 11-13: `make all` rebuilds results/tables, results/figures, report/report.md, report/report.pdf (pandoc+typst) and the README results block from results/*.csv. `uv run testquality rq2-prepare` computes automatic scores for the 60 sampled tests (results/rq2_auto.csv, per-test mutation runs, ~30-40 min). Once the user saves manual_review/sample_rated.csv, `make all` fills the RQ2 table automatically.
- REMAINING FOR USER: rate manual_review/sample_blinded.csv -> save as manual_review/sample_rated.csv; human check of data/behaviours.yaml; review TO VERIFY notes in report/refs.bib.
