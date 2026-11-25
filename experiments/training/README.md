# Bug-localization training pipeline (baselines)

This folder trains and evaluates rankers that sort a defect's candidate source lines
so the buggy line comes first. It was built against the
`rtlprobe-baseline-starter-2026-11-22` package and follows that package's README.

- **Models:** LightGBM LambdaMART, L2 logistic regression, and a small neural ranker
  (MLP with a within-case pairwise ranking loss).
- **Evidence views:** C0 code + log, C1 + graph, C2 + waveform, C3 + specification,
  C4 all of them.
- **Status:** only an in-sample smoke test on the 20 development cases exists
  (see [results](results/smoke-test-2026-11-24/report.md)). That is a pipeline
  check, not performance. Read [LIMITATIONS.md](LIMITATIONS.md) before using any
  number.

It is separate from `experiments/localization/`, which is a historical
heuristic pilot.

## Files

| File | Role |
|---|---|
| `run_baseline.py` | Single entry point: validate → features → split → train → predict → evaluate → report |
| `predict.py` | Load saved models from a run and rank the candidates of a package (optionally evaluate) |
| `loader.py` | Package integrity and label-join validation; evidence-only view; labels loaded separately |
| `features.py` | Versioned evidence-only features (`rtlprobe-baseline-features-v2`) |
| `embed.py` | Frozen UniXcoder encoder (`microsoft/unixcoder-base` @ `5604afdc…`), disk cache |
| `splits.py` | `dev-smoke` and `held-out` (train / validation / test) split readers with leakage refusal |
| `models.py` | Training-only preprocessing and the three models |
| `model_config.json` | All hyperparameters and default seeds (copied into every run) |
| `evaluate.py` | Per-defect Top-1/5/10, MRR, median rank, tie counts; prediction checks |
| `report.py` | Markdown report and console table from `run.json` |
| `test_handoff.py` | Handoff checks on scratch copies of a package |
| `test_splits.py` | Split-reader leakage tests on synthetic records |
| `rtlcoder_surprise.py` | Optional no-training reference: ranks lines by RTLCoder token surprise (needs a CUDA GPU) |
| `requirements-training.in` / `.lock.txt` | Direct pins / full resolved environment |
| `requirements-rtlcoder.in` | Extra pins for `rtlcoder_surprise.py` only |
| `results/smoke-test-2026-11-24/` | The 20-case in-sample smoke-test report (`report.md`, `run.json`) |

## 1. Set up

Python 3.11 or 3.12. Commands are run from this folder.

```sh
python -m venv .venv-training
source .venv-training/bin/activate            # Windows: .venv-training\Scripts\activate
python -m pip install -r requirements-training.in
# exact environment of the recorded run (CUDA 12.4 torch build):
# python -m pip install --extra-index-url https://download.pytorch.org/whl/cu124 -r requirements-training.lock.txt
```

A GPU is optional. The first run downloads the pinned UniXcoder model (internet needed)
and caches embeddings in `~/.cache/rtlprobe-training/unixcoder` (change with `--emb-cache`).

## 2. Input: the dataset package

The package is kept **outside this repository** and is never modified. Expected layout
(same as the starter package):

```text
integrity.json                SHA-256 of every other package file
metadata/samples.jsonl        one row per case: sample_id, candidate_count, candidate_inventory_id,
                              conditions[C0..C4, M] -> {path, manifest_sha256}
supervision/labels.jsonl      positive_candidate_ids, locations (path, line_1based, buggy_source_sha256)
supervision/groups.jsonl      split status, final_test_eligible, lineage/design/related-site/template groups
evidence/sample-<id>/<C0..C4|M>/
  manifest.json               condition, sample id, file hashes, source hashes
  candidates.json             every candidate line: candidate_id, path, line, text, syntax_kinds, lhs, ...
  common.json, checker.json   configuration and the buggy-run checker log
  rtl/...                     exact buggy RTL
  structure/graph.json, alignment.json        (C1, C4)
  waveform/trace.json, raw/failure.vcd        (C2, C4)
  specification/requirements.jsonl            (C3, C4)
```

Every run first re-checks the package: file hashes, per-view manifests, buggy-source
hashes, identical candidate sets across views, and labels pointing at existing
candidates. A changed byte or a bad label join stops the run.

**Split manifest** (needed for held-out mode; issued by the dataset owner):

```json
{"split_id": "name-of-frozen-split", "train": ["sample-…"], "validation": ["sample-…"], "test": ["sample-…"]}
```

