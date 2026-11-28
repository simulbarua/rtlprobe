# RTLProbe documentation

These guides describe the shared capstone implementation and its reproducible
experiments. Start with the [project README](../README.md).

| Guide | Contents |
|---|---|
| [Execution and data layout](execution-layout.md) | Runner commands, configuration, curation, external data and evidence portability |
| [Serial execution measurements](measurement.md) | Opt-in elapsed/CPU traces, exclusive stage accounting, host samples and measurement limits |
| [Dataset artifact contract](dataset-artifacts.md) | Versioned collection coordinates, required retention, completeness, provenance and private/public boundaries |
| [Mutation operators](mutation-operators.md) | Approved edits, safety constraints, candidate extraction and read-only inspection commands |
| [Verilator backends](verilator-backends.md) | Build requirements, manifest fields, checker contracts and qualification limits |
| [Buggy evidence capture](evidence-capture.md) | Additive observational capture, raw VCD retention, source/signal/time mapping and integration limits |
| [Sanitized condition exports](sanitized-exports.md) | C0–C4/M allowlisted views, shared candidates, manifest checks and isolation limits |
| [Baseline training](../experiments/training/README.md) | Starter dataset, ranker training, split checks, and evaluation |
| [Localization pilot](localization.md) | Experiment method, recorded baseline results, limitations and reproduction entry point |
| [Target configuration](../targets/README.md) | Target manifests and admission gates |
| [Specification stores](../targets/SPEC_STORE.md) | Source-backed requirements, curation and inference boundaries |
| [Tests](../tests/README.md) | Software validation and its scope |
| [Tooling](../tooling/README.md) | Historical raw-artifact collection tools |

## Repository catalog

The [repository catalog](RTLProbe_Repository_Catalog.xlsx) lists candidate
repositories and proposed pilot/split selections. Catalog status does not establish
testbench qualification or dataset admission; execution requires an explicit
target manifest and fresh qualification.

The maintained spreadsheet was imported on October 19, 2026 from the shared
project-workspace catalog.

## Documentation policy

Keep setup, architecture, machine contracts, dataset methodology and reproducible
capstone methods/results here. Describe implemented behavior and known limits,
and distinguish recorded results from fresh verification. Research claims need
primary sources. Dated team/advisor notes belong in [meetings](../meetings/README.md).

Bulk evidence stays in the configured external data/evidence roots. The existing
[Verilator validation archive](evidence/verilator-2026-10-24/README.md) is retained
unchanged for provenance; its original-only observations do not establish full
target qualification. Test fixtures remain with their owning tests.

Use repository-relative links for runner files and portable example paths.
Contributor instructions must work with this checkout alone. Check executable
registries and manifests before stating current approval or target support;
dated results remain historical observations, not fresh qualification.
