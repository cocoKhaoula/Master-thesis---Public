# Results

Price date for cost: 2026-10-17 (input $0.1/M, output $0.5/M tokens).

## Table 6.1 - comparison with baselines

| Method | Precision | Recall | FPR | Level-1 | Top-1 | Top-3 | Tokens/window | Cost/window (USD) |
|---|---|---|---|---|---|---|---|---|
| threshold | 1.000 | 1.000 | 0.000 | n/a | n/a | n/a | 0 | 0.0000 |
| iforest | 0.500 | 1.000 | 1.000 | n/a | n/a | n/a | 0 | 0.0000 |
| cfn_drift | 0.400 | 0.667 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0.0000 |
| agent-L0 | 1.000 | 1.000 | 0.000 | 0.333 | 0.333 | 0.667 | 36024 | 0.0048 |
| agent-L1 | 1.000 | 1.000 | 0.000 | 0.667 | 0.667 | 0.667 | 374941 | 0.0165 |
| agent-L2 | 1.000 | 1.000 | 0.000 | 0.667 | 0.333 | 0.333 | 434854 | 0.0179 |
| agent-L3 | 1.000 | 1.000 | 0.000 | 1.000 | 0.667 | 0.667 | 196685 | 0.0104 |
| agent-L4 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 | 195378 | 0.0090 |

Values are mean ± standard deviation across repetitions; localisation is computed on detected symptomatic incidents only (Section 2.6).

## Time to detect (minutes)

| Method | Median | Q1 | Q3 | n |
|---|---|---|---|---|
| cfn_drift | 8.108 | 8.104 | 8.113 | 2 |
| iforest | 1.400 | 1.258 | 1.408 | 3 |
| threshold | 1.400 | 1.258 | 1.408 | 3 |