`validation` is optional. The run is refused if a sample is unknown or in two
partitions, if any test sample is `development_only` or not `final_test_eligible`,
or if any two partitions share a lineage, design, related-site or operator-template group.

## 3. Commands (full pipeline)

Check the package and the pipeline (scratch copies only; the package is not touched):

```sh
python test_handoff.py PATH/TO/PACKAGE PATH/TO/SCRATCH
python -m unittest test_splits -v
```

Train and evaluate. The output folder must not exist yet:

```sh
# development package (all cases development_only): in-sample smoke test
python run_baseline.py --package PATH/TO/PACKAGE --out ../../outputs/training/smoke-YYYY-MM-DD --mode dev-smoke

# real evaluation once a frozen split exists
python run_baseline.py --package PATH/TO/PACKAGE --out ../../outputs/training/heldout-YYYY-MM-DD --mode held-out --split PATH/TO/split.json
```

Options: `--conditions C0 C1 C4` (default all five), `--models logreg lgbm mlp`
(default all three), `--seeds 0 1 2` (default from `model_config.json`).

Load saved models and rank candidates of a package:

```sh
python predict.py --package PATH/TO/PACKAGE --run ../../outputs/training/heldout-YYYY-MM-DD --out ../../outputs/training/predict-YYYY-MM-DD
python predict.py ... --conditions C4 --samples sample-ID1 sample-ID2 --evaluate
```

## 4. Outputs

`run_baseline.py --out DIR` writes:

| Path | Content |
|---|---|
| `report.md` | Tables of Top-1/5/10, MRR and median rank per condition, partition and model (mean ± sd over seeds), with the reference rankings |
| `run.json` | Package check, split, feature version, encoder, all hyperparameters, seeds, environment, and per-case ranks for every seed |
| `model_config.json` | Copy of the configuration used |
| `<C>/features.jsonl` | Feature rows keyed by `(sample_id, candidate_id)` |
| `<C>/predictions.jsonl` | One row per candidate, model and seed: `sample_id, candidate_id, path, line, condition, model, seed, partition, score, rank` |
| `<C>/<model>_seed<k>.joblib` | Trained model + fitted preprocessing + feature names + feature version |

`predict.py --out DIR` writes `<C>/predictions.jsonl`, `<C>/top10.md` (top 10 files/lines
per sample) and `predict.json`. It refuses models built with a different feature
version, encoder or feature list.

**Metrics** are per defect, never per candidate row: Top-k is the share of defects whose
bug line is in the top k, and MRR is the mean of 1/rank. Tied scores share their average
rank (expected rank under random tie-breaking), and ties at the bug line are counted.
The `rank` column in prediction files instead gives tied lines the best shared rank.
Reference rankings on the same candidates: random (exact expectation), source order,
and lexical log overlap.

## 5. Features (v2)

Built only from the files in the selected view. Missing evidence is NaN plus a missing
flag, never 0. Not used: line numbers, IDs, operator type, patches, original/restored RTL,
labels, groups, provenance.

| Group | Feature | Definition | Missing when |
|---|---|---|---|
| code/log (all) | `log_overlap` | share of the line's identifiers that appear in the failure log | line has no identifiers |
| | `anchor_resolved` | 1 if an anchor was found | never |
| | `anchor_mention` | line mentions the anchor signal | no anchor |
| | `anchor_src_distance` | lines between the candidate and the nearest line in the same file that mentions the anchor | no such line |
| | `emb_log_sim` | cosine(frozen UniXcoder of candidate ±2 lines, failure part of the log) | never |
| | `universe_size` | number of candidates in the case | never |
| | `syntax_kind` (categorical) | first syntax kind of the candidate | — |
| structure (C1, C4) | `graph_back_dist` | fewest reverse edges from the anchor signal to any of the candidate's aligned signals | unreachable or unmapped |
| | `graph_reachable`, `graph_mapped` | availability flags | — |
| | `graph_register_depth` | fewest registers entered on any backward path from the anchor (register = signal written by a non-blocking assignment) | unreachable or unmapped |
| | `graph_is_register`* | 1 if one of the candidate's signals is a register | unmapped |
| | `graph_fanin`, `graph_fanout`* | most distinct drivers / readers among the candidate's signals | unmapped |
| | `module_dist` | instance-path distance between candidate and DUT scope | no instance |
| waveform (C2, C4) | `wave_available` | the candidate's LHS names matched a traced signal | — |
| | `wave_changed`, `wave_toggles_log1p` | value changes after reset release, up to the first failure | no traced signal |
| | `wave_time_since_change` | (failure tick − last change) / (failure tick − reset release) | no traced signal or no change |
| | `wave_has_xz` | any x/z value seen | no traced signal |
| spec (C3, C4) | `spec_sim_max` | best cosine to any record in the full fixed requirement store | never |

