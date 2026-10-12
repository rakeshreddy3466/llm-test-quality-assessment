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
