# RTLProbe repository inventory and agent-boundary audit

> Dated audit. The sibling paths it names (`github/rtlprobe`, `github/rtlprobe-agents`, `rtlprobe-data`, `workarea`) are the pre-2026-10-23 layout; this repository is now the `rtlprobe/` submodule of `rtlprobe-agents`, with data and the workarea under a local root outside both. See `docs/execution-layout.md`.

Audited October 19, 2026; refreshed after target-manifest generalization and the real ChaCha trial. This lists all version-control-eligible files in the active main checkout, including pending untracked implementation files. It excludes `.git`, ignored caches, local environments/configuration, and generated data.

**Conclusion:** agent preparation, model-response interpretation, Hermes provenance, prompts, skills, and their schemas/tests live in the separate `rtlprobe-agents` repository. The main repository retains reusable hardware/dataset operations, machine contracts, tests, infrastructure, and project records.

**Scope:** this inventory covers the active `github/rtlprobe` checkout. The parent workspace also retains `workarea`, the historical prototype with its original planner/skill/tests and evidence. That preserved copy is not the active main repository or deployment source. The active agent implementation is in sibling `github/rtlprobe-agents`; active experiment records are in sibling workspace directory `rtlprobe-data`.

## Cleanup during this audit

- Removed unused model-call budget metadata from the main SHA-256 template and unused model-accounting placeholders from newly emitted core cost records. Model accounting remains in the agent receipt. Existing sealed data records/configurations were not rewritten.
- Removed the unused prompt-environment cleanup from the core CLI; core execution does not consume model prompt settings.
- Removed three ignored bytecode cache files for the moved planner/Hermes tests and module.
- Clarified that `data/`, `outputs/`, and `vendor/` contain guides in this checkout; the active Python runner uses a separate data directory.

## Complete inventory

64 files (including the catalog, real ChaCha trial, and detailed human review):