\* Beyond the planned feature table.

**Anchor:** top-module output port(s) whose bit width equals the width of the value
the checker compared (from the checker verdict and buggy RTL only). On the starter
package this is `digest` in every case. **Graph:** edges go from driver (`source`) to
driven signal (`target`); distances walk them backwards from the anchor, cycles keep
the shortest distance, signals are full instance paths, and a candidate with several
signals takes the minimum distance/depth and maximum fan-in/fan-out.

## 6. Models

Fitted on training rows only and saved with each model: median imputation, missing
flags, one-hot `syntax_kind` (unseen kinds → all zero), standardisation (logistic
regression and MLP). LightGBM gets the same columns without imputation or scaling.

| Model | Setup (see `model_config.json`) |
|---|---|
| LightGBM LambdaMART | `LGBMRanker(objective="lambdarank")`, 200 trees, lr 0.05, 15 leaves; candidates of a case contiguous; group sizes rebuilt from the training rows |
| L2 logistic regression | lbfgs, C = 1.0; per-case weights: the bug line(s) share 0.5 and the other lines share 0.5, so every case weighs the same |
| Neural ranker | MLP in → 32 → 16 → 1, ReLU, dropout 0.1; loss = mean softplus(score_other − score_bug) over pairs within each case; Adam lr 1e-3, weight decay 1e-4, 300 full-batch epochs, CPU |

Seeds 0, 1, 2. Settings are fixed, not tuned (single-lineage starter); validation
cases are scored and reported but not used for tuning.

## 7. Smoke-test result (in-sample, 20 development cases)

Trained and scored on the **same** 20 SHA-256 cases, so it only shows the pipeline
works. LightGBM's ~100% is memorisation. Full tables:
[results/smoke-test-2026-11-24/report.md](results/smoke-test-2026-11-24/report.md).

| C4, mean of 3 seeds | Top-1 | Top-5 | Top-10 | MRR |
|---|---|---|---|---|
| random (expected) | 0.00 | 0.01 | 0.03 | 0.018 |
| logistic regression | 0.00 | 0.05 | 0.10 | 0.057 |
| neural ranker | 0.03 | 0.33 | 0.50 | 0.168 |
| LightGBM (memorises) | 1.00 | 1.00 | 1.00 | 1.000 |

## 8. Optional no-training reference: RTLCoder surprise

`rtlcoder_surprise.py` ranks each case's candidate lines with a pretrained Verilog
language model and **no training**. The model reads each buggy file from the top;
a token's surprise is `s_i = -log p(t_i | earlier tokens)`, and a line's score is the
largest surprise among its tokens. The model, revision, 8-bit precision, window
(1,024 tokens, 256 overlap) and per-line tokenization are fixed in the script.

```sh
python -m pip install -r requirements-rtlcoder.in      # on top of the training environment, CUDA torch
python rtlcoder_surprise.py --package PATH/TO/PACKAGE --out ../../outputs/training/rtlcoder-YYYY-MM-DD --evaluate
```

Needs a CUDA GPU (about 70 seconds for the 20 starter cases on an RTX 4070 SUPER, 12 GB,
once the model is downloaded; the first run downloads it). Output: `predictions.jsonl` (file, line, score, rank
per candidate) and `result.json`.

Starter package, 20 development cases ([result.json](results/rtlcoder-surprise-2026-11-24/result.json)):

| No training | Top-1 | Top-5 | Top-10 | MRR | Median rank |
|---|---|---|---|---|---|
| RTLCoder surprise (max per line) | 0.15 | 0.55 | 0.60 | 0.303 | 5 |
| RTLCoder surprise (mean per line) | 0.05 | 0.20 | 0.30 | 0.146 | 23 |
| random (expected) | 0.00 | 0.01 | 0.03 | 0.018 | 180 |

Nothing was fitted on these cases, but SHA-256 is public code that may be in
RTLCoder's pretraining data, so this may be optimistic. It is a reference ranking,
not a feature of the trained models.
