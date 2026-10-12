# Decisions log

| Date | Phase | What you proposed | What was decided | Why |
|---|---|---|---|---|
| 2026-10-12 | 1 | HA_PYTHON pointed at `venv` in .env and .env.example | Changed both to `.venv/bin/python` | HA checkout uses `.venv`; per brief |
| 2026-10-12 | 1 | CLI framework | argparse (stdlib), stub subcommands exit code 2 | No extra dependency; stubs must not look like success |
| 2026-10-12 | 1 | Build backend / layout | hatchling, src layout, dev tools in `[dependency-groups]`, analysis libs as optional extra | Keeps phase 1 install light; uv supports dependency-groups |
| 2026-10-12 | 1 | Review seed | 20261012 (date of project start) in config.yaml | Fixed seed for reproducible blinded sample |
| 2026-10-12 | 2 | Model ids/prices | Verified on platform.claude.com pricing page: Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per MTok (<=100K prompt) | Brief required docs check before first real call |
| 2026-10-12 | 2 | Sampling control | No temperature/top_p/top_k; `output_config.effort: medium` fixed and logged in params; max_tokens 16000 | Models reject sampling params; effort bounds thinking cost; reproducibility |
| 2026-10-12 | 2 | Prompt unit | One prompt per target module (binary_sensor, config_flow, __init__), whole component source in context, k=5 | Component is small (~8K tokens); keeps cost ~$1.6 for the main run |
| 2026-10-12 | 2 | Leakage control | Prompt only reads component source; `assert_no_leakage` fails if any developer test function name appears in a prompt | Brief: never show developer tests to the LLM |
| 2026-10-12 | 2 | Cost guard | `generate` refuses (exit 3) when estimate > llm.max_cost_usd (3.0); dry-run estimate uses 3.3 chars/token and 9000 output tokens/call | Brief rule (a) |
| 2026-10-12 | 2 | Truncated outputs | stop_reason=max_tokens samples are logged but not written as test files | Truncated code would be miscounted as non-executable |
| 2026-10-12 | 2 | Workspace header | Optional ANTHROPIC_WORKSPACE_ID in .env sent as `anthropic-workspace-id` header | First real call returned 400: key not scoped to a workspace |
| 2026-10-12 | 3 | Execution unit | One pytest process per test file per repeat, junit xml parsed; `--timeout=120` per test, `-p no:sugar` | Isolates a broken sample (syntax/import error) from others; junit gives per-test outcomes |
| 2026-10-12 | 3 | Metric definitions | collect_rate = files with >=1 collected test / files requested (incl. samples lost to truncation); pass_rate = passed/(passed+failed+error) averaged over 3 repeats; flaky = test with differing outcomes across repeats; skipped excluded | Keeps denominators explicit; docs/metrics.md will restate in phase 6 |
| 2026-10-12 | 3 | Results layout | results/exec_tests.csv, exec_summary.csv, exec_errors.csv keyed by suite; a rerun replaces that suite's rows | Phase 11 report builds only from these CSVs |
| 2026-10-13 | 4 | Per-test coverage on Python 3.14 | Force `COVERAGE_CORE=ctrace` for every coverage run | Default `sysmon` core only reports each line once, so `--cov-context=test` lost 98 of 115 per-test contexts (verified); ctrace gives all 115 |
| 2026-10-13 | 4 | Import-time lines | Lines executed at import (empty context) count for a unit once >=1 of its tests passes, but are not attributed to any test | Needed to reproduce the 246/246 baseline; module-level code is run by collection |
| 2026-10-13 | 4 | Branch coverage | Branch arcs taken from coverage.py's own analysis (multi-line translated); developer suite = 54/58 branches (93.1%), identical to `coverage report` | Cross-checked against coverage.py total (4 missing branches) |
| 2026-10-13 | 4 | Which tests count | A test counts only if it passed in the coverage run and in all 3 phase-3 repeats | Brief: only passing tests count; excludes flaky tests |
| 2026-10-13 | 4 | Tooling accident | `ruff --fix` touched generated samples under data/; fixed by excluding data/ and results/ in ruff config and rebuilding samples verbatim from calls.jsonl | Generated artefacts must stay byte-identical to the LLM output |
