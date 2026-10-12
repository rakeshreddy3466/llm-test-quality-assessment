# Decisions log

| Date | Phase | What you proposed | What was decided | Why |
|---|---|---|---|---|
| 2026-10-12 | 1 | HA_PYTHON pointed at `venv` in .env and .env.example | Changed both to `.venv/bin/python` | HA checkout uses `.venv`; per brief |
| 2026-10-12 | 1 | CLI framework | argparse (stdlib), stub subcommands exit code 2 | No extra dependency; stubs must not look like success |
| 2026-10-12 | 1 | Build backend / layout | hatchling, src layout, dev tools in `[dependency-groups]`, analysis libs as optional extra | Keeps phase 1 install light; uv supports dependency-groups |
| 2026-10-12 | 1 | Review seed | 20261012 (date of project start) in config.yaml | Fixed seed for reproducible blinded sample |
