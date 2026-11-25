# RTLProbe baseline training report: `in_sample_smoke_test`

> IN-SAMPLE SMOKE TEST. Models were trained and scored on the SAME cases. These numbers check that the pipeline runs end to end; they are not validation or test performance and must not be reported as such.

## Run

- Package check: passed, 20 cases, 7180 candidate rows per condition
- Mode: `dev-smoke`; train 20 cases, validation 0, test 20
- Feature version: `rtlprobe-baseline-features-v2`; encoder `microsoft/unixcoder-base` @ `5604afdc964f`
- Models: logreg, lgbm, mlp; seeds [0, 1, 2]; model_config.json sha256 `ad4a21c9c963`
- Python 3.12.10 on Windows-11-10.0.26200-SP0; 27.9 s

Metrics are per defect: Top-k = share of defects whose bug line ranks in the top k; MRR = mean reciprocal rank; ties share their average rank. Models show mean ± sd over seeds.

## C0: test (7180 candidate rows, 6 features)

| Method | Top-1 | Top-5 | Top-10 | MRR | Median rank |
|---|---|---|---|---|---|
| reference: random | 0.00 | 0.01 | 0.03 | 0.018 | 180.0 |
| reference: source_order | 0.00 | 0.00 | 0.00 | 0.019 | 123.5 |
| reference: lexical_log_overlap | 0.00 | 0.00 | 0.00 | 0.010 | 139.0 |
| logreg | 0.00 ± 0.00 | 0.05 ± 0.00 | 0.10 ± 0.00 | 0.042 ± 0.000 | 39.0 ± 0.0 |
| lgbm | 0.85 ± 0.00 | 0.95 ± 0.00 | 1.00 ± 0.00 | 0.898 ± 0.000 | 1.0 ± 0.0 |
| mlp | 0.00 ± 0.00 | 0.12 ± 0.06 | 0.27 ± 0.02 | 0.091 ± 0.019 | 21.0 ± 0.7 |

## C1: test (7180 candidate rows, 14 features)

| Method | Top-1 | Top-5 | Top-10 | MRR | Median rank |
|---|---|---|---|---|---|
| reference: random | 0.00 | 0.01 | 0.03 | 0.018 | 180.0 |
| reference: source_order | 0.00 | 0.00 | 0.00 | 0.019 | 123.5 |
| reference: lexical_log_overlap | 0.00 | 0.00 | 0.00 | 0.010 | 139.0 |
| logreg | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.05 ± 0.00 | 0.038 ± 0.000 | 41.0 ± 0.0 |
| lgbm | 0.85 ± 0.00 | 1.00 ± 0.00 | 1.00 ± 0.00 | 0.900 ± 0.000 | 1.0 ± 0.0 |
| mlp | 0.02 ± 0.02 | 0.18 ± 0.02 | 0.25 ± 0.00 | 0.113 ± 0.017 | 21.0 ± 1.5 |

## C2: test (7180 candidate rows, 11 features)

| Method | Top-1 | Top-5 | Top-10 | MRR | Median rank |
|---|---|---|---|---|---|
| reference: random | 0.00 | 0.01 | 0.03 | 0.018 | 180.0 |
| reference: source_order | 0.00 | 0.00 | 0.00 | 0.019 | 123.5 |
| reference: lexical_log_overlap | 0.00 | 0.00 | 0.00 | 0.010 | 139.0 |
| logreg | 0.00 ± 0.00 | 0.05 ± 0.00 | 0.15 ± 0.00 | 0.058 ± 0.000 | 39.0 ± 0.0 |
| lgbm | 0.90 ± 0.00 | 1.00 ± 0.00 | 1.00 ± 0.00 | 0.929 ± 0.000 | 1.0 ± 0.0 |
| mlp | 0.03 ± 0.02 | 0.32 ± 0.02 | 0.40 ± 0.04 | 0.161 ± 0.016 | 17.8 ± 3.7 |

## C3: test (7180 candidate rows, 7 features)

| Method | Top-1 | Top-5 | Top-10 | MRR | Median rank |
|---|---|---|---|---|---|
| reference: random | 0.00 | 0.01 | 0.03 | 0.018 | 180.0 |
| reference: source_order | 0.00 | 0.00 | 0.00 | 0.019 | 123.5 |
| reference: lexical_log_overlap | 0.00 | 0.00 | 0.00 | 0.010 | 139.0 |
| logreg | 0.00 ± 0.00 | 0.05 ± 0.00 | 0.15 ± 0.00 | 0.053 ± 0.000 | 37.5 ± 0.0 |
| lgbm | 1.00 ± 0.00 | 1.00 ± 0.00 | 1.00 ± 0.00 | 1.000 ± 0.000 | 1.0 ± 0.0 |
| mlp | 0.03 ± 0.02 | 0.18 ± 0.02 | 0.32 ± 0.02 | 0.121 ± 0.026 | 20.3 ± 0.2 |

## C4: test (7180 candidate rows, 20 features)

| Method | Top-1 | Top-5 | Top-10 | MRR | Median rank |
|---|---|---|---|---|---|
| reference: random | 0.00 | 0.01 | 0.03 | 0.018 | 180.0 |
| reference: source_order | 0.00 | 0.00 | 0.00 | 0.019 | 123.5 |
| reference: lexical_log_overlap | 0.00 | 0.00 | 0.00 | 0.010 | 139.0 |
| logreg | 0.00 ± 0.00 | 0.05 ± 0.00 | 0.10 ± 0.00 | 0.057 ± 0.000 | 32.0 ± 0.0 |
| lgbm | 1.00 ± 0.00 | 1.00 ± 0.00 | 1.00 ± 0.00 | 1.000 ± 0.000 | 1.0 ± 0.0 |
| mlp | 0.03 ± 0.02 | 0.33 ± 0.02 | 0.50 ± 0.00 | 0.168 ± 0.008 | 9.3 ± 0.6 |

## Notes

- Per-candidate scores with file, line and rank are in each condition's `predictions.jsonl`.
- Per-case ranks for every seed are in `run.json`.
- See LIMITATIONS.md in the training folder for known limits.
