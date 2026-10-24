# Execution layout and external agents

RTLProbe owns deterministic qualification, mutation mapping, execution, restoration,
and evidence checks. The separate `rtlprobe-agents` repository owns Hermes skills,
model instructions, and the orchestration launcher. The main repository includes
no agent runtime, model prompt package, request/response workflow, or Hermes-specific
provenance schema. Agent-side workflows and tests belong to `rtlprobe-agents`.

## Stable script interface

Run with the main runner's Python environment and an absolute data directory.
The script works from any current directory:

```sh
/path/to/rtlprobe/.venv-dataset/bin/python /path/to/rtlprobe/scripts/rtlprobe.py --data-root /path/to/rtlprobe-data paths
```

Actions are `paths`, `fetch`, `check`, `qualify`, `run`, `audit`, and `audit-data`.
Target operations (`fetch`, `check`, `qualify`, `run`) require an absolute
`--target-config /path/to/target.json` before the action. There is no implicit
target, inherited target selection, named-target allowlist, or data-root config override.
`audit` and `audit-data` can operate without a target manifest.
`run` accepts a machine-proposal JSONL file or a sealed bundle directory. It has no
model/provider-specific assumptions. A client may supply `--bundle-sha256 HASH`
before `run` to pin the exact manifest it validated; the main runner checks that
hash and all bundle files inside its execution transaction. It then validates
source coordinates, approved operators, test/configuration, and resource policy.

The agent repo's own `scripts/planner.py` performs preparation, response import,
Hermes provenance, and agent-record checks. It imports core mapping/qualification
helpers from this explicit main checkout. It calls this main script for hardware
execution; no hardware/checker implementation is duplicated in the agent repo.

`check` verifies current qualified source/configuration/tools/implementation.
`qualify` executes the baseline and checker control. `run` invokes the existing bounded batch runner. `audit-data` verifies saved case
manifests and acceptance receipts without fresh execution. `audit CASE_DIRECTORY`
re-parses saved logs and verifies the actual source/executable/patch evidence.

`RTLPROBE_DATA_ROOT` is set before imports by the script. Code/schema/registry and
Python dependency pins resolve from the code repository; source checkouts, mutable
dossiers, plans, state, and outputs resolve from the selected data root. The script
rejects a data root overlapping its code repository. The main script does not read model prompt settings; those are an agent-side concern. Direct library imports retain a repository-local
default for compatibility; external agents should use the script interface.

## Data directory

```text
rtlprobe-data/
├── tools/dataset/vendor/<selected>/   Pinned separate upstream Git checkout
├── designs/<target_id>/               Config/dossier/current qualification pointer
├── data/plans/                   Frozen requests, responses, and plans
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

The backend still supports one existing deterministic Icarus TB, Verilator lint,
Yosys synthesis, empty defines/parameters, and the current narrow AST operators.
Additional build systems, languages, seeded tests, or testbench environments need
explicit backend support. Repository discovery is separate, unfinished work.

## Evidence migration

Copy the complete dataset tree, preserving case-relative paths and bytes. Do not
rewrite absolute host paths in sealed historical logs. Saved-evidence auditing
checks the internal consistency of recorded variant/executable paths and compares
actual files/hashes in their current location; it does not rerun commands at old
paths. All five simulation records must reference the same recorded case root.

The original `workarea` prototype and its evidence are retained as a historical
snapshot. The separated data copy retains the fourteen existing cases and their
human decisions. A new qualification updates only the copied current dossier and
adds a new sealed qualification directory. Previous dossier pointers were archived
under `history/pre-separation-dossier/` before refreshing them.

Accepted cases remain historical accepted evidence after a copy. Metadata auditing
or content deduplication does not establish a new-host replay. Preserve provider
usage as reported/unknown and retain human acceptance as a separate transition.

## Setup on BaruaLabs

1. Transfer/clone the main code checkout, the separate agents checkout, and the full
   data tree. Preserve the original development copy until verification succeeds.
2. Rebuild the main Python environment with Python 3.12 and
   `python -m pip install -r requirements-dataset.lock.txt`. Do not copy a Mac venv.
3. Install/check native Git, patch, Icarus, Verilator, and Yosys for the destination.
   The historical Docker tooling image is a separate environment and is not evidence
   that this Python runner has been qualified in that image.
4. Configure the agents repository's absolute code/data/Python/target-manifest paths, load its skill,
   run `audit-data`, then perform fresh `qualify` and prepare a new request.

The existing `tooling/` scripts remain available for raw artifact collection. Their
process exit status is not the semantic mutation acceptance oracle. Agents must
use the qualified runner script for bug validation and restoration.


## Consumption as a submodule (added 2026-10-23)

This repository may be consumed as a Git submodule pinned at `rtlprobe/`
inside the `rtlprobe-agents` repository. Nothing in this repository may
assume a particular parent directory. Two locations stay outside both
repositories on every machine: `DATA_ROOT`, the external data root the
runner is given explicitly, and `EVIDENCE_ROOT`, the folder holding sealed
session evidence that older documents here cite (on the development Mac,
`~/Work/ml_projects/RTLProbe/local/rtlprobe-data` and
`~/Work/ml_projects/RTLProbe/local/reference/evidence`). Documents that cite
evidence use those two names rather than relative paths that climb above
the checkout.