| Path | Why it belongs in RTLProbe |
|---|---|
| [.dockerignore](../.dockerignore) | Excludes local credentials/configuration, downloaded sources, caches, and generated data from image builds. |
| [.gitignore](../.gitignore) | Excludes local environments, credentials/configuration, bulk artifacts, and runtime state from version control. |
| [Dockerfile](../Dockerfile) | Hardware-tool container definition for the existing artifact pipeline; no agent runtime. |
| [README.md](../README.md) | Project scope, current implementation status, and links to operating instructions. |
| [data/README.md](../data/README.md) | Dataset record and retention guide; actual active records are in the external data directory. |
| [docs/README.md](../docs/README.md) | Research/technical documentation ownership guide. |
| [docs/RTLProbe_ChaCha_Agent_Trial_2026-10-19.md](../docs/RTLProbe_ChaCha_Agent_Trial_2026-10-19.md) | Real-repository mutation review, observed validation, manual interventions, evidence references, and remaining work. |
| [docs/RTLProbe_Repository_Catalog.xlsx](../docs/RTLProbe_Repository_Catalog.xlsx) | Shared candidate repository catalog, imported unchanged; pilot/split annotations are not proof of target qualification. |
| [docs/execution-layout.md](../docs/execution-layout.md) | Core script interface, location resolution, evidence migration, and destination setup. |
| [docs/repository-inventory.md](../docs/repository-inventory.md) | This audit inventory and explanation of the current ownership boundary. |
| [docs/reviews/chacha-cf9ca6a8bc3bf5b4.md](../docs/reviews/chacha-cf9ca6a8bc3bf5b4.md) | Detailed human review of the preserved ChaCha mutation, explaining one variant versus three runs, source context, requirement, recorded outcomes, evidence links, and acceptance questions. |
| [meetings/2026-08-28-team.md](../meetings/2026-08-28-team.md) | Dated team/advisor decisions and capstone project history. |
| [meetings/2026-09-10-advisor.md](../meetings/2026-09-10-advisor.md) | Dated team/advisor decisions and capstone project history. |
| [meetings/2026-09-15-team.md](../meetings/2026-09-15-team.md) | Dated team/advisor decisions and capstone project history. |
| [meetings/2026-09-17-advisor.md](../meetings/2026-09-17-advisor.md) | Dated team/advisor decisions and capstone project history. |
| [meetings/2026-09-23-team.md](../meetings/2026-09-23-team.md) | Dated team/advisor decisions and capstone project history. |
| [meetings/2026-09-29-team.md](../meetings/2026-09-29-team.md) | Dated team/advisor decisions and capstone project history. |
| [meetings/README.md](../meetings/README.md) | Team/advisor meeting-note organization. |
| [outputs/README.md](../outputs/README.md) | Artifact retention guide; active mutation evidence is external, legacy tooling can write here. |
| [requirements-dataset.in](../requirements-dataset.in) | Direct Python dependencies for parsing, validation, graph/data and waveform tooling. |
| [requirements-dataset.lock.txt](../requirements-dataset.lock.txt) | Pinned Python environment for reproducible core tooling; no model-provider SDK. |
| [rtlprobe/README.md](../rtlprobe/README.md) | Core package responsibilities and ownership boundary. |
| [rtlprobe/__init__.py](../rtlprobe/__init__.py) | Defines the reusable Python package. |
| [rtlprobe/batch.py](../rtlprobe/batch.py) | Preflight, isolated execution, three-run reproduction, restoration, lint/synthesis, dispositions, and batch accounting. |
| [rtlprobe/evidence.py](../rtlprobe/evidence.py) | Bounded subprocess execution, logs, hashes, manifests, atomic writes, environment fingerprints, and process locking. |
| [rtlprobe/execution.py](../rtlprobe/execution.py) | Generic machine-proposal execution; checks sealed bundles and an optional caller-provided manifest hash. |
| [rtlprobe/fetch.py](../rtlprobe/fetch.py) | Generic pinned Git retrieval from the selected manifest; rejects dirty or different existing checkouts. |
| [rtlprobe/lifecycle.py](../rtlprobe/lifecycle.py) | Content identity, duplicate detection, bounded recovery, immutable publication, and acceptance-receipt integrity. |
| [rtlprobe/mutation.py](../rtlprobe/mutation.py) | AST-checked supported mutation operators and exact source-span mapping; shared enforcement for all clients. |
| [rtlprobe/operators.json](../rtlprobe/operators.json) | Approved executable operator registry, versions, applicability/exclusions, and implementation-review provenance. |
| [rtlprobe/oracle.py](../rtlprobe/oracle.py) | Dispatches to the explicitly selected checker adapter and validates verdict/checkpoint consistency; handles labeled historical reparsing. |
| [rtlprobe/pilot.py](../rtlprobe/pilot.py) | Selected-target qualification, snapshots, build/simulation/lint/synthesis helpers, restoration gates, and evidence audits; no repository default. |
| [rtlprobe/schemas/case.json](../rtlprobe/schemas/case.json) | Version 1 validated-case record contract, retained for existing evidence. |
| [rtlprobe/schemas/case_v2.json](../rtlprobe/schemas/case_v2.json) | Version 2 validated-case record contract. |
| [rtlprobe/schemas/design.json](../rtlprobe/schemas/design.json) | Machine-readable qualification record contract. |
| [rtlprobe/schemas/proposal.json](../rtlprobe/schemas/proposal.json) | Version 1 exact-edit execution request contract, retained for historical record compatibility. |
| [rtlprobe/schemas/proposal_v2.json](../rtlprobe/schemas/proposal_v2.json) | Version 2 exact-edit execution request contract for current supported operators. |
| [rtlprobe/target.py](../rtlprobe/target.py) | Validates explicit target manifests and resolves selected namespaces/checker paths without repository defaults. |
| [scripts/README.md](../scripts/README.md) | Operating instructions for generic core scripts. |
| [scripts/fetch-design.sh](../scripts/fetch-design.sh) | Manifest-based pinned source retrieval through the core Python fetch command; no named-target allowlist. |
| [scripts/rtlprobe.py](../scripts/rtlprobe.py) | Paths/fetch/check/qualify/run/audit/audit-data CLI with explicit target selection; any human or client can call it. |
| [targets/README.md](../targets/README.md) | Target configuration/admission requirements and source-path rules. |
| [targets/chacha/README.md](../targets/chacha/README.md) | Target qualification scope, reproduction, lineage, and known parser limitations. |
| [targets/chacha/checker.py](../targets/chacha/checker.py) | Strict adapter for the unchanged upstream fifteen-comparison ChaCha suite, including duplicated labels and exact expected words. |
| [targets/chacha/config.json](../targets/chacha/config.json) | Explicit real ChaCha target, pinned RTL/TB, scope, checkpoint mapping, distinct control, and bounded resource policy. |
| [targets/sha256/checker.py](../targets/sha256/checker.py) | SHA-256-specific strict checker adapter, explicitly selected and frozen with qualification evidence. |
| [targets/sha256/config.json](../targets/sha256/config.json) | Explicit SHA-256 target example: pinned RTL/TB/configuration, checker path, namespace/lineage, metadata, control, and hardware limits. |
| [tests/README.md](../tests/README.md) | Test suite setup, scope, and limits. |
| [tests/fixtures/tiny_checker.py](../tests/fixtures/tiny_checker.py) | Strict checker for an unrelated synthetic software integration fixture; never benchmark admission evidence. |
| [tests/test_batch.py](../tests/test_batch.py) | Mutation applicability, recovery, duplicate/publication protection, and execution dispositions. |
| [tests/test_chacha_checker.py](../tests/test_chacha_checker.py) | Completeness, contradictory logs, expected-value checks, repeated-label identity, and simulator-status regression tests. |
| [tests/test_data_paths.py](../tests/test_data_paths.py) | External data roots, independent working directory, and absence of embedded agent workflows. |
| [tests/test_execution.py](../tests/test_execution.py) | Generic bundle execution, manifest pinning, plain proposals, and agent-free core CLI surface. |
| [tests/test_launcher.py](../tests/test_launcher.py) | Existing Docker launcher mounts, cwd/argument safety, and exit-status propagation. |
| [tests/test_pilot.py](../tests/test_pilot.py) | Checker outcomes, exact source edits, acceptance gates, and evidence integrity. |
| [tests/test_pipeline_paths.py](../tests/test_pipeline_paths.py) | Native-tool smoke tests of artifact output routing; not dataset qualification. |
| [tests/test_targets.py](../tests/test_targets.py) | Explicit-target isolation, checker integrity, incompatible manifests, and historical-audit compatibility tests. |
| [tooling/.gitignore](../tooling/.gitignore) | Excludes legacy downloads, builds, and generated outputs. |
| [tooling/DATASETS.md](../tooling/DATASETS.md) | Historical target investigations and setup observations. |
| [tooling/FINDINGS.md](../tooling/FINDINGS.md) | Historical pipeline findings, testbench limits, and open technical choices. |
| [tooling/README.md](../tooling/README.md) | Legacy artifact pipeline usage and known limitations. |
| [tooling/pipeline.sh](../tooling/pipeline.sh) | Host launcher for the existing Docker artifact pipeline. |
| [tooling/run_pipeline.sh](../tooling/run_pipeline.sh) | Existing raw compilation/simulation/lint/Yosys/AST artifact collector; not the semantic mutation acceptance oracle. |
| [vendor/README.md](../vendor/README.md) | Downloaded-source policy and legacy tooling input location; active pilot sources are external. |

