# Manual review rubric

You rate **60 unit tests** of the Home Assistant `threshold` integration
(`homeassistant/components/threshold/`, tag 2026.10.1). The tests come from two sources, which
are **hidden**. Do not try to guess the source, and please do not open
`key_do_not_open_until_rated.csv` before all ratings are done.

Open `sample_blinded.csv`. For every row read `test_code` (and `context_code`, the helpers and
fixtures it uses) and fill the four columns **relevance, clarity, maintainability,
oracle_strength** with an integer from 1 to 5. Use `notes` freely (optional). Rate each test on
its own; rate each scale independently. Docstrings were normalised so that their format does not
reveal the source. The tests are presented in random order.

You may read the code under test (`binary_sensor.py`, `config_flow.py`, `__init__.py`,
`const.py`). You do not need to run anything.

## Scales

### 1. Relevance (is this a test that matters?)
| Score | Meaning |
|---|---|
| 1 | Tests nothing of the component (framework behaviour, trivial constant, tautology). |
| 2 | Tests a minor detail of the component; a defect here would hardly matter. |
| 3 | Tests a real behaviour, but a secondary or very narrow one. |
| 4 | Tests an important behaviour of the component. |
| 5 | Tests a core behaviour users depend on (state calculation, configuration, migration, setup). |

### 2. Clarity of purpose (do I understand what it checks and why?)
| Score | Meaning |
|---|---|
| 1 | Cannot tell what is being tested; name/doc misleading. |
| 2 | Purpose must be reverse-engineered from the code. |
| 3 | Purpose is guessable from the name or the code, doc missing or vague. |
| 4 | Name and/or doc state the purpose; minor ambiguities remain. |
| 5 | Name, doc and structure make the single behaviour under test obvious. |

### 3. Maintainability (how painful is this test to live with?)
Consider duplication, magic values, coupling to implementation details, structure
(arrange / act / assert), reliance on private attributes, use of helpers and parametrisation.
| Score | Meaning |
|---|---|
| 1 | Brittle or convoluted; any refactoring of the code breaks it, heavy duplication. |
| 2 | Hard to change; many hard-coded details or private-API coupling. |
| 3 | Acceptable; some duplication or unclear setup. |
| 4 | Clean; small issues only. |
| 5 | Minimal, well structured, robust against harmless refactorings. |

### 4. Oracle strength (would it fail if the behaviour were wrong?)
Think about plausible defects (wrong comparison operator, off-by-one at a limit, wrong state or
attribute, missing call) and whether the assertions would detect them.
| Score | Meaning |
|---|---|
| 1 | No meaningful assertion, or one that can never fail. |
| 2 | Weak: checks existence / type / "no exception" only. |
| 3 | Checks the main outcome but misses boundaries or side effects. |
| 4 | Checks outcome and relevant details; would catch most plausible defects. |
| 5 | Precise assertions on outcome, boundaries and side effects; would catch almost any defect. |

## Procedure
1. Rate in the order of `item_id` (R01...R60), one sitting if possible.
2. Integers 1-5 only; leave nothing blank (use 3 if truly undecidable, and say so in `notes`).
3. Save the file as `manual_review/sample_rated.csv` (keep `sample_blinded.csv` untouched).
4. Tell the assistant; only then are the automatic scores compared with your ratings (RQ2).

## What is compared afterwards
Relevance <-> behaviour mapping score; clarity <-> traceability; maintainability <-> smell
density (inverted); oracle strength <-> mutants killed per test. Metrics: Spearman rho and
linearly weighted Cohen's kappa (automatic scores binned to 1-5).
