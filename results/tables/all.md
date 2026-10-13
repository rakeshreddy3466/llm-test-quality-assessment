### Executability

| Suite | Units | Collect rate | Tests | Pass rate (mean of 3) | Stable pass rate | Flaky rate |
|---|---|---|---|---|---|---|
| developer | 3/3 | 100.0 % | 115 | 100.0 % | 100.0 % | 0.0 % |
| main_sonnet55_v1 | 15/15 | 100.0 % | 294 | 97.6 % | 97.6 % | 0.0 % |
| mr_mr1a_binary_sensor | 5/5 | 100.0 % | 128 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr1b_binary_sensor | 5/5 | 100.0 % | 160 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr1c_binary_sensor | 5/5 | 100.0 % | 117 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr2_binary_sensor | 5/5 | 100.0 % | 160 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr3_binary_sensor | 5/5 | 100.0 % | 190 | 100.0 % | 100.0 % | 0.0 % |
| mr_mr4_binary_sensor | 5/5 | 100.0 % | 146 | 100.0 % | 100.0 % | 0.0 % |

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

### RQ3 metamorphic sensitivity (binary_sensor target, n = 5 samples per variant)

| Variant | Metric | Baseline mean (sd) | Variant mean | In baseline range | MWU p | Cliff's delta | Effect |
|---|---|---|---|---|---|---|---|
| mr1a | valid_tests | 29.000 (4.899) | 25.600 | 60 % | 0.2933 | -0.44 | medium |
| mr1a | line_cov | 0.866 (0.000) | 0.872 | 80 % | 0.4237 | 0.2 | small |
| mr1a | branch_cov | 0.776 (0.000) | 0.786 | 80 % | 0.4237 | 0.2 | small |
| mr1a | mut_global | 0.560 (0.029) | 0.561 | 80 % | 1.0 | -0.04 | negligible |
| mr1a | trace_name | 0.225 (0.080) | 0.252 | 100 % | 0.462 | 0.32 | small |
| mr1a | smell_density | 0.634 (0.120) | 0.710 | 40 % | 1.0 | -0.04 | negligible |
| mr1b | valid_tests | 29.000 (4.899) | 32.000 | 100 % | 0.3398 | 0.4 | medium |
| mr1b | line_cov | 0.866 (0.000) | 0.866 | 100 % | 1.0 | 0.0 | negligible |
| mr1b | branch_cov | 0.776 (0.000) | 0.776 | 100 % | 1.0 | 0.0 | negligible |
| mr1b | mut_global | 0.560 (0.029) | 0.581 | 100 % | 0.2918 | 0.44 | medium |
| mr1b | trace_name | 0.225 (0.080) | 0.220 | 100 % | 1.0 | 0.04 | negligible |
| mr1b | smell_density | 0.634 (0.120) | 0.961 | 20 % | 0.0952 | 0.68 | large |
| mr1c | valid_tests | 29.000 (4.899) | 23.400 | 80 % | 0.14 | -0.6 | large |
| mr1c | line_cov | 0.866 (0.000) | 0.863 | 80 % | 0.4237 | -0.2 | small |
| mr1c | branch_cov | 0.776 (0.000) | 0.765 | 60 % | 0.1797 | -0.4 | medium |
| mr1c | mut_global | 0.560 (0.029) | 0.526 | 80 % | 0.0917 | -0.68 | large |
| mr1c | trace_name | 0.225 (0.080) | 0.240 | 80 % | 0.5476 | 0.28 | small |
| mr1c | smell_density | 0.634 (0.120) | 0.757 | 20 % | 0.0317 | 0.84 | large |
| mr2 | valid_tests | 29.000 (4.899) | 32.000 | 80 % | 0.3976 | 0.36 | medium |
| mr2 | line_cov | 0.866 (0.000) | 0.862 | 80 % | 0.4237 | -0.2 | small |
| mr2 | branch_cov | 0.776 (0.000) | 0.765 | 80 % | 0.4237 | -0.2 | small |
| mr2 | mut_global | 0.560 (0.029) | 0.572 | 100 % | 0.5993 | 0.24 | small |
| mr2 | trace_name | 0.225 (0.080) | 0.236 | 80 % | 1.0 | 0.04 | negligible |
| mr2 | smell_density | 0.634 (0.120) | 0.687 | 80 % | 1.0 | 0.04 | negligible |
| mr3 | valid_tests | 29.000 (4.899) | 38.000 | 20 % | 0.0345 | 0.84 | large |
| mr3 | line_cov | 0.866 (0.000) | 0.866 | 100 % | 1.0 | 0.0 | negligible |
| mr3 | branch_cov | 0.776 (0.000) | 0.776 | 100 % | 1.0 | 0.0 | negligible |
| mr3 | mut_global | 0.560 (0.029) | 0.581 | 100 % | 0.2873 | 0.44 | medium |
| mr3 | trace_name | 0.225 (0.080) | 0.237 | 100 % | 0.8413 | 0.12 | negligible |
| mr3 | smell_density | 0.634 (0.120) | 0.525 | 40 % | 0.3095 | -0.44 | medium |
| mr4 | valid_tests | 29.000 (4.899) | 29.200 | 100 % | 0.8237 | 0.12 | negligible |
| mr4 | line_cov | 0.866 (0.000) | 0.862 | 80 % | 0.4237 | -0.2 | small |
| mr4 | branch_cov | 0.776 (0.000) | 0.765 | 80 % | 0.4237 | -0.2 | small |
| mr4 | mut_global | 0.560 (0.029) | 0.570 | 100 % | 0.7518 | 0.16 | small |
| mr4 | trace_name | 0.225 (0.080) | 0.206 | 60 % | 0.6905 | -0.2 | small |
| mr4 | smell_density | 0.634 (0.120) | 0.787 | 20 % | 0.0749 | 0.72 | large |
| mr1_pooled | valid_tests | 29.000 (4.899) | 27.000 | 80 % | 0.5113 | -0.2133 | small |
| mr1_pooled | line_cov | 0.866 (0.000) | 0.867 | 87 % | 1.0 | 0.0 | negligible |
| mr1_pooled | branch_cov | 0.776 (0.000) | 0.776 | 80 % | 0.7789 | -0.0667 | negligible |
| mr1_pooled | mut_global | 0.560 (0.029) | 0.556 | 87 % | 0.7918 | -0.0933 | negligible |
| mr1_pooled | trace_name | 0.225 (0.080) | 0.238 | 93 % | 0.5117 | 0.2133 | small |
| mr1_pooled | smell_density | 0.634 (0.120) | 0.809 | 27 % | 0.1186 | 0.4933 | large |

