# Results

Price date for cost: 2026-10-17 (input $0.1/M, output $0.5/M tokens).

## Table 6.1 - comparison with baselines

| Method | Precision | Recall | FPR | Level-1 | Top-1 | Top-3 | Tokens/window | Cost/window (USD) |
|---|---|---|---|---|---|---|---|---|
| threshold | 1.000 | 0.842 | 0.000 | n/a | n/a | n/a | 0 | 0.0000 |
| iforest | 0.655 | 1.000 | 0.857 | n/a | n/a | n/a | 0 | 0.0000 |
| cfn_drift | 0.688 | 0.579 | 0.429 | 1.000 | 1.000 | 1.000 | 0 | 0.0000 |
| agent-L0 | 1.000 | 0.649 | 0.000 | 0.595 | 0.595 | 0.649 | 36631 | 0.0048 |
| agent-L1 | 1.000 | 0.825 | 0.000 | 0.745 | 0.723 | 0.745 | 320908 | 0.0152 |
| agent-L2 | 1.000 | 0.772 | 0.000 | 0.727 | 0.682 | 0.682 | 395322 | 0.0178 |
| agent-L3 | 0.950 | 1.000 | 0.086 | 1.000 | 0.789 | 0.789 | 191684 | 0.0101 |
| agent-L4 | 1.000 | 0.982 | 0.000 | 1.000 | 1.000 | 1.000 | 208016 | 0.0098 |

Values are mean ± standard deviation across repetitions; localisation is computed on detected symptomatic incidents only (Section 2.6).

## Time to detect (minutes)

| Method | Median | Q1 | Q3 | n |
|---|---|---|---|---|
| cfn_drift | 8.117 | 8.100 | 8.117 | 33 |
| iforest | 1.600 | 1.267 | 1.800 | 57 |
| threshold | 1.675 | 1.333 | 1.929 | 48 |
