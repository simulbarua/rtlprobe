# RTLProbe implementation

Put the project's Python implementation directly in this directory, without a
`src/` parent. The outer repository and this Python package have different roles.

Responsibilities include configuration validation, pipeline execution, compilation
and simulation, checker adapters, lint and synthesis, artifact extraction, approved
mutation operators, evidence auditing, dataset processing, localization models,
and evaluation.

The target-selected runner supplies mutation operators, checker parsing,
qualification, bounded execution, restoration, immutable evidence, curation-index
checks, and generic proposal execution in `execution.py`.
Use [`../scripts/rtlprobe.py`](../scripts/rtlprobe.py) with explicit data and target-manifest paths.
The older artifact tooling remains under [`../tooling/`](../tooling/README.md).

Keep target-specific manifests and checker adapters in `targets/`. The Python
runner resolves downloaded sources and generated artifacts under its external data
root. The older artifact tooling uses repo-local `vendor/` and `outputs/`.