**Overlap of covered lines and of killed mutants**

| Variant | Set | Noise floor (same prompt) | Variant vs original | MWU p | Cliff's delta |
|---|---|---|---|---|---|
| mr1a | lines | 1.000 | 0.990 | 0.1401 | -0.2 |
| mr1a | killed | 0.925 | 0.916 | 0.7284 | -0.08 |
| mr1b | lines | 1.000 | 1.000 | 1.0 | 0.0 |
| mr1b | killed | 0.925 | 0.946 | 0.1293 | 0.336 |
| mr1c | lines | 1.000 | 0.995 | 0.1401 | -0.2 |
| mr1c | killed | 0.925 | 0.922 | 1.0 | 0.0 |
| mr2 | lines | 1.000 | 0.993 | 0.1401 | -0.2 |
| mr2 | killed | 0.925 | 0.944 | 0.2208 | 0.272 |
| mr3 | lines | 1.000 | 1.000 | 1.0 | 0.0 |
| mr3 | killed | 0.925 | 0.942 | 0.2341 | 0.264 |
| mr4 | lines | 1.000 | 0.993 | 0.1401 | -0.2 |
| mr4 | killed | 0.925 | 0.942 | 0.2206 | 0.272 |
| mr1_pooled | lines | 1.000 | 0.995 | 0.2273 | -0.1333 |
| mr1_pooled | killed | 0.925 | 0.928 | 0.6672 | 0.0853 |

### RQ2 agreement with manual review

| Scale | n | Spearman rho | p | Weighted kappa |
|---|---|---|---|---|
| relevance | 60 | 0.302 | 0.019 | 0.104 |
| clarity | 60 | 0.072 | 0.586 | 0.007 |
| maintainability | 60 | 0.104 | 0.427 | 0.047 |
| oracle_strength | 60 | 0.189 | 0.148 | -0.001 |
