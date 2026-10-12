# Metric definitions

Every number in the README and the report comes from `results/*.csv` produced by the tool.
This file defines each metric **before** it is implemented (phase 6). Units of analysis:

- **suite**: a labelled set of test files (`developer`, or a generation run id such as
  `main_sonnet55_v1`).
- **unit**: one test file (a developer file, or one LLM sample = one prompt x one sample index).
- **test**: one `test_*` function (parametrised cases are separate tests, id includes `[param]`).
- **target**: the prompt's target module (`binary_sensor`, `config_flow`, `init`); developer
  files are their own units.

System under test (SUT): `homeassistant/components/threshold` at tag 2026.10.1:
246 statements, 58 branch arcs, 164 mutmut mutants.

## 1. Executability (phase 3) — `results/exec_*.csv`

| Metric | Definition |
|---|---|
| collect_rate | units with >= 1 collected test (no collection error) / units requested. Samples lost before execution (truncated output, no code block) count as not collected. |
| pass_rate | in one repeat: passed / (passed + failed + error); skipped and collection errors excluded. Reported as mean/min/max over 3 repeats. |
| stable_pass_rate | tests passing in all 3 repeats / tests collected. |
| flaky_rate | tests whose outcome differs between repeats / tests collected. |
| error types | first failure of each non-passing test, classified from the junit message (AssertionError, ModuleNotFoundError, ImportError, SyntaxError, FixtureLookupError, TypeError, ...). |

A test is **valid** (counts for all later metrics) only if it is a *stable pass*.

## 2. Coverage (phase 4) — `results/coverage_*.csv`

Measured with coverage.py through pytest-cov on the SUT only, `--cov-branch`,
`--cov-context=test`, `COVERAGE_CORE=ctrace` (see DECISIONS).

| Metric | Definition |
|---|---|
| line_cov | covered statements / 246, union over valid tests of the unit (or suite) plus import-time lines once >= 1 test passes. |
| branch_cov | taken branch arcs / 58 (coverage.py definition, multi-line translated). |
| per-test lines | statements executed while the test runs (setup, call, teardown). |
| unique_lines | lines covered by this test and by no other valid test of the same unit. |
| suite coverage | union over all valid tests of all units of the suite ("all") or of one target. |

Because developer line coverage is already 100 %, **branch coverage and mutation score** are the
discriminating measures; the LLM suite is also reported on its own.

## 3. Mutation score (phase 5) — `results/mutation_*.csv`

mutmut 3.8.0, 164 mutants, `mutate_only_covered_lines = false` (fixed mutant population).

| Metric | Definition |
|---|---|
| killed / survived / timeout / no_tests | mutmut exit-code classes. `no_tests` = no test of the unit executes the mutated function. Timeouts are reported separately and are not killed. |
| score_covered | killed / (killed + survived) — the definition of the brief. Flatters narrow suites. |
| score_global | killed / 164 — fixed denominator, the comparable score across suites. |
| suite union | a mutant is killed if any unit of the suite kills it. |

Tests that are not stable passes are deselected so that failing tests never kill mutants.

## 4. Traceability (phase 6) — `results/trace_*.csv`

Question: *does the test visibly test the function it appears to test?* Three signals per test:

1. **Name target** — the SUT function / method / class whose name best matches the test name.
   Tokens: split on `_` and camelCase, lower-case, drop `test`, `async`, a trailing plural `s`,
   parametrisation. Similarity = Jaccard of token sets; best candidate with similarity >= 0.2,
   else none. Candidates are all functions, methods and classes of the component.
2. **Coverage target** — the last SUT function entered *before the first assertion* of the test
   (dynamic trace under `sys.settrace`; first assertion = first `assert` statement or call of a
   method named `assert*`). `called` = set of SUT functions entered before that point.
3. **Declared target** — the name in the docstring line `Target: <name>` (LLM tests only).

Score per test (0 / 0.5 / 1), for a claimed target *X* (name target or declared target):

- **1** — *X* equals the coverage target;
- **0.5** — *X* is in `called`, or is the class of the coverage target (partial support);
- **0** — otherwise, or if the test has no assertion, calls no SUT code, or has no candidate.

Reported: `trace_name` (all tests, comparable between developers and LLM),
`trace_declared` (LLM tests; developer tests have no declaration), and suite means.
`declared_missing_rate` = fraction of LLM tests without a parsable `Behaviour:` and `Target:`.

## 5. Test smells (phase 7) — `results/smells_*.csv`

Custom AST detector, per test function. Smells: empty test, no assertion, assertion roulette
(> 3 asserts without messages), duplicate assert, magic number, conditional logic, sleepy test,
redundant print, eager test (> 3 distinct SUT functions called before the end — from the dynamic
trace; fallback: distinct attribute calls), try/except instead of `pytest.raises`.
`smell_density` = smell instances / tests; `smelly_rate` = tests with >= 1 smell / tests.
Exact thresholds are defined in `src/testquality/smells.py` and mirrored in phase-7 DECISIONS.

## 6. Relevance and completeness (phase 8) — `results/behaviour_*.csv`

`data/behaviours.yaml` lists 15–40 behaviours of the SUT with code line ranges (DRAFT, needs
human check). A test is mapped to a behaviour when it is valid and covers >= 50 % of the
behaviour's lines (statements) **and** covers at least one line of it that the test does not share
with *all* behaviours (non-trivial).

| Metric | Definition |
|---|---|
| relevance | valid tests mapped to >= 1 behaviour / valid tests (tests that exercise no listed behaviour are irrelevant boiler-plate). |
| completeness | behaviours mapped to >= 1 valid test / behaviours. |
| weighted completeness | weighted by lines of each behaviour. |

## 7. Manual review agreement — RQ2 (phase 9, pending)

Four 1–5 scales (relevance, clarity of purpose, maintainability, oracle strength) on 60 blinded
tests. Agreement between the automatic score and the manual rating: Spearman rho (per scale
against the matching automatic score) and linearly weighted Cohen's kappa after binning the
automatic score to 1–5. **Pending manual ratings; nothing is reported before they exist.**

## 8. Metamorphic sensitivity — RQ3 (phase 10)

Variants (MR1 paraphrased prompt x3, MR2 renamed local variables, MR3 reordered functions,
MR4 stripped comments) are compared with the noise floor between the k = 5 repeated samples of
the same prompt on: valid test count, line / branch coverage, mutation score (per unit),
Mann-Whitney U (two-sided), Cliff's delta (|d| < 0.147 negligible, < 0.33 small, < 0.474
medium, else large), and Jaccard similarity of covered lines and of killed mutants between
the variant and the original (compared with Jaccard between pairs of original samples).
