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
