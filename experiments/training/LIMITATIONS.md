# Known limitations and unfinished steps

Status on 2026-11-24, against `rtlprobe-baseline-starter-2026-11-22`.

## Data and evaluation

- **Only in-sample results exist.** All 20 starter cases are `development_only`,
  from one design (SHA-256) and one lineage (`secworks_crypto`). The smoke test trains
  and scores on the same cases. Its numbers show the pipeline runs end to end; they are
  not validation or test performance.
- **LightGBM's near-perfect in-sample score is memorisation**, not skill. With 20 cases
  and 200 trees it can fit every training case.
- **No held-out run yet.** `--mode held-out` is implemented and tested on synthetic
  group records (`test_splits.py`), but it has never run on real held-out data.
- **Split manifest format is assumed.** The reader expects
  `{"split_id", "train", "validation", "test"}` with sample IDs. It must be reconciled
  with the dataset owner's frozen manifest format when one is issued.
- **Validation is reported, not used.** Hyperparameters are fixed in `model_config.json`
  and not tuned; there is no early stopping (the MLP always runs 300 epochs).
- **Uncertainty is not estimated.** The ± values in the report are the spread over
  training seeds only. There are no bootstrap or group-level confidence intervals, and
  20 related cases cannot support a general claim.
- Candidate recall is trivially 100% on the starter (every true line is mapped). Misses
  are counted (`missed_true_site`) but not yet broken down by cause.

## Features

- **Anchor resolver is narrow.** The anchor is a top-module output port whose width
  equals the width of the value the checker compared. On the starter it is always
  `digest`. On other designs it may find no port or several ports; then anchor features
  are missing (NaN plus flag), not zero.
- **The graph is signal-level and conservative**, not exact cycle-level causality.
  Registers are inferred from non-blocking assignment left-hand sides. On SHA-256 almost
  every line is 1–3 graph steps from `digest`, so graph distance ties heavily and
  separates lines poorly on this design.
- **Waveform features map a line to signals by its left-hand-side names.** Lines with no
  left-hand side (conditions, case labels, declarations) get no waveform features; equal
  local names in different modules are merged.
- Specification similarity uses the frozen encoder only (no training on spec text).
- The first run downloads `microsoft/unixcoder-base` (pinned revision) and needs
  internet access; later runs use the embedding cache.
- Two structure features (`graph_fanout`, `graph_is_register`) go beyond the planned
  feature table; they are listed in the README.

## Scope not covered yet

- **Netlist evidence** (the fourth project modality) is not used. Only views C0–C4 are
  read; the raw view `M` is not.
- RTLCoder token surprise is provided only as a separate no-training reference
  (`rtlcoder_surprise.py`), not as a feature of the trained models; adding it as a
  feature changes the feature contract and is a team decision. It needs a CUDA GPU
  (8-bit weights), and SHA-256 may be in RTLCoder's pretraining data, so its score on
  the starter package may be optimistic.
- `predict.py` needs a package that passes full validation, which includes the
  supervision files, even when `--evaluate` is not used. Unlabelled packages are not
  supported yet.
- Tested on Windows 11 with Python 3.12.10 only. LightGBM runs with
  `deterministic=True`, but identical results on other platforms are not verified.
