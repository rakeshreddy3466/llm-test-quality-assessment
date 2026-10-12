# PLAN (verbatim copy of the project brief; survives a new session)

You will build my full research project in this repo, phase by phase, mostly on your own.

## PROJECT
"Automated Quality Assessment of LLM Generated Unit Tests: A Home Assistant Case Study".
GitHub repo: rakeshreddy3466/llm-test-quality-assessment (remote "origin", branch main).

## ENVIRONMENT
- Home Assistant core: ~/code/ha-core, branch study-pinned, tag 2026.10.1.
- Home Assistant venv: ~/code/ha-core/.venv (NOT venv). Always run HA tests with
  ~/code/ha-core/.venv/bin/python -m pytest, from inside ~/code/ha-core.
- First task: in .env set HA_PYTHON=/Users/rakeshreddy/code/ha-core/.venv/bin/python. Never print the API key.
- My API key is in .env as ANTHROPIC_API_KEY. Never print it, never commit .env.
- System under test: homeassistant/components/threshold.
  Developer tests in tests/components/threshold are the human baseline.
- Baseline already measured: 115 developer tests pass in 2.4 s with 100% line coverage (246 statements).
  Because line coverage is already 100%, treat branch coverage and mutation score as the main ways to
  compare test quality, and also report the coverage of the LLM suite on its own.

## RESEARCH QUESTIONS
RQ1: How do LLM generated tests compare with the developers' tests on executability, coverage,
     mutation score, traceability, maintainability (test smells), relevance and completeness?
RQ2: How well do the automatic scores agree with a blinded manual review of a sample
     (Spearman rho, weighted Cohen's kappa)?
RQ3: How sensitive are generated tests to metamorphic changes (paraphrased prompt, renamed local
     variables, reordered functions, stripped comments), compared with the normal noise between
     repeated samples?

## ARCHITECTURE
- Python package "testquality" in src/, managed with uv (Python 3.12+), its own venv. CLI with subcommands.
- Run HA tests only as a subprocess inside ~/code/ha-core.
- Copy generated tests into ~/code/ha-core/tests/components/threshold/_llm_generated/<run_id>/
  (with __init__.py) and delete them after each run. Never edit any other Home Assistant file.
- LLM: Anthropic Messages API. Main model claude-sonnet-5-5, cheap model claude-haiku-5-5.
  Do NOT send temperature, top_p or top_k (these models reject them). Generate k=5 samples per prompt
  to measure the noise floor. Check the current model IDs and prices in the official docs before the
  first real call.
- Never show the developer tests to the LLM (data leakage). Each generated test must have a docstring with
  "Behaviour: <one sentence>" and "Target: <function name>".
- Log EVERY LLM call to data/runs/<run_id>/calls.jsonl (model, full prompt, full response, usage,
  params, timestamp, prompt version).

## PHASES (in order; after each phase: run its checks, update PROGRESS.md and docs/DECISIONS.md,
commit with message "Phase N: <name>", and git push origin main)
1. Skeleton: pyproject.toml, config.yaml, CLI stubs, tests of the tool, README skeleton, MIT LICENSE,
   short CLAUDE.md, .gitignore already exists (keep .env ignored).
2. Generation pipeline with full logging, --dry-run and a cost estimate.
3. Executability: collect rate, pass rate over 3 runs, flaky rate, error types. Developer tests as baseline.
4. Coverage: suite line and branch coverage, and per test coverage using --cov-context=test.
   Only passing tests count.
5. Mutation testing with mutmut 3.x on threshold only (mutate_only_covered_lines).
   Mutation score = killed/(killed+survived); report timeouts separately.
   If mutmut does not work in the HA tree within about 1 hour of trying, build a small AST mutator
   fallback (relational op swap, arithmetic op swap, constant +1/-1, boolean negation, return value
   replacement) that also gives a per test kill matrix, and explain it in DECISIONS.md.
6. Traceability: name similarity, coverage based target (last call before the first assert),
   declared Target; score 0 / 0.5 / 1. Write docs/metrics.md defining every metric before coding.
7. Test smells with a custom AST detector (empty test, no assertion, assertion roulette, duplicate assert,
   magic number, conditional logic, sleepy test, redundant print, eager test, try/except instead of
   pytest.raises), each smell with one positive and one negative unit test.
8. Relevance and completeness: draft data/behaviours.yaml (15 to 40 behaviours of threshold with code
   line ranges) and map tests to behaviours. Mark the YAML as "DRAFT, needs human check".
9. Manual review: create manual_review/rubric.md (1 to 5 scales for relevance, clarity of purpose,
   maintainability, oracle strength) and a blinded sample of 60 tests (20 developer, 40 LLM, fixed seed,
   origin hidden) in manual_review/sample_blinded.csv. Then STOP and tell me. I will fill in the ratings
   myself. Never fill ratings yourself. While waiting, continue with phases 10 to 12.
10. Metamorphic experiment: MR1 paraphrased prompt x3, MR2 rename local variables, MR3 reorder functions,
    MR4 strip comments, each with tests proving the change keeps the meaning. Compare each variant with
    the noise floor (Mann Whitney U, Cliff's delta, Jaccard of covered lines and killed mutants).
11. Results: report.py builds all tables (Markdown) and figures (PNG) only from results/*.csv.
    One command (make all) rebuilds everything.
12. GitHub Actions CI (ruff + the tool's own pytest, no API key, no HA), CI badge in README.
13. Report: report/report.md (Introduction, Related work, Method, Setup, Results, Threats to validity,
    Conclusion) with real, correct citations in report/refs.bib (TestGen-LLM at Meta, TestPilot, CodaMosa,
    ChatUniTest, CoverUp, Siddiq et al. on test smells in LLM generated tests, PyNose, TCTracer, ReCode,
    Wang et al. survey on LLMs in software testing). Build report/report.pdf with pandoc.
    Fill the README with the results table, key findings and how to reproduce.

## RULES
- Work autonomously. Do not ask me small questions; make a sensible choice and log it in
  docs/DECISIONS.md (columns: Date | Phase | What you proposed | What was decided | Why).
- STOP and ask me only for: (a) any API run expected to cost more than 3 USD (show the estimate first),
  (b) the manual review in phase 9, (c) anything that deletes data or rewrites git history.
- Never invent numbers. Every number in README and report must come from results/*.csv.
  Until my manual ratings exist, write "pending manual review" for RQ2.
- Never invent citations. If you are not sure a reference is correct, mark it "TO VERIFY".
- Keep PROGRESS.md updated so that if this session stops, a new session can read it and continue.
- At the end of each phase, give me a 3 line summary in simple English of what was built and what it means.
