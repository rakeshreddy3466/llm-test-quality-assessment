### Executability

| Suite | Units | Collect rate | Tests | Pass rate (mean of 3) | Stable pass rate | Flaky rate |
|---|---|---|---|---|---|---|
| developer | 3/3 | 100.0 % | 115 | 100.0 % | 100.0 % | 0.0 % |
| main_sonnet55_v1 | 15/15 | 100.0 % | 294 | 97.6 % | 97.6 % | 0.0 % |
| mr_mr1a_binary_sensor | 5/5 | 100.0 % | 128 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr1b_binary_sensor | 5/5 | 100.0 % | 160 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr1c_binary_sensor | 5/5 | 100.0 % | 117 | 100.0 % | 100.0 % | 0.0 % |

**Failure types of non-passing tests**

| Suite | Error type | Tests |
|---|---|---|
| main_sonnet55_v1 | RuntimeError | 6 |
| main_sonnet55_v1 | AssertionError | 1 |

### Coverage and mutation score (suite level)

Developer rows per target are the matching developer file; the LLM rows are the union over the k = 5 samples of that target.

| Target / scope | Suite | Tests passing | Line cov. | Branch cov. | Mutation score (global) | Mutation score (covered) |
|---|---|---|---|---|---|---|
| all | developer | 115 | 100.0 % | 93.1 % | 78.7 % | 78.7 % |
| all | LLM (union of k=5) | 287 | 99.6 % | 96.5 % | 81.1 % | 81.1 % |
| target:binary_sensor | developer | 97 | 86.2 % | 75.9 % | 59.8 % | 62.0 % |
| target:binary_sensor | LLM (union of k=5) | 145 | 86.6 % | 77.6 % | 59.2 % | 82.9 % |
| target:config_flow | developer | 9 | 84.2 % | 56.9 % | 47.6 % | 59.1 % |
| target:config_flow | LLM (union of k=5) | 80 | 76.8 % | 51.7 % | 12.2 % | 62.5 % |
| target:init | developer | 9 | 65.8 % | 25.9 % | 54.3 % | 70.6 % |
| target:init | LLM (union of k=5) | 62 | 74.4 % | 53.4 % | 57.9 % | 75.4 % |

### Per file / per sample

| Target | Developer file | LLM samples (mean ± sd, k=5) |
|---|---|---|
| binary_sensor - valid tests | 97 | 29.0 ± 4.9 |
| binary_sensor - line cov. | 86.2 % | 86.6 % ± 0.0 % |
| binary_sensor - branch cov. | 75.9 % | 77.6 % ± 0.0 % |
| binary_sensor - mutation score (global) | 59.8 % | 56.0 % ± 2.9 % |
| config_flow - valid tests | 9 | 16.0 ± 2.1 |
| config_flow - line cov. | 84.2 % | 48.9 % ± 15.6 % |
| config_flow - branch cov. | 56.9 % | 13.1 % ± 21.6 % |
| config_flow - mutation score (global) | 47.6 % | 5.4 % ± 3.8 % |
| init - valid tests | 9 | 12.4 ± 3.2 |
| init - line cov. | 65.8 % | 68.2 % ± 0.9 % |
| init - branch cov. | 25.9 % | 33.4 % ± 4.0 % |
| init - mutation score (global) | 54.3 % | 50.0 % ± 2.0 % |

### Traceability, smells, relevance, completeness

Behaviour list is a DRAFT (needs human check); completeness is relative to the behaviours the developer tests reach.

| Suite | Trace (name target) | Trace (declared target) | Declared present | Smelly tests | Smell density | Relevance | Completeness |
|---|---|---|---|---|---|---|---|
| developer | 0.378 | n/a | n/a | 98.3 % | 2.496 | 99.1 % | 100.0 % |
| LLM | 0.301 | 0.533 | 92.0 % | 44.2 % | 0.662 | 91.6 % | 100.0 % |

### Test smells (share of valid tests with the smell)

| Smell | developer | LLM |
|---|---|---|
| assertion_roulette | 97.4 % | 20.2 % |
| duplicate_assert | 6.1 % | 3.8 % |
| magic_number | 60.0 % | 27.2 % |
| conditional_logic | 79.1 % | 0.0 % |
| no_assertion | 0.0 % | 5.6 % |
| try_except | 0.0 % | 0.0 % |
| sleepy_test | 0.0 % | 0.0 % |
| redundant_print | 0.0 % | 0.0 % |
| eager_test | 0.0 % | 0.0 % |
| empty_test | 0.0 % | 0.0 % |

### RQ3 metamorphic sensitivity

pending: results/mr_metrics.csv not found.

### RQ2 agreement with manual review

pending manual review (manual_review/sample_rated.csv not present).
