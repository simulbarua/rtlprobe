# Execution and data layout

RTLProbe owns deterministic qualification, mutation mapping, execution,
restoration, evidence checks and curation. Its commands and machine contracts
are usable directly by contributors or by external clients. Optional agent
orchestration is maintained in the separate
[rtlprobe-agents repository](https://github.com/simulbarua/rtlprobe-agents).

## Stable script interface

Run with the main runner's Python environment and an absolute data directory.
The script works from any current directory:

```sh
/path/to/rtlprobe/.venv-dataset/bin/python /path/to/rtlprobe/scripts/rtlprobe.py --data-root /path/to/rtlprobe-data paths
```

Actions are `paths`, `fetch`, `check`, `qualify`, `run`, `audit`, `audit-data`,
`accept`, `promote-auto`, and `sample-auto`.
Target operations (`fetch`, `check`, `qualify`, `run`) require an absolute
`--target-config /path/to/target.json` before the action. There is no implicit
target, inherited target selection, named-target allowlist, or data-root config override.
`audit` and `audit-data` can operate without a target manifest.
`run` accepts a machine-proposal JSONL file or a sealed bundle directory. It has no
model/provider-specific assumptions. A client may supply `--bundle-sha256 HASH`
before `run` to pin the exact manifest it validated; the main runner checks that
hash and all bundle files inside its execution transaction. It then validates
source coordinates, approved operators, test/configuration, and resource policy.

External clients submit the same machine proposals or sealed bundles and are
subject to the runner's independent validation. Model request preparation and
provider-specific configuration are outside the runner interface.

`check` verifies current qualified source/configuration/tools/implementation.
`qualify` executes the baseline and checker control. `run` invokes the existing bounded batch runner. `audit-data` verifies saved case
manifests and acceptance receipts without fresh execution. `audit CASE_DIRECTORY`
re-parses saved logs and verifies the actual source/executable/patch evidence.

`RTLPROBE_DATA_ROOT` is set before imports by the script. Code/schema/registry and
Python dependency pins resolve from the code repository; source checkouts, mutable
dossiers, plans, state, and outputs resolve from the selected data root. The script
rejects a data root overlapping its code repository. The main script does not read model prompt settings; those are an agent-side concern. Direct library imports retain a repository-local
default for compatibility; external agents should use the script interface.

## Case curation

These actions require no target config and acquire the existing
`workspace_lock(data_root)` for the entire read/check/write transaction:

```sh
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data accept CASE_ID --reviewer NAME --decision approve --evidence "Review rationale" --document /absolute/review.md
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data accept CASE_ID --reviewer NAME --decision reject --evidence "Rejection rationale"
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data promote-auto --first-n 5 --dry-run
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data promote-auto --first-n 5
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data sample-auto --fraction 0.10
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data audit-data
```

The curation states are `validated_pending_review`, `accepted_core`,
`accepted_auto`, and `rejected`. Existing terminal execution states remain
`needs_review`, `invalid`, `unexposed`, `infrastructure_error`, `unsupported`,
and `flaky`. Curation only starts from pending or auto-accepted cases; it does
not change sealed evidence or recover terminal execution failures. Rejected
cases retain their evidence for auditing and deduplication, with both acceptance
flags zero; dataset consumers select accepted states explicitly and exclude them.

`accepted_core` means a named human approved the case. `accepted_auto` means it
passed the automated acceptance policy without that human approval. The distinction
records what was actually reviewed: counts always show these states separately,
and no accepted-total field combines them. `audit-data` reports state counts and,
for each design/operator pair, `accepted_core`, `accepted_auto`, `pending`,
`held_with_reasons` (case IDs, ranks, and reasons), and `rejected`. Pending includes
held cases. Hold reporting uses the default first-N policy and sealed checks;
`promote-auto --dry-run` additionally runs the saved-evidence audit for eligible
cases. The batch runner reports `newly_accepted_core: 0` and
`newly_accepted_auto: 0`; curation is a separate action.

`accept` requires a reviewer, decision, and evidence text, with an optional review
document whose text, path, and hash are retained in the review. Approval changes
pending or auto cases to `accepted_core`; rejection changes either to `rejected`.
It replaces the current review and label, records their previous hashes and the
previous index hash, and binds the acceptance receipt to the review, sealed case,
and case manifest. An auto receipt replaced by human review is preserved under
`data/reviews/history/<case_id>/`, and its hash is added to the new receipt.
Human acceptance remains an explicit human decision; this command does not infer it.

`promote-auto` defaults to `--first-n 5` (nonnegative integer). Rank is one-based
within `(design_id, proposal.operator.id)`, among pending, core, auto, and rejected
cases, ordered by the timestamp suffix of `case_path`; path and ID break ties.
Ranks 1 through N wait for human review. Later cases are held for non-pass automated
validation, unconfirmed predictions, an independently checked first-checkpoint
mismatch, any false check, a pair policy file, or a failed saved-evidence audit.
Gate reasons use only sealed `case.json`; annotations never influence them.
Eligible cases must pass `pilot.audit` immediately before promotion. Dry-run prints
`PROMOTE` or `HOLD`, pair, rank, and reasons for each pending case, without changing
file contents or creating curation/reservation records. Acquiring the controller
lock is permitted; its existing behavior can create the lock on a fresh data root.

`sample-auto` defaults to `--fraction 0.10` (finite, greater than zero, at most one).
The seed is `identity(sorted case ids)`. It chooses one random member per pair,
then fills to `ceil(fraction * population size)` with uniformly chosen remaining
cases. Thus the per-pair floor may exceed the fraction for a small population.
The same population and fraction select the same cases. Each immutable
`data/reviews/samples/<utc-stamp>-<hash>.json` records the population, pairs,
sample, fraction, seed, and the first-N values of the population's receipts.
An empty population produces an empty sample. Rejecting a sampled case creates
`data/reviews/policy/<design_id>__<operator_id>.json` with `full_review: true`,
the rejected ID, timestamp, and sample references. While that file exists, every
pending case of the pair is held with `pair_under_full_review`. Existing auto
receipts stay valid; policy removal is a separate human action.

New receipts use [curation-2](../rtlprobe/schemas/curation_v2.json). A standard-library
validator enforces the schema's supported keywords before any receipt is written.
Every receipt records `from_state`, `to_state`, reviewer/review bindings (null on
auto receipts), the manifest hash, `validation_record` (sealed `case.json`) and
`validation_sha256`, policy parameters (`first_n`, `fraction`, pair, rank, holds),
previous record hashes, and UTC timestamp. Human review inherits an auto receipt's
first-N value and, when sampled, the most recent sample fraction. New human cases
record the defaults. Old `curation-1` approvals retain their existing verification
checks. New auto/rejected branches check receipt and sealed-evidence bindings;
auto verification also recomputes sealed gate holds. Pair policies govern future
promotion rather than invalidating previously issued receipts.

All curation data stays in `data/reviews/`, `data/labels/`, and `data/manifests/`.
These are evaluator-only records, excluded from localizer inputs along with the
original RTL, mutation patch, operator metadata, case IDs, and acceptance records.

## Data directory

```text
rtlprobe-data/
├── tools/dataset/vendor/<selected>/   Pinned separate upstream Git checkout
├── designs/<target_id>/               Config/dossier/current qualification pointer
├── data/plans/                   Frozen machine proposals and client records
├── data/manifests/               Current case indexes
├── data/reviews/                 Human decisions and acceptance receipts
├── data/labels/                  Curator labels
├── data/patches/                 Scoped mutation patches
├── data/state/                   Single-writer lock and recovery state
└── outputs/<target_id>/               Immutable qualification/case evidence
```

The manifest supplies the pinned repository URL/commit, data-relative `vendor` path,
`target_id`, `case_prefix`, `split_group`, RTL/TB inputs, test metadata, control,
checker adapter, scope, and limits. The SHA-256 example is
`targets/sha256/config.json`; selecting it is explicit. Dossier contents and paths
are derived from the selected configuration.

`rtlprobe/oracle.py` dispatches to the declared trusted local checker file, which
is fingerprinted and copied into qualification evidence. It also checks outcome,
checkpoint, and simulator-status consistency. The SHA-256-specific parser is in
`targets/sha256/checker.py`. Historical bundles are audited with their frozen
checker; they are not reinterpreted using a newly selected target. The earliest
pilot case has no frozen checker snapshot. Auditing such a case requires explicit
`--target-config` selection, matching repository/test settings, and reports
`explicit_compatibility_reparse`; it does not claim historical code reconstruction.

The main `scripts/fetch-design.sh /absolute/target.json` uses an absolute
`RTLPROBE_DATA_ROOT` and the configured `RTLPROBE_PYTHON` (or `python3`). It invokes
the main Python fetch command and refuses to switch dirty/different existing
checkouts. Source retrieval alone does not qualify a target.

Select the execution backend explicitly through the manifest when needed:
Icarus for the existing crypto targets, or the supported Verilator pre_dv/UVM
flows. Backend-specific build options and admission constraints are described in
[Verilator backends](verilator-backends.md). A parsed manifest or fetched source
is not proof of functional qualification.

## Evidence migration

Copy the complete dataset tree, preserving case-relative paths and bytes. Do not
rewrite absolute host paths in sealed historical logs. Saved-evidence auditing
checks the internal consistency of recorded variant/executable paths and compares
actual files/hashes in their current location; it does not rerun commands at old
paths. All five simulation records must reference the same recorded case root.

Preserve historical qualification pointers and evidence when refreshing a target;
create a new qualification record instead of rewriting the prior one. Metadata
auditing and content deduplication do not establish a replay on a new host.
Acceptance records remain separate from sealed execution evidence.

## Setup on a new host

1. Clone the runner and copy the complete external data tree while preserving
   the source copy until verification succeeds.
2. Create a Python 3.12 environment and install
   `python -m pip install -r requirements-dataset.lock.txt`. Rebuild the
   environment on that host rather than copying a platform-specific venv.
3. Install Git, patch, Icarus, Verilator and Yosys as required by the selected
   backend. A tool image or matching version banner alone is not qualification.
4. Run `audit-data` against the copied data tree, then fresh `qualify` and `check`
   with the explicit target manifest and host-specific backend environment.
   Pending-control targets still require their remaining qualification gates.

The [tooling scripts](../tooling/README.md) collect raw artifacts. Their process
exit status does not replace the qualified functional checker, mutation validation
or restoration gates.

## Optional submodule use

This repository may be consumed as a Git submodule, but no command assumes a
particular parent checkout. Configure the runner with an absolute `DATA_ROOT`.
Full experiment evidence can be maintained under a separate `EVIDENCE_ROOT`;
large execution artifacts and curator-only records stay outside source checkouts.