## Why some related metadata remains

Execution proposals include activation hypotheses, predicted checkpoints, requirements, and optional confidence. These describe a proposed defect and aid review; they can come from a human or any client and never establish acceptance. Case/label/review/approval contracts and leakage boundaries belong to dataset curation. They are not agent runtime or provider configuration.

Operator review notes truthfully record the earlier implementation review and tests. These historical provenance fields remain with the executable operator registry. Documentation that names the separate agent repo and tests that assert its absence are boundary checks, not misplaced implementations.

## Limitations and next actions

The ownership-only audit passed 41 core tests and 30 agent tests. Subsequent target generalization adds explicit-selection/checker tests and an unrelated synthetic full-flow regression. The subsequent real ChaCha trial passed 55 core and 32 agent tests and produced one case pending human review. See its trial report for evidence, manual setup, and parser limitations. Existing curated-case approvals remain separate from software test fixtures.

The shared runner and agent launcher are now target-selected. SHA-256 and ChaCha are explicit configured targets with real pilot evidence. An unrelated tiny fixture tests target independence; it is not a benchmark repository. The backend still supports one deterministic Icarus TB, Verilator/Yosys, and the two existing narrow 32-bit operators. Catalog discovery, additional build-system adapters, and trained localization/evaluation implementations remain unfinished.

The native Python mutation runner and the older Docker artifact pipeline coexist for different purposes. Only the qualified runner supplies the accepted mutation validation gates. Container build/host compatibility must be established on the execution host.

Decision: keep shared operators, execution, verification, machine schemas, and curation in the main repo; keep model/agent workflows outside. Next: add qualified real targets through manifests/adapters and qualify BaruaLabs before live generation.
